@echo off
title DroidLens - Webcam USB
cd /d "%~dp0"

echo ===================================================
echo     DroidLens - Webcam USB para Windows
echo ===================================================
echo.

if not exist "pc_client\.venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual e instalando dependencias...
    python -m venv pc_client\.venv
    call pc_client\.venv\Scripts\pip.exe install -r pc_client\requirements.txt
)

echo [INFO] Iniciando DroidLens...
start "" pc_client\.venv\Scripts\pythonw.exe pc_client\main.py
exit
