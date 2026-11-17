# -*- coding: utf-8 -*-
"""Test del trascinamento di file e cartelle sulla finestra."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import apphash as A  # noqa: E402


class PickDroppedTest(unittest.TestCase):
    def test_vuoto(self):
        self.assertEqual(A.pick_dropped([]), (None, None))
        self.assertEqual(A.pick_dropped(["", "  "]), (None, None))

    def test_un_elemento(self):
        p = os.path.join("C:", "Atti", "Fascicolo.zip")
        path, msg = A.pick_dropped([p])
        self.assertEqual(path, os.path.normpath(p))
        self.assertIn("Calcola hash", msg)

    def test_piu_elementi(self):
        a = os.path.join("C:", "Atti", "uno.pdf")
        b = os.path.join("C:", "Atti", "due.pdf")
        path, msg = A.pick_dropped([a, b])
        self.assertEqual(path, os.path.normpath(a))
        self.assertIn("2 elementi", msg)
        self.assertIn("uno.pdf", msg)


class PollTest(unittest.TestCase):
    """I percorsi messi da parte vengono consegnati dal ciclo degli eventi."""

    def test_consegna_e_riprogramma(self):
        from unittest import mock
        widget = mock.Mock()
        received = []
        with mock.patch.object(sys, "platform", "linux"):
            drop = A.WinFileDrop(widget, received.append)
        self.assertFalse(drop.ok)
        drop.pending += [["a.txt"], ["b.txt", "c.txt"]]
        drop._poll()
        self.assertEqual(received, [["a.txt"], ["b.txt", "c.txt"]])
        self.assertEqual(drop.pending, [])
        widget.after.assert_called_with(drop.POLL_MS, drop._poll)

    def test_errore_non_ferma_il_controllo(self):
        from unittest import mock
        widget = mock.Mock()

        def broken(paths):
            raise ValueError("errore di prova")

        with mock.patch.object(sys, "platform", "linux"):
            drop = A.WinFileDrop(widget, broken)
        drop.pending.append(["a.txt"])
        with self.assertRaises(ValueError):
            drop._poll()
        widget.after.assert_called_with(drop.POLL_MS, drop._poll)


@unittest.skipUnless(sys.platform == "win32", "solo Windows")
class WindowsDropTest(unittest.TestCase):
    """Rilascio di file come lo fa Esplora file.

    Il messaggio WM_DROPFILES viene messo in coda (PostMessage) e consegnato dal
    ciclo degli eventi di Tk (mainloop), cioe' la stessa strada di un vero
    trascinamento. Nella versione 1.1.0 questa strada faceva chiudere il programma.
    """

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # nessuna sessione grafica disponibile
            self.skipTest("Tk non disponibile: %s" % exc)
        self.root.geometry("300x200")
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    @staticmethod
    def _post_drop(hwnd, paths):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL

        class DROPFILES(ctypes.Structure):
            _fields_ = [("pFiles", wintypes.DWORD), ("pt", wintypes.POINT),
                        ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]

        names = ("\0".join(paths) + "\0\0").encode("utf-16-le")
        header = DROPFILES(ctypes.sizeof(DROPFILES), wintypes.POINT(10, 10), False, True)
        size = ctypes.sizeof(DROPFILES) + len(names)
        hglobal = kernel32.GlobalAlloc(0x0042, size)  # GMEM_MOVEABLE | GMEM_ZEROINIT
        ptr = kernel32.GlobalLock(hglobal)
        ctypes.memmove(ptr, ctypes.byref(header), ctypes.sizeof(DROPFILES))
        ctypes.memmove(ptr + ctypes.sizeof(DROPFILES), names, len(names))
        kernel32.GlobalUnlock(hglobal)
        # la finestra legge l'elenco e libera la memoria con DragFinish
        if not user32.PostMessageW(hwnd, A.WinFileDrop.WM_DROPFILES, hglobal, 0):
            raise OSError(ctypes.get_last_error(), "PostMessageW")

    def test_trascinamento_dal_ciclo_degli_eventi(self):
        root = self.root
        received = []
        ticks = [0]

        def on_drop(paths):
            received.append(paths)
            if len(received) == 2:
                root.after(300, root.quit)

        drop = A.WinFileDrop(root, on_drop)
        self.assertTrue(drop.ok, "installazione del trascinamento non riuscita")

        # altri richiami Python frequenti, come nell'app (barra, interfaccia):
        # e' proprio la loro presenza che faceva chiudere la 1.1.0
        def ticker():
            ticks[0] += 1
            root.after(1, ticker)

        with tempfile.TemporaryDirectory() as d:
            first = [os.path.join(d, "perché è.txt"), os.path.join(d, "Cartella")]
            second = [os.path.join(d, "Fascicolo.zip")]
            root.after(50, ticker)
            root.after(100, self._post_drop, drop.hwnd, first)
            root.after(400, self._post_drop, drop.hwnd, second)
            root.after(5000, root.quit)  # rete di sicurezza
            root.mainloop()

        self.assertEqual(received, [first, second])
        self.assertGreater(ticks[0], 10)

        # gli altri messaggi continuano ad arrivare alla finestra
        root.title("ancora attiva")
        root.update()
        self.assertEqual(root.title(), "ancora attiva")


if __name__ == "__main__":
    unittest.main()
