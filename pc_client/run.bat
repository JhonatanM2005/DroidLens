@echo off
title DroidLens - Cliente PC
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual e instalando dependencias...
    python -m venv .venv
    call .venv\Scripts\pip.exe install -r requirements.txt
)

start "" .venv\Scripts\pythonw.exe main.py
exit
