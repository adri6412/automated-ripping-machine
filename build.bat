@echo off
rem Crea un eseguibile standalone in dist\AutoRipMachine\
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller.exe --noconfirm --windowed --name AutoRipMachine run.pyw
if exist tools xcopy /e /i /y tools dist\AutoRipMachine\tools >nul
echo.
echo Eseguibile pronto in dist\AutoRipMachine\AutoRipMachine.exe
