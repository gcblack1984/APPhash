# -*- coding: utf-8 -*-
"""Genera le immagini del pacchetto MSIX (Microsoft Store) dall'icona a cancelletto.

    py packaging/msix/genera_icone.py

Le immagini generate sono gia' presenti nel repository: serve rieseguirlo solo se
cambia l'icona.
"""
import os

from PIL import Image, ImageDraw

BLUE = "#2f80ed"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Assets")


def icon(size, ss=4):
    """Quadrato blu arrotondato con il cancelletto bianco, sfondo trasparente."""
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * .2), fill=BLUE)
    w = max(1, int(S * .085))

    def ln(a, b):
        d.line([(a[0] * S, a[1] * S), (b[0] * S, b[1] * S)], fill="white", width=w)
        for p in (a, b):
            d.ellipse([p[0] * S - w / 2, p[1] * S - w / 2,
                       p[0] * S + w / 2, p[1] * S + w / 2], fill="white")

    ln((.40, .80), (.48, .20))
    ln((.58, .80), (.66, .20))
    ln((.24, .40), (.82, .40))
    ln((.18, .62), (.76, .62))
    return im.resize((size, size), Image.LANCZOS)


def tile(w, h, scale):
    """Riquadro trasparente con l'icona centrata."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    s = int(min(w, h) * scale)
    im.alpha_composite(icon(s), ((w - s) // 2, (h - s) // 2))
    return im


def save(im, name):
    im.save(os.path.join(OUT, name))


def main():
    os.makedirs(OUT, exist_ok=True)
    # logo del pacchetto
    save(icon(50), "StoreLogo.png")
    save(icon(100), "StoreLogo.scale-200.png")
    # icona dell'app (menu Start, barra delle applicazioni)
    save(icon(44), "Square44x44Logo.png")
    save(icon(88), "Square44x44Logo.scale-200.png")
    for t in (16, 24, 32, 48, 256):
        save(icon(t), "Square44x44Logo.targetsize-%d.png" % t)
        save(icon(t), "Square44x44Logo.targetsize-%d_altform-unplated.png" % t)
    # riquadri del menu Start
    save(tile(150, 150, .62), "Square150x150Logo.png")
    save(tile(300, 300, .62), "Square150x150Logo.scale-200.png")
    save(tile(310, 150, .62), "Wide310x150Logo.png")
    save(tile(620, 300, .62), "Wide310x150Logo.scale-200.png")


if __name__ == "__main__":
    main()
