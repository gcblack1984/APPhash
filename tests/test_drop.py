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


@unittest.skipUnless(sys.platform == "win32", "solo Windows")
class WindowsDropTest(unittest.TestCase):
    """Invia alla finestra un vero messaggio WM_DROPFILES, come fa Esplora file."""

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # nessuna sessione grafica disponibile
            self.skipTest("Tk non disponibile: %s" % exc)
        self.root.geometry("300x200")
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    @staticmethod
    def _send_drop(hwnd, paths):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t

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
        user32.SendMessageW(hwnd, A.WinFileDrop.WM_DROPFILES, hglobal, 0)

    def test_trascinamento(self):
        received = []
        drop = A.WinFileDrop(self.root, received.append)
        self.assertTrue(drop.ok, "installazione del trascinamento non riuscita")

        with tempfile.TemporaryDirectory() as d:
            paths = [os.path.join(d, "perché è.txt"), os.path.join(d, "Cartella")]
            self._send_drop(drop.hwnd, paths)
            for _ in range(20):
                self.root.update()
                if received:
                    break
            self.assertEqual(received, [paths])

        # gli altri messaggi devono continuare ad arrivare alla finestra
        self.root.title("ancora attiva")
        self.root.update()
        self.assertEqual(self.root.title(), "ancora attiva")


if __name__ == "__main__":
    unittest.main()
