@echo off
rem Avvia Automated Ripping Machine (crea l'ambiente virtuale al primo avvio)
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo Creazione ambiente Python...
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe run.pyw %*
