# Componenti di terze parti

L'eseguibile distribuito include, nella cartella `_internal`, i seguenti componenti open
source. Sono usati senza modifiche, come librerie.

| Componente | Uso | Licenza |
|---|---|---|
| [Python](https://www.python.org/) e libreria standard | Ambiente di esecuzione | PSF License 2.0 |
| [Tcl/Tk](https://www.tcl-lang.org/) | Interfaccia grafica | Tcl/Tk License (stile BSD) |
| [ReportLab](https://www.reportlab.com/opensource/) | Report in PDF | BSD 3-Clause |
| [Pillow](https://python-pillow.org/) | Dipendenza di ReportLab | MIT-CMU (HPND) |
| [py7zr](https://github.com/miurahr/py7zr) | Elenco del contenuto degli archivi 7z | LGPL-2.1-or-later |
| [PyInstaller](https://pyinstaller.org/) (bootloader) | Avvio dell'eseguibile | GPL-2.0-or-later con eccezione per il bootloader |

py7zr porta con sé alcune dipendenze (librerie di compressione e cifratura), tutte con
licenze open source. L'elenco esatto dipende dalla versione installata al momento della
compilazione e si ottiene con:

```bat
py -m pip install pip-licenses
py -m piplicenses --format=markdown
```

I componenti con licenza LGPL sono distribuiti come file separati nella cartella
`_internal` e possono essere sostituiti dall'utente con versioni proprie.
