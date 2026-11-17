# -*- coding: utf-8 -*-
"""Controlli sul pacchetto MSIX per il Microsoft Store."""

import os
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSIX = os.path.join(ROOT, "packaging", "msix")
NS = {
    "f": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
}


def manifest():
    with open(os.path.join(MSIX, "AppxManifest.xml"), encoding="utf-8") as f:
        text = f.read()
    text = (text.replace("__IDENTITY_NAME__", "GiovanniCiccarese.APPhash")
                .replace("__PUBLISHER__", "CN=APPhash-Test")
                .replace("__PUBLISHER_DISPLAY_NAME__", "Giovanni Ciccarese")
                .replace("__VERSION__", "1.1.0.0"))
    return text, ET.fromstring(text)


class ManifestTest(unittest.TestCase):
    def test_segnaposto_sostituiti(self):
        text, _ = manifest()
        self.assertNotRegex(text, r"__[A-Z_]+__")

    def test_struttura(self):
        _, root = manifest()
        app = root.find("f:Applications/f:Application", NS)
        self.assertEqual(app.get("Executable"), "APPhash.exe")
        self.assertEqual(app.get("EntryPoint"), "Windows.FullTrustApplication")
        caps = [c.get("Name") for c in root.find("f:Capabilities", NS)]
        self.assertEqual(caps, ["runFullTrust"])  # nessun accesso a rete o dati personali
        self.assertEqual(root.find("f:Resources/f:Resource", NS).get("Language"), "it-IT")

    def test_immagini_presenti(self):
        _, root = manifest()
        ve = root.find("f:Applications/f:Application/uap:VisualElements", NS)
        refs = [root.find("f:Properties/f:Logo", NS).text,
                ve.get("Square150x150Logo"), ve.get("Square44x44Logo"),
                ve.find("uap:DefaultTile", NS).get("Wide310x150Logo")]
        for ref in refs:
            base = os.path.join(MSIX, *ref.split("\\"))
            self.assertTrue(os.path.isfile(base), ref)
            stem, ext = os.path.splitext(base)
            self.assertTrue(os.path.isfile(stem + ".scale-200" + ext), ref + " (scale-200)")

    def test_dimensioni_immagini(self):
        from PIL import Image
        expected = {
            "StoreLogo.png": (50, 50), "StoreLogo.scale-200.png": (100, 100),
            "Square44x44Logo.png": (44, 44), "Square44x44Logo.scale-200.png": (88, 88),
            "Square150x150Logo.png": (150, 150), "Square150x150Logo.scale-200.png": (300, 300),
            "Wide310x150Logo.png": (310, 150), "Wide310x150Logo.scale-200.png": (620, 300),
        }
        for t in (16, 24, 32, 48, 256):
            expected["Square44x44Logo.targetsize-%d.png" % t] = (t, t)
            expected["Square44x44Logo.targetsize-%d_altform-unplated.png" % t] = (t, t)
        assets = os.path.join(MSIX, "Assets")
        self.assertEqual(sorted(os.listdir(assets)), sorted(expected))
        for name, size in expected.items():
            with Image.open(os.path.join(assets, name)) as im:
                self.assertEqual(im.size, size, name)

    def test_versione_store(self):
        import sys
        sys.path.insert(0, ROOT)
        import apphash
        # lo Store vuole X.Y.Z.0: crea_msix.ps1 aggiunge ".0" ad APP_VERSION
        self.assertRegex(apphash.APP_VERSION + ".0", r"^\d+\.\d+\.\d+\.0$")


if __name__ == "__main__":
    unittest.main()
