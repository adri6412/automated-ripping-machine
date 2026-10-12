<#
.SYNOPSIS
    Scarica e installa i programmi esterni usati da Automated Ripping Machine.

.DESCRIPTION
    - cyanrip  -> <InstallDir>\tools\cyanrip\cyanrip.exe   (GitHub cyanreg/cyanrip)
    - MakeMKV  -> installazione di sistema (winget o installer ufficiale da makemkv.com)
                  + chiave beta gratuita dal forum ufficiale, se non c'e' una licenza

    Senza switch installa tutto. Puo' essere rieseguito per aggiornare i programmi.

.EXAMPLE
    install-deps.ps1 -InstallDir "C:\Program Files\AutoRipMachine" -Cyanrip -MakeMKV
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$Cyanrip,
    [switch]$MakeMKV,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest e' lentissimo con la barra attiva
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not ($Cyanrip -or $MakeMKV)) {
    $Cyanrip = $MakeMKV = $true
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
if (-not (Test-Writable $Tools) -or ($MakeMKV -and -not (Test-Admin))) {
    if (-not (Test-Admin)) {
        Write-Host "Richiesti i permessi di amministratore, riavvio elevato..."
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                     '-InstallDir', "`"$InstallDir`"")
        foreach ($sw in 'Cyanrip', 'MakeMKV', 'NoPause') {
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

# --- MakeMKV (decifra e rippa DVD / Blu-ray / UHD) --------------------------------------------
function Find-MakeMKVCon {
    foreach ($dir in "${env:ProgramFiles(x86)}\MakeMKV", "$env:ProgramFiles\MakeMKV") {
        foreach ($exe in 'makemkvcon64.exe', 'makemkvcon.exe') {
            $p = Join-Path $dir $exe
            if (Test-Path $p) { return $p }
        }
    }
    return $null
}

if ($MakeMKV) {
    Invoke-Component 'MakeMKV' {
        $how = $null
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            & $winget.Source install --id GuinpinSoft.MakeMKV -e --silent `
                --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
            # 0 = installato, -1978335189 = gia' installato/nessun aggiornamento
            if (($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) -and (Find-MakeMKVCon)) {
                $how = 'winget'
            } else {
                Write-Host "    winget ha restituito $LASTEXITCODE, provo con l'installer ufficiale"
            }
        }
        if (-not $how) {
            $page = (Invoke-WebRequest -Uri 'https://www.makemkv.com/download/' -UserAgent $UserAgent `
                -UseBasicParsing).Content
            $m = [regex]::Match($page, 'Setup_MakeMKV_v[\d.]+\.exe')
            if (-not $m.Success) { throw 'link di download non trovato su makemkv.com' }
            $setup = Join-Path $Temp $m.Value
            Get-File "https://www.makemkv.com/download/$($m.Value)" $setup
            $p = Start-Process -FilePath $setup -ArgumentList '/S' -Wait -PassThru
            if ($p.ExitCode -ne 0) { throw "installer terminato con codice $($p.ExitCode)" }
            $how = $m.Value
        }
        $exe = Find-MakeMKVCon
        if (-not $exe) { throw 'makemkvcon non trovato dopo l''installazione' }

        # Chiave: la beta gratuita viene aggiornata ogni mese sul forum ufficiale.
        $regPath = 'HKCU:\Software\MakeMKV'
        $current = (Get-ItemProperty -Path $regPath -Name app_Key -ErrorAction SilentlyContinue).app_Key
        $keyInfo = 'licenza registrata'
        if (-not $current -or $current.StartsWith('T-')) {
            try {
                $forum = (Invoke-WebRequest -Uri 'https://forum.makemkv.com/forum/viewtopic.php?t=1053' `
                    -UserAgent $UserAgent -UseBasicParsing).Content
                $k = [regex]::Match($forum, '<code>\s*(T-[A-Za-z0-9@_\-]{20,})\s*</code>')
                if (-not $k.Success) { throw 'chiave non trovata' }
                New-Item -Path $regPath -Force | Out-Null
                Set-ItemProperty -Path $regPath -Name app_Key -Value $k.Groups[1].Value
                $keyInfo = 'chiave beta impostata'
            } catch {
                $keyInfo = "chiave beta NON impostata ($($_.Exception.Message)): inseriscila dalle impostazioni dell'app"
            }
        }
        "$how -> $exe ($keyInfo)"
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
    Write-Host "'Aggiorna programmi esterni'." -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host "Premi Invio per chiudere" | Out-Null }
    exit 1
}
if (-not $NoPause) { Start-Sleep -Seconds 3 }
exit 0
