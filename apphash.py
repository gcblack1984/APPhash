# -*- coding: utf-8 -*-
"""
APPhash - Calcolo delle impronte hash di file, cartelle e archivi compressi
con generazione di report (PDF, HTML, TXT).

Copyright (c) 2026 Giovanni Ciccarese - Licenza MIT (vedi file LICENSE).
"""

import datetime as _dt
import hashlib
import html
import os
import platform
import queue
import sys
import tarfile
import threading
import time
import zipfile
import zlib

APP_NAME = "APPhash"
APP_VERSION = "1.1.1"
APP_SUBTITLE = "Calcolo impronte hash di file, cartelle e archivi"
APP_AUTHOR = "Ciccarese Giovanni"
GUIDE_FILE = "Guida_APPhash.pdf"

CHUNK = 1024 * 1024  # lettura a blocchi da 1 MiB

# Colori
C_NAVY = "#12233f"
C_NAVY2 = "#1b3359"
C_ACCENT = "#2f80ed"
C_LIGHT = "#f4f6fa"
C_TEXT = "#1d2533"
C_MUTED = "#6b7688"
C_OK = "#1e8e3e"
C_KO = "#c5221f"


# --------------------------------------------------------------------------
#  MOTORE DI CALCOLO
# --------------------------------------------------------------------------
class _Crc32:
    """CRC32 con la stessa interfaccia degli oggetti hashlib."""

    def __init__(self):
        self._v = 0

    def update(self, data):
        self._v = zlib.crc32(data, self._v)

    def hexdigest(self):
        return "%08x" % (self._v & 0xFFFFFFFF)


# nome mostrato -> costruttore (l'ordine è quello di visualizzazione)
ALGOS = {
    "MD5": hashlib.md5,
    "SHA-1": hashlib.sha1,
    "SHA-256": hashlib.sha256,
    "SHA-384": hashlib.sha384,
    "SHA-512": hashlib.sha512,
    "SHA3-256": hashlib.sha3_256,
    "BLAKE2b": hashlib.blake2b,
    "CRC32": _Crc32,
}
DEFAULT_ALGOS = ("MD5", "SHA-1", "SHA-256")

ARCHIVE_EXT = (".zip", ".tar", ".tgz", ".tar.gz", ".tbz2", ".tar.bz2",
               ".txz", ".tar.xz", ".7z", ".rar")


class Cancelled(Exception):
    pass


def is_archive(path):
    return os.path.isfile(path) and path.lower().endswith(ARCHIVE_EXT)


def fmt_size(n):
    if n is None:
        return "-"
    byte = "{:,}".format(n).replace(",", ".")
    if n < 1024:
        return "%s byte" % byte
    val = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        val /= 1024.0
        if val < 1024 or unit == "TB":
            return "%s %s (%s byte)" % (("%.2f" % val).replace(".", ","), unit, byte)
    return byte


def fmt_size_short(n):
    if n is None:
        return "-"
    if n < 1024:
        return "%d byte" % n
    val = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        val /= 1024.0
        if val < 1024 or unit == "TB":
            return "%s %s" % (("%.2f" % val).replace(".", ","), unit)
    return str(n)


def fmt_dt(d):
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else "-"


class Engine:
    """Calcola gli hash di un file, di una cartella o di un archivio."""

    def __init__(self, algos, progress=None, cancel=None):
        self.algos = [a for a in ALGOS if a in algos]
        self.progress = progress
        self.cancel = cancel or threading.Event()
        self.done = 0
        self.total = 0
        self._last = 0.0

    # -- utilità ----------------------------------------------------------
    def _notify(self, label, force=False):
        if not self.progress:
            return
        now = time.time()
        if force or now - self._last >= 0.05:
            self._last = now
            self.progress(self.done, self.total, label)

    def _hash_stream(self, fobj, label):
        hs = {n: ALGOS[n]() for n in self.algos}
        while True:
            if self.cancel.is_set():
                raise Cancelled()
            block = fobj.read(CHUNK)
            if not block:
                break
            for h in hs.values():
                h.update(block)
            self.done += len(block)
            self._notify(label)
        return {n: h.hexdigest() for n, h in hs.items()}

    def _hash_file(self, path, label):
        with open(path, "rb") as f:
            return self._hash_stream(f, label)

    # -- punto d'ingresso -------------------------------------------------
    def analyze(self, path, recursive=True, hash_members=True):
        path = os.path.abspath(path)
        started = _dt.datetime.now()
        t0 = time.time()
        res = {
            "app": "%s %s" % (APP_NAME, APP_VERSION),
            "source": path,
            "name": os.path.basename(path.rstrip("\\/")) or path,
            "algos": list(self.algos),
            "started": started,
            "host": platform.node(),
            "recursive": recursive,
            "main": {},
            "main_error": None,
            "contents": [],
            "contents_note": None,
            "modified": None,
        }
        try:
            res["modified"] = _dt.datetime.fromtimestamp(os.path.getmtime(path))
        except OSError:
            pass

        if os.path.isdir(path):
            res["kind"] = "folder"
            res["kind_label"] = "Cartella"
            self._do_folder(path, recursive, res)
        elif is_archive(path):
            res["kind"] = "archive"
            res["kind_label"] = "Archivio compresso"
            self._do_archive(path, hash_members, res)
        else:
            res["kind"] = "file"
            res["kind_label"] = "File"
            res["total_size"] = os.path.getsize(path)
            self.total = res["total_size"]
            res["main"] = self._hash_file(path, res["name"])

        res["finished"] = _dt.datetime.now()
        res["elapsed"] = time.time() - t0
        self._notify("Completato", force=True)
        return res

    # -- cartella ---------------------------------------------------------
    def _do_folder(self, path, recursive, res):
        files = []
        for root, dirs, names in os.walk(path):
            dirs.sort(key=str.casefold)
            for n in names:
                full = os.path.join(root, n)
                rel = os.path.relpath(full, path)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = None
                files.append((rel, full, size))
            if not recursive:
                break
            if self.cancel.is_set():
                raise Cancelled()
        files.sort(key=lambda t: t[0].casefold())
        self.total = sum(s or 0 for _, _, s in files)
        res["total_size"] = self.total

        for rel, full, size in files:
            entry = {"name": rel, "size": size, "hashes": None, "error": None}
            try:
                entry["hashes"] = self._hash_file(full, rel)
            except Cancelled:
                raise
            except Exception as exc:  # file bloccato, permessi, ecc.
                entry["error"] = "non leggibile (%s)" % exc.__class__.__name__
            res["contents"].append(entry)

        # impronta complessiva: hash dell'elenco ordinato "hash  percorso"
        for algo in self.algos:
            h = ALGOS[algo]()
            for e in res["contents"]:
                val = e["hashes"][algo] if e["hashes"] else "ERRORE"
                line = "%s  %s\n" % (val, e["name"].replace("\\", "/"))
                h.update(line.encode("utf-8"))
            res["main"][algo] = h.hexdigest()
        if not recursive:
            res["contents_note"] = "Sottocartelle escluse dall'analisi."

    # -- archivio ---------------------------------------------------------
    def _do_archive(self, path, hash_members, res):
        low = path.lower()
        arch_size = os.path.getsize(path)
        res["total_size"] = arch_size
        self.total = arch_size
        res["main"] = self._hash_file(path, res["name"])

        try:
            if low.endswith(".zip"):
                self._zip_members(path, hash_members, res)
            elif low.endswith(".7z"):
                self._7z_members(path, res)
            elif low.endswith(".rar"):
                res["contents_note"] = ("Elenco del contenuto non disponibile "
                                        "per il formato RAR.")
            else:
                self._tar_members(path, hash_members, res)
        except Cancelled:
            raise
        except Exception as exc:
            res["contents_note"] = ("Impossibile leggere il contenuto "
                                    "dell'archivio: %s" % exc)

    def _zip_members(self, path, hash_members, res):
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if hash_members:
                self.total += sum(i.file_size for i in infos)
            for i in infos:
                name = i.filename
                if not i.flag_bits & 0x800:  # nome senza indicazione UTF-8
                    try:
                        name = name.encode("cp437").decode("utf-8")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                entry = {"name": name, "size": i.file_size,
                         "hashes": None, "error": None}
                if hash_members:
                    if i.flag_bits & 0x1:
                        entry["error"] = "protetto da password"
                        self.done += i.file_size
                    else:
                        try:
                            with zf.open(i) as f:
                                entry["hashes"] = self._hash_stream(f, name)
                        except Cancelled:
                            raise
                        except Exception as exc:
                            entry["error"] = "non leggibile (%s)" % exc.__class__.__name__
                res["contents"].append(entry)
        if not hash_members:
            res["contents_note"] = "Hash dei singoli file contenuti non richiesto."

    def _tar_members(self, path, hash_members, res):
        with tarfile.open(path, "r:*") as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            if hash_members:
                self.total += sum(m.size for m in members)
            for m in members:
                if self.cancel.is_set():
                    raise Cancelled()
                name = m.name[2:] if m.name.startswith("./") else m.name
                entry = {"name": name, "size": m.size,
                         "hashes": None, "error": None}
                if hash_members:
                    try:
                        f = tf.extractfile(m)
                        try:
                            entry["hashes"] = self._hash_stream(f, name)
                        finally:
                            f.close()
                    except Cancelled:
                        raise
                    except Exception as exc:
                        entry["error"] = "non leggibile (%s)" % exc.__class__.__name__
                res["contents"].append(entry)
        if not hash_members:
            res["contents_note"] = "Hash dei singoli file contenuti non richiesto."

    def _7z_members(self, path, res):
        try:
            import py7zr
        except ImportError:
            res["contents_note"] = ("Elenco del contenuto non disponibile: "
                                    "supporto 7z non installato.")
            return
        with py7zr.SevenZipFile(path, "r") as z:
            for info in z.list():
                if getattr(info, "is_directory", False):
                    continue
                res["contents"].append({
                    "name": info.filename,
                    "size": getattr(info, "uncompressed", None),
                    "hashes": None, "error": None})
        res["contents_note"] = ("Per gli archivi 7z vengono elencati nomi e "
                                "dimensioni; l'hash è calcolato sull'archivio.")


# --------------------------------------------------------------------------
#  REPORT
# --------------------------------------------------------------------------
def _main_title(res):
    if res["kind"] == "folder":
        return "Impronta complessiva della cartella"
    if res["kind"] == "archive":
        return "Hash dell'archivio"
    return "Hash del file"


FOLDER_NOTE = ("L'impronta complessiva è calcolata sull'elenco ordinato dei "
               "file (hash e percorso relativo di ciascuno): cambia se un "
               "qualsiasi file viene modificato, aggiunto, rimosso o rinominato.")


def _info_rows(res):
    rows = [
        ("Elemento analizzato", res["source"]),
        ("Tipo", res["kind_label"]),
        ("Dimensione", fmt_size(res.get("total_size"))),
    ]
    if res["kind"] != "file":
        rows.append(("File contenuti", str(len(res["contents"]))))
    rows += [
        ("Ultima modifica", fmt_dt(res.get("modified"))),
        ("Algoritmi", ", ".join(res["algos"])),
        ("Inizio calcolo", fmt_dt(res["started"])),
        ("Fine calcolo", fmt_dt(res["finished"])),
        ("Durata", ("%.2f secondi" % res["elapsed"]).replace(".", ",")),
        ("Postazione", res.get("host") or "-"),
    ]
    if res.get("operator"):
        rows.append(("Operatore", res["operator"]))
    if res.get("reference"):
        rows.append(("Riferimento / note", res["reference"]))
    return rows


def _contents_title(res):
    return "Elenco dei file contenuti (%d)" % len(res["contents"])


def report_txt(res, out):
    L = []
    bar = "=" * 78
    L += [bar, "%s - REPORT IMPRONTE HASH" % APP_NAME.upper(), bar, ""]
    for k, v in _info_rows(res):
        L.append("%-22s: %s" % (k, v))
    L += ["", "-" * 78, _main_title(res).upper(), "-" * 78]
    for a in res["algos"]:
        L.append("%-9s: %s" % (a, res["main"].get(a, "-")))
    if res["kind"] == "folder":
        L += ["", FOLDER_NOTE]
    if res["kind"] != "file":
        L += ["", "-" * 78, _contents_title(res).upper(), "-" * 78]
        if res.get("contents_note"):
            L += [res["contents_note"], ""]
        for n, e in enumerate(res["contents"], 1):
            L.append("%d. %s" % (n, e["name"]))
            L.append("   Dimensione: %s" % fmt_size(e["size"]))
            if e["error"]:
                L.append("   ATTENZIONE: %s" % e["error"])
            elif e["hashes"]:
                for a in res["algos"]:
                    L.append("   %-9s: %s" % (a, e["hashes"][a]))
            L.append("")
    L += ["", bar, "Report generato da %s il %s" % (res["app"], fmt_dt(_dt.datetime.now())), bar]
    with open(out, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(L) + "\n")


def report_html(res, out):
    e = html.escape
    P = []
    P.append("""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<title>Report APPhash - %s</title><style>
body{font-family:Segoe UI,Arial,sans-serif;color:#1d2533;margin:0;background:#f4f6fa}
.wrap{max-width:980px;margin:0 auto;background:#fff;padding:0 0 30px}
header{background:#12233f;color:#fff;padding:22px 32px}
header h1{margin:0;font-size:24px}header p{margin:4px 0 0;color:#b9c6dc;font-size:13px}
section{padding:6px 32px}h2{font-size:16px;color:#12233f;border-bottom:2px solid #2f80ed;padding-bottom:4px;margin-top:26px}
table{border-collapse:collapse;width:100%%;font-size:13px}
td,th{padding:5px 8px;border-bottom:1px solid #e3e7ee;text-align:left;vertical-align:top}
td.k{width:190px;color:#6b7688}
.h{font-family:Consolas,monospace;font-size:12px;word-break:break-all}
.f{margin:10px 0;border:1px solid #e3e7ee;border-radius:6px;padding:8px 12px;page-break-inside:avoid}
.f b{word-break:break-all}.f .s{color:#6b7688;font-size:12px}
.err{color:#c5221f}.note{color:#6b7688;font-size:12.5px}
footer{padding:14px 32px;color:#6b7688;font-size:12px}
@media print{body{background:#fff}}
</style></head><body><div class="wrap">""" % e(res["name"]))
    P.append("<header><h1># %s &ndash; Report impronte hash</h1><p>%s</p></header>"
             % (APP_NAME, e(res["name"])))
    P.append("<section><h2>Dati dell'analisi</h2><table>")
    for k, v in _info_rows(res):
        P.append("<tr><td class='k'>%s</td><td>%s</td></tr>" % (e(k), e(v)))
    P.append("</table></section>")
    P.append("<section><h2>%s</h2><table>" % e(_main_title(res)))
    for a in res["algos"]:
        P.append("<tr><td class='k'>%s</td><td class='h'>%s</td></tr>"
                 % (a, res["main"].get(a, "-")))
    P.append("</table>")
    if res["kind"] == "folder":
        P.append("<p class='note'>%s</p>" % e(FOLDER_NOTE))
    P.append("</section>")
    if res["kind"] != "file":
        P.append("<section><h2>%s</h2>" % e(_contents_title(res)))
        if res.get("contents_note"):
            P.append("<p class='note'>%s</p>" % e(res["contents_note"]))
        for n, it in enumerate(res["contents"], 1):
            P.append("<div class='f'><b>%d. %s</b> <span class='s'>&middot; %s</span>"
                     % (n, e(it["name"]), e(fmt_size(it["size"]))))
            if it["error"]:
                P.append("<div class='err'>Attenzione: %s</div>" % e(it["error"]))
            elif it["hashes"]:
                P.append("<table>")
                for a in res["algos"]:
                    P.append("<tr><td class='k' style='width:80px'>%s</td>"
                             "<td class='h'>%s</td></tr>" % (a, it["hashes"][a]))
                P.append("</table>")
            P.append("</div>")
        P.append("</section>")
    P.append("<footer>Report generato da %s il %s</footer></div></body></html>"
             % (e(res["app"]), fmt_dt(_dt.datetime.now())))
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(P))


def pdf_available():
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def _pdf_fonts():
    """Usa i font di sistema (per i nomi con caratteri speciali) se presenti."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fdir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        pdfmetrics.registerFont(TTFont("AH", os.path.join(fdir, "arial.ttf")))
        pdfmetrics.registerFont(TTFont("AH-B", os.path.join(fdir, "arialbd.ttf")))
        pdfmetrics.registerFont(TTFont("AH-M", os.path.join(fdir, "consola.ttf")))
        return "AH", "AH-B", "AH-M"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Courier"


def report_pdf(res, out):
    from xml.sax.saxutils import escape as x
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    F, FB, FM = _pdf_fonts()
    navy = colors.HexColor(C_NAVY)
    accent = colors.HexColor(C_ACCENT)
    muted = colors.HexColor(C_MUTED)
    line = colors.HexColor("#e3e7ee")

    st_h2 = ParagraphStyle("h2", fontName=FB, fontSize=11.5, textColor=navy,
                           spaceBefore=12, spaceAfter=5)
    st_k = ParagraphStyle("k", fontName=F, fontSize=8.5, textColor=muted, leading=11)
    st_v = ParagraphStyle("v", fontName=F, fontSize=8.5, leading=11, wordWrap="CJK")
    st_m = ParagraphStyle("m", fontName=FM, fontSize=7.5, leading=9.5, wordWrap="CJK")
    st_n = ParagraphStyle("n", fontName=FB, fontSize=8.5, leading=11, wordWrap="CJK")
    st_note = ParagraphStyle("note", fontName=F, fontSize=8, textColor=muted, leading=10.5)
    st_err = ParagraphStyle("err", fontName=F, fontSize=8.5,
                            textColor=colors.HexColor(C_KO), leading=11)

    W = A4[0] - 36 * mm
    generated = fmt_dt(_dt.datetime.now())

    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(navy)
        canvas.rect(0, h - 24 * mm, w, 24 * mm, stroke=0, fill=1)
        # icona cancelletto
        canvas.setFillColor(accent)
        canvas.roundRect(18 * mm, h - 19 * mm, 13 * mm, 13 * mm, 2.2 * mm, stroke=0, fill=1)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(1.6)
        bx, by, s = 18 * mm, h - 19 * mm, 13 * mm
        canvas.line(bx + s * .36, by + s * .2, bx + s * .44, by + s * .8)
        canvas.line(bx + s * .56, by + s * .2, bx + s * .64, by + s * .8)
        canvas.line(bx + s * .2, by + s * .62, bx + s * .8, by + s * .62)
        canvas.line(bx + s * .2, by + s * .38, bx + s * .8, by + s * .38)
        canvas.setFillColor(colors.white)
        canvas.setFont(FB, 15)
        canvas.drawString(36 * mm, h - 12.5 * mm, "%s - Report impronte hash" % APP_NAME)
        canvas.setFont(F, 9)
        canvas.setFillColor(colors.HexColor("#b9c6dc"))
        name = res["name"]
        if len(name) > 90:
            name = name[:87] + "..."
        canvas.drawString(36 * mm, h - 18 * mm, name)
        canvas.setFillColor(muted)
        canvas.setFont(F, 7.5)
        canvas.drawString(18 * mm, 10 * mm,
                          "Report generato da %s il %s" % (res["app"], generated))
        canvas.drawRightString(w - 18 * mm, 10 * mm, "Pagina %d" % doc.page)
        canvas.restoreState()

    def hash_table(hashes, kw=22 * mm):
        data = [[Paragraph(a, st_k), Paragraph(hashes.get(a, "-"), st_m)]
                for a in res["algos"]]
        t = Table(data, colWidths=[kw, W - kw - 6 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    story = [Paragraph("Dati dell'analisi", st_h2)]
    info = [[Paragraph(x(k), st_k), Paragraph(x(v), st_v)] for k, v in _info_rows(res)]
    t = Table(info, colWidths=[40 * mm, W - 40 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    story.append(Paragraph(x(_main_title(res)), st_h2))
    box = Table([[hash_table(res["main"])]], colWidths=[W])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, accent),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f7ff")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(box)
    if res["kind"] == "folder":
        story += [Spacer(1, 4), Paragraph(x(FOLDER_NOTE), st_note)]

    if res["kind"] != "file":
        story.append(Paragraph(x(_contents_title(res)), st_h2))
        if res.get("contents_note"):
            story += [Paragraph(x(res["contents_note"]), st_note), Spacer(1, 4)]
        for n, it in enumerate(res["contents"], 1):
            rows = [[Paragraph("%d. %s" % (n, x(it["name"])), st_n)],
                    [Paragraph("Dimensione: %s" % fmt_size(it["size"]), st_k)]]
            if it["error"]:
                rows.append([Paragraph("Attenzione: %s" % x(it["error"]), st_err)])
            elif it["hashes"]:
                rows.append([hash_table(it["hashes"], 18 * mm)])
            ft = Table(rows, colWidths=[W])
            ft.setStyle(TableStyle([
                ("LINEBELOW", (0, -1), (-1, -1), 0.4, line),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(KeepTogether(ft))

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=30 * mm, bottomMargin=17 * mm,
                            title="Report APPhash - %s" % res["name"],
                            author=res.get("operator") or APP_NAME)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def save_report(res, out):
    ext = os.path.splitext(out)[1].lower()
    if ext == ".pdf":
        report_pdf(res, out)
    elif ext in (".html", ".htm"):
        report_html(res, out)
    else:
        report_txt(res, out)


# --------------------------------------------------------------------------
#  INTERFACCIA GRAFICA
# --------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """Percorso di una risorsa, sia nell'eseguibile sia eseguendo dai sorgenti."""
    base = getattr(sys, "_MEIPASS", app_dir())
    for sub in ("", "assets", "docs"):
        p = os.path.join(base, sub, name)
        if os.path.exists(p):
            return p
    return os.path.join(base, name)


def draw_hash(canvas, x, y, size, color="white", width=4):
    """Disegna un cancelletto dentro il quadrato (x, y, size)."""
    s = size
    kw = dict(fill=color, width=width, capstyle="round")
    canvas.create_line(x + s * .42, y + s * .80, x + s * .50, y + s * .20, **kw)
    canvas.create_line(x + s * .60, y + s * .80, x + s * .68, y + s * .20, **kw)
    canvas.create_line(x + s * .22, y + s * .40, x + s * .84, y + s * .40, **kw)
    canvas.create_line(x + s * .18, y + s * .62, x + s * .80, y + s * .62, **kw)


def center(win, w, h, dy=0):
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2),
                                  max(0, (sh - h) // 2 + dy)))


def set_icon(win):
    try:
        win.iconbitmap(resource_path("apphash.ico"))
        return
    except Exception:
        pass
    try:
        import tkinter as tk
        img = tk.PhotoImage(file=resource_path("apphash.png"))
        win.iconphoto(True, img)
        win._icon_ref = img
    except Exception:
        pass


def ui_scale(win):
    """Fattore di scala dello schermo (1.0 = 100%, 1.5 = 150%...)."""
    try:
        return max(1.0, float(win.winfo_fpixels("1i")) / 96.0)
    except Exception:
        return 1.0


def pick_dropped(paths):
    """Sceglie l'elemento da analizzare fra quelli trascinati.

    Restituisce (percorso, messaggio per la riga di stato) oppure (None, None).
    """
    paths = [os.path.normpath(p) for p in paths if p and p.strip()]
    if not paths:
        return None, None
    first = paths[0]
    if len(paths) == 1:
        return first, ("Elemento selezionato con il trascinamento. "
                       "Premi «Calcola hash» per iniziare.")
    return first, ("Hai trascinato %d elementi: viene considerato solo il primo "
                   "(«%s»). Per analizzarne più insieme, raccoglili in una cartella."
                   % (len(paths), os.path.basename(first.rstrip("\\/")) or first))


class WinFileDrop:
    """Riceve file e cartelle trascinati da Esplora file (solo Windows).

    Usa direttamente le funzioni di sistema DragAcceptFiles / WM_DROPFILES:
    nessuna libreria aggiuntiva. Su altri sistemi non fa nulla (ok = False).
    """
    WM_DROPFILES = 0x0233
    GWLP_WNDPROC = -4
    POLL_MS = 100

    def __init__(self, widget, callback):
        self.ok = False
        self.widget = widget
        self.callback = callback
        self.pending = []  # elenchi di percorsi ricevuti e non ancora elaborati
        if sys.platform != "win32":
            return
        try:
            self._install()
            self.ok = True
        except Exception:
            self.ok = False
            return
        self.widget.after(self.POLL_MS, self._poll)

    def _poll(self):
        """Consegna i percorsi ricevuti, dal normale ciclo degli eventi di Tk."""
        try:
            while self.pending:
                self.callback(self.pending.pop(0))
        finally:
            try:
                self.widget.after(self.POLL_MS, self._poll)
            except Exception:  # finestra chiusa
                pass

    def _install(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        set_proc = user32.SetWindowLongPtrW
        set_proc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        set_proc.restype = ctypes.c_void_p
        call_proc = user32.CallWindowProcW
        call_proc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM]
        call_proc.restype = LRESULT
        query = shell32.DragQueryFileW
        query.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        query.restype = wintypes.UINT
        finish = shell32.DragFinish
        finish.argtypes = [ctypes.c_void_p]
        finish.restype = None
        accept = shell32.DragAcceptFiles
        accept.argtypes = [wintypes.HWND, wintypes.BOOL]
        accept.restype = None

        hwnd = self.widget.winfo_id()

        # ATTENZIONE: questa procedura viene chiamata da Windows mentre Tk sta
        # elaborando i messaggi. Qui dentro non si deve chiamare NESSUNA funzione
        # di tkinter (nemmeno after): si altera lo stato interno di Python e il
        # programma si chiude. I percorsi vengono solo messi da parte e li
        # consegna _poll, dal normale ciclo degli eventi.
        def wndproc(h, msg, wparam, lparam):
            if msg == self.WM_DROPFILES:
                try:
                    paths = []
                    hdrop = ctypes.c_void_p(wparam)
                    try:
                        for i in range(query(hdrop, 0xFFFFFFFF, None, 0)):
                            n = query(hdrop, i, None, 0) + 1
                            buf = ctypes.create_unicode_buffer(n)
                            query(hdrop, i, buf, n)
                            paths.append(buf.value)
                    finally:
                        finish(hdrop)
                    if paths:
                        self.pending.append(paths)
                except Exception:
                    pass
                return 0
            return call_proc(self._old, h, msg, wparam, lparam)

        self._proc = WNDPROC(wndproc)  # riferimento da conservare
        self._old = set_proc(hwnd, self.GWLP_WNDPROC,
                             ctypes.cast(self._proc, ctypes.c_void_p).value)
        if not self._old:
            raise OSError(ctypes.get_last_error(), "SetWindowLongPtrW")
        accept(hwnd, True)
        self.hwnd = hwnd


class Splash:
    W, H = 540, 330
    DURATION = 3.2  # secondi (minimo garantito: 3)

    STEPS = [
        (0.00, "Avvio in corso…"),
        (0.18, "Caricamento algoritmi di hash…"),
        (0.42, "Caricamento modulo report…"),
        (0.68, "Preparazione interfaccia…"),
        (0.92, "Quasi pronto…"),
    ]

    def __init__(self, root, on_load, on_done):
        import tkinter as tk
        self.root = root
        self.on_load = on_load
        self.on_done = on_done
        self.loaded = False
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
        except Exception:
            pass
        S = ui_scale(root)

        def p(v):
            return int(round(v * S))

        def font(px, *style):
            return ("Segoe UI", -p(px)) + style  # dimensione in pixel

        W, H = p(self.W), p(self.H)
        center(self.top, W, H)

        c = tk.Canvas(self.top, width=W, height=H, bg=C_NAVY,
                      highlightthickness=1, highlightbackground=C_ACCENT)
        c.pack(fill="both", expand=True)
        self.c = c
        # icona
        isz = p(84)
        ix, iy = W // 2 - isz // 2, p(34)
        c.create_rectangle(ix, iy, ix + isz, iy + isz, fill=C_ACCENT, outline="")
        draw_hash(c, ix, iy, isz, "white", p(8))
        # testi
        c.create_text(W // 2, p(158), text=APP_NAME, fill="white",
                      font=font(40, "bold"))
        c.create_text(W // 2, p(196), text=APP_SUBTITLE, fill="#b9c6dc",
                      font=font(14))
        # barra di caricamento
        self.bx0, self.bx1, self.by, self.bh = p(60), W - p(60), p(236), p(10)
        c.create_rectangle(self.bx0, self.by, self.bx1, self.by + self.bh,
                           fill=C_NAVY2, outline="")
        self.bar = c.create_rectangle(self.bx0, self.by, self.bx0,
                                      self.by + self.bh, fill=C_ACCENT, outline="")
        self.msg = c.create_text(self.bx0, self.by + p(26), anchor="w",
                                 text=self.STEPS[0][1], fill="#b9c6dc",
                                 font=font(12))
        self.pct = c.create_text(self.bx1, self.by + p(26), anchor="e", text="0%",
                                 fill="white", font=font(12, "bold"))
        c.create_text(p(16), H - p(16), anchor="w", text=APP_AUTHOR,
                      fill="#8fa1bf", font=font(11))
        c.create_text(W - p(16), H - p(16), anchor="e",
                      text="Versione %s" % APP_VERSION, fill="#8fa1bf",
                      font=font(11))

        self.top.update()  # disegna subito lo splash
        self.t0 = time.time()
        self.top.after(30, self._tick)

    def _tick(self):
        frac = min(1.0, (time.time() - self.t0) / self.DURATION)
        if frac >= 0.45 and not self.loaded:
            # caricamento reale dell'applicazione mentre lo splash è visibile
            self.loaded = True
            self.c.itemconfigure(self.msg, text=self.STEPS[2][1])
            self.top.update()
            try:
                self.on_load()
            except Exception as exc:
                from tkinter import messagebox
                self.top.destroy()
                messagebox.showerror(APP_NAME, "Errore di avvio:\n\n%s" % exc)
                self.root.destroy()
                return
        text = self.STEPS[0][1]
        for lim, label in self.STEPS:
            if frac >= lim:
                text = label
        self.c.itemconfigure(self.msg, text=text)
        self.c.itemconfigure(self.pct, text="%d%%" % int(frac * 100))
        self.c.coords(self.bar, self.bx0, self.by,
                      self.bx0 + (self.bx1 - self.bx0) * frac, self.by + self.bh)
        if frac >= 1.0:
            self.top.after(150, self._finish)
        else:
            self.top.after(30, self._tick)

    def _finish(self):
        self.top.destroy()
        self.on_done()


class MainWindow:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.result = None
        self.rows = {}  # id riga -> (nome, hashes)

        self.S = S = ui_scale(root)
        root.title("%s %s" % (APP_NAME, APP_VERSION))
        root.configure(bg=C_LIGHT)
        root.minsize(int(820 * S), int(600 * S))
        set_icon(root)

        style = ttk.Style(root)
        style.configure("TLabelframe", background=C_LIGHT)
        style.configure("TLabelframe.Label", background=C_LIGHT, foreground=C_NAVY,
                        font=("Segoe UI", 9, "bold"))
        style.configure("TFrame", background=C_LIGHT)
        style.configure("TLabel", background=C_LIGHT, foreground=C_TEXT)
        style.configure("TCheckbutton", background=C_LIGHT)
        style.configure("Muted.TLabel", foreground=C_MUTED, background=C_LIGHT)
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.configure("Treeview", rowheight=int(22 * S))

        # --- intestazione ---
        head = tk.Frame(root, bg=C_NAVY, height=int(64 * S))
        head.pack(fill="x")
        head.pack_propagate(False)
        isz = int(44 * S)
        ic = tk.Canvas(head, width=isz, height=isz, bg=C_ACCENT, highlightthickness=0)
        ic.pack(side="left", padx=(16, 12))
        draw_hash(ic, 0, 0, isz, "white", max(3, int(4 * S)))
        box = tk.Frame(head, bg=C_NAVY)
        box.pack(side="left")
        tk.Label(box, text=APP_NAME, bg=C_NAVY, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(box, text=APP_SUBTITLE, bg=C_NAVY, fg="#b9c6dc",
                 font=("Segoe UI", 9)).pack(anchor="w")
        ttk.Button(head, text="Guida", command=self.open_guide).pack(
            side="right", padx=16)

        body = ttk.Frame(root, padding=(14, 10, 14, 10))
        body.pack(fill="both", expand=True)

        # --- 1. origine ---
        f1 = ttk.LabelFrame(body, text=" 1. Cosa vuoi analizzare ", padding=10)
        f1.pack(fill="x")
        self.path_var = tk.StringVar()
        ent = ttk.Entry(f1, textvariable=self.path_var)
        ent.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ent.bind("<Return>", lambda e: self._path_changed())
        ent.bind("<FocusOut>", lambda e: self._path_changed())
        ttk.Button(f1, text="Scegli file…", command=self.pick_file).grid(row=0, column=1)
        ttk.Button(f1, text="Scegli cartella…", command=self.pick_folder).grid(
            row=0, column=2, padx=(6, 0))
        self.kind_var = tk.StringVar(value="Seleziona un file, un archivio compresso o una cartella.")
        ttk.Label(f1, textvariable=self.kind_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        f1.columnconfigure(0, weight=1)

        # --- 2. algoritmi + 3. dati report ---
        mid = ttk.Frame(body)
        mid.pack(fill="x", pady=(8, 0))
        f2 = ttk.LabelFrame(mid, text=" 2. Algoritmi ", padding=10)
        f2.pack(side="left", fill="both", expand=True)
        self.algo_vars = {}
        for i, name in enumerate(ALGOS):
            v = tk.BooleanVar(value=name in DEFAULT_ALGOS)
            self.algo_vars[name] = v
            ttk.Checkbutton(f2, text=name, variable=v).grid(
                row=i // 4, column=i % 4, sticky="w", padx=(0, 18), pady=2)
        self.rec_var = tk.BooleanVar(value=True)
        self.mem_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f2, text="Includi le sottocartelle",
                        variable=self.rec_var).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(f2, text="Calcola l'hash anche dei file dentro l'archivio",
                        variable=self.mem_var).grid(
            row=3, column=0, columnspan=4, sticky="w")

        f3 = ttk.LabelFrame(mid, text=" 3. Dati per il report (facoltativi) ", padding=10)
        f3.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.op_var = tk.StringVar()
        self.ref_var = tk.StringVar()
        ttk.Label(f3, text="Operatore").grid(row=0, column=0, sticky="w")
        ttk.Entry(f3, textvariable=self.op_var).grid(row=1, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(f3, text="Riferimento / note").grid(row=2, column=0, sticky="w")
        ttk.Entry(f3, textvariable=self.ref_var).grid(row=3, column=0, sticky="ew", pady=(2, 0))
        f3.columnconfigure(0, weight=1)

        # --- pulsanti ---
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(10, 4))
        self.btn_run = ttk.Button(bar, text="#  Calcola hash", style="Big.TButton",
                                  command=self.start)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="Annulla", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        self.btn_save = ttk.Button(bar, text="Salva report…", style="Big.TButton",
                                   command=self.save, state="disabled")
        self.btn_save.pack(side="right")
        self.btn_copy = ttk.Button(bar, text="Copia riga selezionata",
                                   command=self.copy_row, state="disabled")
        self.btn_copy.pack(side="right", padx=6)

        self.prog = ttk.Progressbar(body, maximum=1000)
        self.prog.pack(fill="x")
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel").pack(
            anchor="w", pady=(2, 6))

        # --- confronto (in basso, sempre visibile) ---
        self.cmp_lbl = tk.Label(body, text="", bg=C_LIGHT, anchor="w",
                                font=("Segoe UI", 9, "bold"))
        self.cmp_lbl.pack(side="bottom", fill="x")
        cmp_ = ttk.Frame(body)
        cmp_.pack(side="bottom", fill="x", pady=(8, 2))
        ttk.Label(cmp_, text="Confronta con un hash atteso:").pack(side="left")
        self.cmp_var = tk.StringVar()
        ce = ttk.Entry(cmp_, textvariable=self.cmp_var, font=("Consolas", 9))
        ce.pack(side="left", fill="x", expand=True, padx=8)
        ce.bind("<Return>", lambda e: self.compare())
        ttk.Button(cmp_, text="Confronta", command=self.compare).pack(side="left")

        # --- risultati ---
        tf = ttk.Frame(body)
        tf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tf, selectmode="browse")
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree.tag_configure("err", foreground=C_KO)
        self.tree.tag_configure("main", font=("Segoe UI", 9, "bold"))
        self._setup_columns(list(DEFAULT_ALGOS))
        # invito al trascinamento, mostrato sulla tabella vuota
        self.drop_ok = False
        self.drop_hint = tk.Label(
            self.tree, text="Trascina qui un file, una cartella o un archivio compresso",
            bg="white", fg=C_MUTED, font=("Segoe UI", 11))

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        center(root, min(int(1000 * S), sw - 60), min(int(740 * S), sh - 110), dy=-20)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- tabella ----------------------------------------------------------
    def _setup_columns(self, algos):
        widths = {"MD5": 250, "SHA-1": 300, "SHA-256": 470, "SHA-384": 690,
                  "SHA-512": 910, "SHA3-256": 470, "BLAKE2b": 910, "CRC32": 90}
        cols = ["size"] + algos
        self.tree.configure(columns=cols)
        self.tree.heading("#0", text="Nome")
        S = self.S
        self.tree.column("#0", width=int(330 * S), minwidth=160, stretch=False)
        self.tree.heading("size", text="Dimensione")
        self.tree.column("size", width=int(100 * S), anchor="e", stretch=False)
        for a in algos:
            self.tree.heading(a, text=a)
            self.tree.column(a, width=int(widths.get(a, 300) * S), stretch=False)

    # -- selezione origine ------------------------------------------------
    def pick_file(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(title="Scegli il file o l'archivio da analizzare")
        if p:
            self.path_var.set(os.path.normpath(p))
            self._path_changed()

    def pick_folder(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(title="Scegli la cartella da analizzare")
        if p:
            self.path_var.set(os.path.normpath(p))
            self._path_changed()

    # -- trascinamento ---------------------------------------------------
    def enable_drop(self):
        """Attiva il trascinamento sulla finestra (chiamato quando è visibile)."""
        self.dropper = WinFileDrop(self.root, self.on_drop)
        self.drop_ok = self.dropper.ok
        if self.drop_ok:
            self._path_changed()
            self._show_drop_hint(True)

    def _show_drop_hint(self, on):
        if on and self.drop_ok and not self.tree.get_children():
            self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.drop_hint.place_forget()

    def on_drop(self, paths):
        if self.worker and self.worker.is_alive():
            self.status_var.set("Calcolo in corso: attendi la fine o premi «Annulla» "
                                "prima di trascinare un altro elemento.")
            return
        path, msg = pick_dropped(paths)
        if not path:
            return
        self.path_var.set(path)
        self._path_changed()
        self.status_var.set(msg)
        try:
            self.root.lift()
        except Exception:
            pass

    def _path_changed(self):
        p = self.path_var.get().strip().strip('"')
        if not p:
            if self.drop_ok:
                self.kind_var.set("Seleziona un file, un archivio compresso o una cartella, "
                                  "oppure trascinalo in un punto qualsiasi della finestra.")
            else:
                self.kind_var.set("Seleziona un file, un archivio compresso o una cartella.")
        elif os.path.isdir(p):
            self.kind_var.set("Tipo rilevato: cartella – nel report sarà incluso "
                              "l'elenco di tutti i file contenuti.")
        elif is_archive(p):
            self.kind_var.set("Tipo rilevato: archivio compresso – nel report sarà "
                              "incluso l'elenco di tutti i file contenuti.")
        elif os.path.isfile(p):
            self.kind_var.set("Tipo rilevato: file singolo (%s)."
                              % fmt_size_short(os.path.getsize(p)))
        else:
            self.kind_var.set("Percorso non trovato.")

    # -- calcolo ----------------------------------------------------------
    def start(self):
        from tkinter import messagebox
        path = self.path_var.get().strip().strip('"')
        if not path or not os.path.exists(path):
            messagebox.showwarning(APP_NAME, "Seleziona un file o una cartella esistente.")
            return
        algos = [a for a, v in self.algo_vars.items() if v.get()]
        if not algos:
            messagebox.showwarning(APP_NAME, "Seleziona almeno un algoritmo.")
            return
        self.result = None
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        self._show_drop_hint(False)
        self._setup_columns(algos)
        self.cmp_lbl.configure(text="")
        self.cancel.clear()
        self._busy(True)
        self.status_var.set("Analisi in corso…")
        self.prog.configure(value=0)

        eng = Engine(algos, progress=lambda d, t, n: self.q.put(("p", d, t, n)),
                     cancel=self.cancel)
        rec, mem = self.rec_var.get(), self.mem_var.get()

        def run():
            try:
                self.q.put(("done", eng.analyze(path, rec, mem)))
            except Cancelled:
                self.q.put(("cancel",))
            except Exception as exc:
                self.q.put(("error", "%s: %s" % (exc.__class__.__name__, exc)))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.root.after(60, self._poll)

    def stop(self):
        self.cancel.set()
        self.status_var.set("Annullamento in corso…")

    def _busy(self, on):
        self.btn_run.configure(state="disabled" if on else "normal")
        self.btn_stop.configure(state="normal" if on else "disabled")
        if on:
            self.btn_save.configure(state="disabled")
            self.btn_copy.configure(state="disabled")

    def _poll(self):
        from tkinter import messagebox
        last = None
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "p":
                    last = m
                    continue
                self._busy(False)
                if m[0] == "done":
                    self._show(m[1])
                elif m[0] == "cancel":
                    self.prog.configure(value=0)
                    self.status_var.set("Operazione annullata.")
                    self._show_drop_hint(True)
                else:
                    self.prog.configure(value=0)
                    self.status_var.set("Errore durante il calcolo.")
                    self._show_drop_hint(True)
                    messagebox.showerror(APP_NAME, "Si è verificato un errore:\n\n%s" % m[1])
                return
        except queue.Empty:
            pass
        if last:
            _, done, total, name = last
            frac = (done / total) if total else 0
            self.prog.configure(value=int(min(1.0, frac) * 1000))
            if len(name) > 70:
                name = "…" + name[-69:]
            self.status_var.set("%d%%  –  %s di %s  –  %s" % (
                int(frac * 100), fmt_size_short(done), fmt_size_short(total), name))
        self.root.after(60, self._poll)

    def _show(self, res):
        self.result = res
        algos = res["algos"]

        def vals(size, hashes, error):
            if error:
                return [fmt_size_short(size), error] + [""] * (len(algos) - 1)
            if not hashes:
                return [fmt_size_short(size)] + [""] * len(algos)
            return [fmt_size_short(size)] + [hashes[a] for a in algos]

        label = res["name"]
        if res["kind"] == "folder":
            label += "  (impronta complessiva)"
        top = self.tree.insert("", "end", text=label, open=True, tags=("main",),
                               values=vals(res.get("total_size"), res["main"], None))
        self.rows[top] = (res["name"], res["main"])
        for it in res["contents"]:
            iid = self.tree.insert(top, "end", text=it["name"],
                                   tags=("err",) if it["error"] else (),
                                   values=vals(it["size"], it["hashes"], it["error"]))
            self.rows[iid] = (it["name"], it["hashes"] or {})
        self.tree.selection_set(top)

        self.prog.configure(value=1000)
        nerr = sum(1 for it in res["contents"] if it["error"])
        txt = "Completato in %s secondi." % ("%.2f" % res["elapsed"]).replace(".", ",")
        if res["kind"] != "file":
            txt += "  File contenuti: %d." % len(res["contents"])
        if nerr:
            txt += "  File non leggibili: %d." % nerr
        if res.get("contents_note"):
            txt += "  " + res["contents_note"]
        self.status_var.set(txt)
        self.btn_save.configure(state="normal")
        self.btn_copy.configure(state="normal")
        if self.cmp_var.get().strip():
            self.compare()

    # -- azioni sui risultati --------------------------------------------
    def copy_row(self):
        sel = self.tree.selection()
        if not sel or sel[0] not in self.rows:
            return
        name, hashes = self.rows[sel[0]]
        lines = [name] + ["%s: %s" % (a, h) for a, h in hashes.items()]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.status_var.set("Hash copiati negli appunti.")

    def compare(self):
        want = "".join(self.cmp_var.get().split()).lower()
        if not want:
            self.cmp_lbl.configure(text="")
            return
        if not self.result:
            self.cmp_lbl.configure(text="Calcola prima gli hash, poi confronta.",
                                   fg=C_MUTED)
            return
        for iid, (name, hashes) in self.rows.items():
            for a, h in hashes.items():
                if h.lower() == want:
                    self.cmp_lbl.configure(
                        text="✔  CORRISPONDE  –  %s di «%s»" % (a, name), fg=C_OK)
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    return
        self.cmp_lbl.configure(text="✘  NESSUNA CORRISPONDENZA con gli hash calcolati",
                               fg=C_KO)

    def save(self):
        from tkinter import filedialog, messagebox
        if not self.result:
            return
        res = dict(self.result)
        res["operator"] = self.op_var.get().strip()
        res["reference"] = self.ref_var.get().strip()
        types = [("Documento HTML", "*.html"), ("File di testo", "*.txt")]
        ext = ".html"
        if pdf_available():
            types.insert(0, ("Documento PDF", "*.pdf"))
            ext = ".pdf"
        base = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in res["name"])
        name = "Report_APPhash_%s_%s" % (base[:60], res["started"].strftime("%Y%m%d_%H%M%S"))
        out = filedialog.asksaveasfilename(
            title="Salva il report", defaultextension=ext, filetypes=types,
            initialfile=name, initialdir=os.path.dirname(res["source"]))
        if not out:
            return
        try:
            save_report(res, out)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Impossibile salvare il report:\n\n%s" % exc)
            return
        self.status_var.set("Report salvato: %s" % out)
        if messagebox.askyesno(APP_NAME, "Report salvato.\n\nVuoi aprirlo adesso?"):
            self._open(out)

    def open_guide(self):
        from tkinter import messagebox
        for p in (os.path.join(app_dir(), GUIDE_FILE), resource_path(GUIDE_FILE)):
            if os.path.isfile(p):
                self._open(p)
                return
        messagebox.showinfo(APP_NAME, "Guida non trovata.\n\nIl file «%s» deve trovarsi "
                            "nella stessa cartella del programma." % GUIDE_FILE)

    @staticmethod
    def _open(path):
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def on_close(self):
        self.cancel.set()
        self.root.destroy()


def main():
    import tkinter as tk
    try:  # testo nitido sugli schermi ad alta risoluzione
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()
    state = {}

    def load():
        pdf_available()            # carica in anticipo il modulo dei report
        state["win"] = MainWindow(root)

    def done():
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update_idletasks()
        state["win"].enable_drop()

    Splash(root, load, done)
    root.mainloop()


if __name__ == "__main__":
    main()
