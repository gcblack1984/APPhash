# Crea il pacchetto MSIX di APPhash per il Microsoft Store.
#
# Prerequisiti: cartella dist\APPhash gia' compilata (PyInstaller) e Windows SDK
# (makeappx.exe e makepri.exe; su GitHub Actions sono gia' installati).
#
# Esempio:
#   .\packaging\msix\crea_msix.ps1 -Version 1.1.0
#
# Il pacchetto prodotto NON e' firmato: lo firma il Microsoft Store al momento
# della pubblicazione. Per provarlo sul proprio PC vedi la cartella "layout"
# (Add-AppxPackage -Register, con la Modalita' sviluppatore attiva).

param(
    [Parameter(Mandatory = $true)] [string] $Version,
    [string] $IdentityName = "GiovanniCiccarese.APPhash",
    [string] $Publisher = "CN=APPhash-Test",
    [string] $PublisherDisplayName = "Giovanni Ciccarese",
    [string] $Dist = "dist\APPhash",
    [string] $OutDir = "dist\msix"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-SdkTool([string] $name) {
    $root = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    $tool = Get-ChildItem $root -Recurse -Filter $name -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\bin\\(\d+\.\d+\.\d+\.\d+)\\x64\\' } |
        Sort-Object { [version]([regex]::Match($_.FullName, '\\bin\\(\d+\.\d+\.\d+\.\d+)\\').Groups[1].Value) } -Descending |
        Select-Object -First 1
    if (-not $tool) { throw "$name non trovato: installare Windows SDK." }
    return $tool.FullName
}

function Invoke-Tool([string] $exe, [string[]] $toolArgs) {
    & $exe @toolArgs
    if ($LASTEXITCODE -ne 0) { throw "$([IO.Path]::GetFileName($exe)) terminato con errore $LASTEXITCODE" }
}

# Lo Store richiede quattro numeri con l'ultimo uguale a 0 (es. 1.1.0 -> 1.1.0.0)
$v4 = "$Version.0"
if ($v4 -notmatch '^\d+\.\d+\.\d+\.0$') { throw "Versione non valida: $Version (atteso X.Y.Z)" }
if (-not (Test-Path (Join-Path $Dist "APPhash.exe"))) { throw "APPhash.exe non trovato in $Dist" }

$layout = Join-Path $OutDir "layout"
$priRoot = Join-Path $OutDir "pri"
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $layout, $priRoot | Out-Null

# 1. contenuto del pacchetto: programma + immagini + manifesto
Copy-Item (Join-Path $Dist "*") $layout -Recurse
Copy-Item (Join-Path $here "Assets") (Join-Path $layout "Assets") -Recurse

$esc = { param($s) [Security.SecurityElement]::Escape($s) }
$manifest = [IO.File]::ReadAllText((Join-Path $here "AppxManifest.xml"))
$manifest = $manifest.Replace("__IDENTITY_NAME__", (& $esc $IdentityName))
$manifest = $manifest.Replace("__PUBLISHER__", (& $esc $Publisher))
$manifest = $manifest.Replace("__PUBLISHER_DISPLAY_NAME__", (& $esc $PublisherDisplayName))
$manifest = $manifest.Replace("__VERSION__", $v4)
$utf8 = New-Object Text.UTF8Encoding $false
[IO.File]::WriteAllText((Join-Path $layout "AppxManifest.xml"), $manifest, $utf8)

# 2. resources.pri: indice delle immagini nelle varie risoluzioni
#    (calcolato su una copia con le sole immagini, per non indicizzare _internal)
Copy-Item (Join-Path $here "Assets") (Join-Path $priRoot "Assets") -Recurse
Copy-Item (Join-Path $layout "AppxManifest.xml") $priRoot
$makepri = Find-SdkTool "makepri.exe"
$priConfig = Join-Path $OutDir "priconfig.xml"
Invoke-Tool $makepri @("createconfig", "/cf", $priConfig, "/dq", "it-IT", "/pv", "10.0.0", "/o")
Invoke-Tool $makepri @("new", "/pr", $priRoot, "/cf", $priConfig,
    "/mn", (Join-Path $priRoot "AppxManifest.xml"), "/of", (Join-Path $layout "resources.pri"), "/o")

# 3. pacchetto
$makeappx = Find-SdkTool "makeappx.exe"
$msix = Join-Path $OutDir "APPhash-$Version-x64.msix"
Invoke-Tool $makeappx @("pack", "/d", $layout, "/p", $msix, "/o")

Remove-Item $priRoot -Recurse -Force
Remove-Item $priConfig -Force
Write-Host "Pacchetto creato: $msix"
Write-Host "Identita': $IdentityName  |  $Publisher  |  $PublisherDisplayName  |  $v4"
