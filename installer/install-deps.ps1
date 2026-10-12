<#
.SYNOPSIS
    Scarica e installa i programmi esterni usati da Automated Ripping Machine.

.DESCRIPTION
    - cyanrip     -> <InstallDir>\tools\cyanrip\cyanrip.exe   (GitHub cyanreg/cyanrip)
    - ffmpeg      -> <InstallDir>\tools\ffmpeg\...\ffmpeg.exe (build GPL BtbN, con libdvdnav)
    - MKVToolNix  -> <InstallDir>\tools\mkvtoolnix\...        (zip portable ufficiale)
    - XReveal     -> installazione di sistema (winget o installer ufficiale)

    Senza switch installa tutto. Puo' essere rieseguito per aggiornare i programmi.

.EXAMPLE
    install-deps.ps1 -InstallDir "C:\Program Files\AutoRipMachine" -Cyanrip -FFmpeg
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$Cyanrip,
    [switch]$FFmpeg,
    [switch]$MKVToolNix,
    [switch]$XReveal,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest e' lentissimo con la barra attiva
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not ($Cyanrip -or $FFmpeg -or $MKVToolNix -or $XReveal)) {
    $Cyanrip = $FFmpeg = $MKVToolNix = $XReveal = $true
}

# --- Elevazione: la cartella in Program Files richiede i diritti di amministratore ----------
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-Writable([string]$dir) {
    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $probe = Join-Path $dir ".write-test"
        Set-Content -Path $probe -Value "" -ErrorAction Stop
        Remove-Item $probe -Force
        return $true
    } catch { return $false }
}

$Tools = Join-Path $InstallDir 'tools'
if (-not (Test-Writable $Tools) -or ($XReveal -and -not (Test-Admin))) {
    if (-not (Test-Admin)) {
        Write-Host "Richiesti i permessi di amministratore, riavvio elevato..."
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                     '-InstallDir', "`"$InstallDir`"")
        foreach ($sw in 'Cyanrip', 'FFmpeg', 'MKVToolNix', 'XReveal', 'NoPause') {
            if ((Get-Variable $sw).Value) { $argList += "-$sw" }
        }
        $p = Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait -PassThru
        exit $p.ExitCode
    }
}

$Temp = Join-Path ([IO.Path]::GetTempPath()) ("arm-deps-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
$UserAgent = 'AutoRipMachine-Installer'
$Results = [ordered]@{}

# --- Helpers ----------------------------------------------------------------------------------
function Write-Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Get-File([string]$url, [string]$dest) {
    Write-Host "    scarico $url"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --retry 3 --retry-delay 2 -A $UserAgent -o $dest $url
        if ($LASTEXITCODE -ne 0) { throw "download non riuscito ($url)" }
    } else {
        Invoke-WebRequest -Uri $url -OutFile $dest -UserAgent $UserAgent -UseBasicParsing
    }
    if (-not (Test-Path $dest) -or (Get-Item $dest).Length -eq 0) { throw "file scaricato vuoto ($url)" }
}

function Get-GitHubLatest([string]$repo) {
    Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ 'User-Agent' = $UserAgent; 'Accept' = 'application/vnd.github+json' }
}

function Reset-Dir([string]$dir) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

function Expand-Zip([string]$zip, [string]$dest) {
    Write-Host "    estraggo in $dest"
    Reset-Dir $dest
    Expand-Archive -Path $zip -DestinationPath $dest -Force
}

function Find-Exe([string]$root, [string]$name) {
    Get-ChildItem -Path $root -Recurse -Filter $name -File -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

function Invoke-Component([string]$name, [scriptblock]$body) {
    Write-Step $name
    try {
        $info = & $body
        $Results[$name] = "OK  $info"
        Write-Host "    OK $info" -ForegroundColor Green
    } catch {
        $Results[$name] = "ERRORE  $($_.Exception.Message)"
        Write-Host "    ERRORE: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# --- cyanrip ----------------------------------------------------------------------------------
if ($Cyanrip) {
    Invoke-Component 'cyanrip' {
        $url = 'https://github.com/cyanreg/cyanrip/releases/download/v0.9.3.1/cyanrip-win64.exe'
        $version = 'v0.9.3.1'
        try {
            $rel = Get-GitHubLatest 'cyanreg/cyanrip'
            $asset = $rel.assets | Where-Object { $_.name -match '^cyanrip.*win64.*\.(exe|zip)$' } |
                Select-Object -First 1
            if ($asset) { $url = $asset.browser_download_url; $version = $rel.tag_name }
        } catch { Write-Host "    API GitHub non raggiungibile, uso $version" }
        $dir = Join-Path $Tools 'cyanrip'
        if ($url.EndsWith('.zip')) {
            $zip = Join-Path $Temp 'cyanrip.zip'
            Get-File $url $zip
            Expand-Zip $zip $dir
            $exe = Find-Exe $dir 'cyanrip*.exe'
            if ($exe -and (Split-Path -Leaf $exe) -ne 'cyanrip.exe') {
                Copy-Item $exe (Join-Path (Split-Path $exe) 'cyanrip.exe')
            }
        } else {
            Reset-Dir $dir
            Get-File $url (Join-Path $dir 'cyanrip.exe')
        }
        $exe = Find-Exe $dir 'cyanrip.exe'
        if (-not $exe) { throw 'cyanrip.exe non trovato dopo il download' }
        "$version -> $exe"
    }
}

# --- ffmpeg (BtbN GPL: include libdvdread/libdvdnav per il demuxer dvdvideo) ------------------
if ($FFmpeg) {
    Invoke-Component 'ffmpeg' {
        $url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
        try {
            $rel = Get-GitHubLatest 'BtbN/FFmpeg-Builds'
            # Preferisce l'ultimo ramo stabile (es. ffmpeg-n7.1-latest-win64-gpl-7.1.zip)
            $stable = $rel.assets |
                Where-Object { $_.name -match '^ffmpeg-n(\d+)\.(\d+).*-latest-win64-gpl-[\d.]+\.zip$' } |
                Sort-Object { [int]($_.name -replace '^ffmpeg-n(\d+)\.(\d+).*$', '$1') * 100 +
                              [int]($_.name -replace '^ffmpeg-n(\d+)\.(\d+).*$', '$2') } -Descending |
                Select-Object -First 1
            if ($stable) { $url = $stable.browser_download_url }
        } catch { Write-Host "    API GitHub non raggiungibile, uso la build master" }
        $zip = Join-Path $Temp 'ffmpeg.zip'
        Get-File $url $zip
        $dir = Join-Path $Tools 'ffmpeg'
        Expand-Zip $zip $dir
        $exe = Find-Exe $dir 'ffmpeg.exe'
        if (-not $exe) { throw 'ffmpeg.exe non trovato nello zip' }
        $demuxers = & $exe -hide_banner -demuxers 2>&1 | Out-String
        if ($demuxers -notmatch 'dvdvideo') { throw 'questa build di ffmpeg non contiene il demuxer dvdvideo' }
        (Split-Path -Leaf $url) + " -> $exe"
    }
}

# --- MKVToolNix (zip portable ufficiale) ------------------------------------------------------
if ($MKVToolNix) {
    Invoke-Component 'MKVToolNix' {
        $base = 'https://mkvtoolnix.download/windows/releases/'
        $listing = (Invoke-WebRequest -Uri $base -UserAgent $UserAgent -UseBasicParsing).Content
        $versions = [regex]::Matches($listing, 'href="\./(\d+(?:\.\d+)+)/"') |
            ForEach-Object { $_.Groups[1].Value } | Sort-Object { [version]$_ } -Descending
        $zip = Join-Path $Temp 'mkvtoolnix.zip'
        $done = $null
        foreach ($v in ($versions | Select-Object -First 3)) {
            # La cartella piu' recente puo' essere ancora vuota durante una pubblicazione.
            try { Get-File "$base$v/mkvtoolnix-64-bit-$v.zip" $zip; $done = $v; break } catch { }
        }
        if (-not $done) { throw 'impossibile scaricare MKVToolNix' }
        $dir = Join-Path $Tools 'mkvtoolnix'
        Expand-Zip $zip $dir
        $exe = Find-Exe $dir 'mkvmerge.exe'
        if (-not $exe) { throw 'mkvmerge.exe non trovato nello zip' }
        "$done -> $exe"
    }
}

# --- XReveal (installazione di sistema) -------------------------------------------------------
if ($XReveal) {
    Invoke-Component 'XReveal' {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            & $winget.Source install --id XrevealTeam.Xreveal -e --silent `
                --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
            # 0 = installato, -1978335189 = gia' installato/nessun aggiornamento
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) { return 'installato con winget' }
            Write-Host "    winget ha restituito $LASTEXITCODE, provo con l'installer ufficiale"
        }
        $page = (Invoke-WebRequest -Uri 'https://www.xreveal.com/' -UserAgent $UserAgent -UseBasicParsing).Content
        $m = [regex]::Match($page, 'https://download\.xreveal\.com/xreveal_[\d.]+(?:_x64)?\.exe')
        if (-not $m.Success) { throw 'link di download non trovato su xreveal.com' }
        $setup = Join-Path $Temp (Split-Path -Leaf $m.Value)
        Get-File $m.Value $setup
        $p = Start-Process -FilePath $setup -ArgumentList '/s' -Wait -PassThru
        if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "installer terminato con codice $($p.ExitCode)" }
        $note = if ($p.ExitCode -eq 3010) { ' (richiede il riavvio)' } else { '' }
        (Split-Path -Leaf $m.Value) + $note
    }
}

# --- Riepilogo --------------------------------------------------------------------------------
Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Riepilogo" -ForegroundColor Cyan
foreach ($k in $Results.Keys) { Write-Host ("  {0,-11} {1}" -f $k, $Results[$k]) }
$failed = @($Results.Values | Where-Object { $_ -like 'ERRORE*' }).Count
if ($failed -gt 0) {
    Write-Host ""
    Write-Host "$failed componenti non installati. Puoi riprovare dal menu Start:" -ForegroundColor Yellow
    Write-Host "'Automated Ripping Machine - Aggiorna programmi esterni'." -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host "Premi Invio per chiudere" | Out-Null }
    exit 1
}
if (-not $NoPause) { Start-Sleep -Seconds 3 }
exit 0
