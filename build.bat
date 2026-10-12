@echo off
rem Crea l'eseguibile in dist\AutoRipMachine\ e, se Inno Setup 6 e' installato,
rem anche l'installer dist\AutoRipMachine-Setup-<versione>.exe
cd /d "%~dp0"
set VERSION=%1
if "%VERSION%"=="" set VERSION=0.0.0-dev
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller.exe --noconfirm --windowed --name AutoRipMachine run.pyw
if errorlevel 1 exit /b 1
echo.
echo Eseguibile pronto in dist\AutoRipMachine\AutoRipMachine.exe
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
    "%ISCC%" /DMyAppVersion=%VERSION% installer\AutoRipMachine.iss
    echo Installer pronto in dist\AutoRipMachine-Setup-%VERSION%.exe
) else (
    echo Inno Setup 6 non trovato: installer non generato ^(https://jrsoftware.org/isdl.php^)
)
