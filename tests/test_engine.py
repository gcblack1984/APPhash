# -*- coding: utf-8 -*-
"""Test del motore di calcolo e dei report (nessuna interfaccia grafica)."""

import hashlib
import os
import re
import sys
import tarfile
import tempfile
import threading
import unittest
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import apphash as A  # noqa: E402

FILES = {
    "nota.txt": b"abc\n",
    "vuoto.bin": b"",
    os.path.join("Allegati", "dati.bin"): bytes(range(256)) * 5000,
    os.path.join("Allegati", "perché.txt"): "testo con accenti àèìòù".encode("utf-8"),
}


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = cls.tmp.name
        cls.folder = os.path.join(cls.base, "Fascicolo")
        for rel, data in FILES.items():
            full = os.path.join(cls.folder, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
        cls.zip = os.path.join(cls.base, "Fascicolo.zip")
        with zipfile.ZipFile(cls.zip, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in FILES:
                z.write(os.path.join(cls.folder, rel), rel.replace(os.sep, "/"))
        cls.tar = os.path.join(cls.base, "Fascicolo.tar.gz")
        with tarfile.open(cls.tar, "w:gz") as t:
            for rel in FILES:
                t.add(os.path.join(cls.folder, rel), rel.replace(os.sep, "/"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def by_name(res, algo):
        return {e["name"].replace("\\", "/"): e["hashes"][algo] for e in res["contents"]}

    def expected(self, algo_fn):
        return {rel.replace(os.sep, "/"): algo_fn(data).hexdigest()
                for rel, data in FILES.items()}

    def test_file_singolo(self):
        res = A.Engine(list(A.ALGOS)).analyze(os.path.join(self.folder, "nota.txt"))
        self.assertEqual(res["kind"], "file")
        self.assertEqual(res["contents"], [])
        data = FILES["nota.txt"]
        self.assertEqual(res["main"]["MD5"], hashlib.md5(data).hexdigest())
        self.assertEqual(res["main"]["SHA-1"], hashlib.sha1(data).hexdigest())
        self.assertEqual(res["main"]["SHA-256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(res["main"]["SHA-384"], hashlib.sha384(data).hexdigest())
        self.assertEqual(res["main"]["SHA-512"], hashlib.sha512(data).hexdigest())
        self.assertEqual(res["main"]["SHA3-256"], hashlib.sha3_256(data).hexdigest())
        self.assertEqual(res["main"]["BLAKE2b"], hashlib.blake2b(data).hexdigest())
        self.assertEqual(res["main"]["CRC32"], "%08x" % zlib.crc32(data))

    def test_valore_noto(self):
        # SHA-256 della stringa vuota
        res = A.Engine(["SHA-256"]).analyze(os.path.join(self.folder, "vuoto.bin"))
        self.assertEqual(
            res["main"]["SHA-256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_cartella(self):
        res = A.Engine(["SHA-256"]).analyze(self.folder)
        self.assertEqual(res["kind"], "folder")
        self.assertEqual(self.by_name(res, "SHA-256"), self.expected(hashlib.sha256))
        self.assertEqual(res["total_size"], sum(len(d) for d in FILES.values()))

    def test_cartella_senza_sottocartelle(self):
        res = A.Engine(["MD5"]).analyze(self.folder, recursive=False)
        self.assertEqual(sorted(e["name"] for e in res["contents"]),
                         ["nota.txt", "vuoto.bin"])

    def test_impronta_cartella_cambia(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.txt")
            with open(p, "w") as f:
                f.write("uno")
            first = A.Engine(["SHA-256"]).analyze(d)["main"]["SHA-256"]
            again = A.Engine(["SHA-256"]).analyze(d)["main"]["SHA-256"]
            self.assertEqual(first, again)
            os.rename(p, os.path.join(d, "b.txt"))
            renamed = A.Engine(["SHA-256"]).analyze(d)["main"]["SHA-256"]
            self.assertNotEqual(first, renamed)

    def test_zip(self):
        res = A.Engine(["SHA-1"]).analyze(self.zip)
        self.assertEqual(res["kind"], "archive")
        with open(self.zip, "rb") as f:
            self.assertEqual(res["main"]["SHA-1"], hashlib.sha1(f.read()).hexdigest())
        self.assertEqual(self.by_name(res, "SHA-1"), self.expected(hashlib.sha1))

    def test_tar(self):
        res = A.Engine(["MD5"]).analyze(self.tar)
        self.assertEqual(res["kind"], "archive")
        self.assertEqual(self.by_name(res, "MD5"), self.expected(hashlib.md5))

    def test_archivio_senza_hash_dei_contenuti(self):
        res = A.Engine(["MD5"]).analyze(self.zip, hash_members=False)
        self.assertEqual(len(res["contents"]), len(FILES))
        self.assertTrue(all(e["hashes"] is None for e in res["contents"]))
        self.assertTrue(res["contents_note"])

    def test_annullamento(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(A.Cancelled):
            A.Engine(["MD5"], cancel=ev).analyze(self.folder)

    def test_report(self):
        res = A.Engine(list(A.DEFAULT_ALGOS)).analyze(self.zip)
        res["operator"] = "Operatore di prova"
        res["reference"] = "Rif. 1/2026"
        formats = ["txt", "html"] + (["pdf"] if A.pdf_available() else [])
        for ext in formats:
            out = os.path.join(self.base, "report." + ext)
            A.save_report(res, out)
            self.assertGreater(os.path.getsize(out), 500, ext)
        with open(os.path.join(self.base, "report.txt"), encoding="utf-8-sig") as f:
            txt = f.read()
        for e in res["contents"]:
            self.assertIn(e["name"], txt)
            self.assertIn(e["hashes"]["SHA-256"], txt)
        self.assertIn("Operatore di prova", txt)


class VersionTest(unittest.TestCase):
    def test_versione_coerente(self):
        with open(os.path.join(ROOT, "version_info.txt"), encoding="utf-8") as f:
            info = f.read()
        self.assertRegex(A.APP_VERSION, r"^\d+\.\d+\.\d+$")
        tup = "(%s, 0)" % ", ".join(A.APP_VERSION.split("."))
        self.assertIn("filevers=" + tup, info)
        self.assertIn("prodvers=" + tup, info)
        strings = re.findall(r"StringStruct\('(?:File|Product)Version', '([^']+)'\)", info)
        self.assertEqual(strings, [A.APP_VERSION + ".0"] * 2)
        self.assertIn("StringStruct('ProductName', '%s')" % A.APP_NAME, info)


if __name__ == "__main__":
    unittest.main()
