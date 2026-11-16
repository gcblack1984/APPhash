@echo off
rem Crea la cartella dist\APPhash con APPhash.exe e le librerie affiancate
rem (modalita' "onedir": avvio molto piu' rapido del file unico).
rem Serve per le prove in locale: le release pubblicate sono compilate da GitHub Actions.
cd /d "%~dp0"

set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY (
  python --version >nul 2>nul && set PY=python
)
if not defined PY (
  echo.
  echo ERRORE: Python non trovato su questo computer.
  echo Installalo da https://www.python.org/downloads/ spuntando
  echo "Add python.exe to PATH" nella prima schermata, poi riavvia questo file.
  echo.
  pause
  exit /b 1
)
echo Uso: %PY%
%PY% --version

%PY% -m pip install --upgrade -r requirements-build.txt
if errorlevel 1 goto errore

%PY% -m PyInstaller --noconfirm --clean APPhash.spec
if errorlevel 1 goto errore

if not exist dist\APPhash\APPhash.exe goto errore
copy /y docs\Guida_APPhash.pdf dist\APPhash\ >nul
copy /y LICENSE dist\APPhash\LICENSE.txt >nul
copy /y THIRD_PARTY_LICENSES.md dist\APPhash\ >nul
echo.
echo Fatto: la cartella da distribuire e' dist\APPhash
pause
exit /b 0

:errore
echo.
echo ERRORE: l'eseguibile NON e' stato creato. Leggi i messaggi qui sopra.
pause
exit /b 1
