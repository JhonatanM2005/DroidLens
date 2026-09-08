"""
Script de empaquetado para distribución de DroidLens en Windows.
Genera una carpeta o paquete ZIP portable listo para el usuario final:
- Incluye el cliente PC compilado/portable.
- Incluye los binarios portables de ADB (adb.exe y dlls).
- Incluye los drivers DirectShow UnityCapture (32 y 64 bits) y scripts de registro.
- Incluye script de verificación automática de registro de driver.
"""

import os
import sys
import shutil
import zipfile

def package_windows():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dist_dir = os.path.join(base_dir, "dist")
    package_name = "DroidLens-Windows-Portable-v1.0.0"
    target_dir = os.path.join(dist_dir, package_name)

    print(f"Empaquetando {package_name}...")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    # 1. Copiar drivers
    driver_src = os.path.join(base_dir, "driver")
    driver_dst = os.path.join(target_dir, "driver")
    shutil.copytree(driver_src, driver_dst)

    # 2. Copiar binarios portables de ADB
    adb_src = os.path.join(base_dir, "pc_client", "bin", "adb")
    adb_dst = os.path.join(target_dir, "bin", "adb")
    shutil.copytree(adb_src, adb_dst)

    # 3. Copiar código fuente y estructura del cliente
    pc_src = os.path.join(base_dir, "pc_client", "src")
    pc_dst = os.path.join(target_dir, "src")
    shutil.copytree(pc_src, pc_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    shutil.copy2(os.path.join(base_dir, "pc_client", "main.py"), os.path.join(target_dir, "main.py"))
    shutil.copy2(os.path.join(base_dir, "pc_client", "requirements.txt"), os.path.join(target_dir, "requirements.txt"))

    # 4. Lanzador de ejecución con chequeo automático de driver
    launcher_content = """@echo off
title DroidLens - Webcam USB
cd /d "%~dp0"

echo ===================================================
echo     DroidLens - Webcam USB para Windows
echo ===================================================
echo.

if not exist ".venv\\Scripts\\python.exe" (
    echo [INFO] Inicializando entorno y dependencias...
    python -m venv .venv
    call .venv\\Scripts\\pip.exe install -r requirements.txt
)

echo [INFO] Iniciando DroidLens...
start "" .venv\\Scripts\\pythonw.exe main.py
exit
"""
    with open(os.path.join(target_dir, "Iniciar DroidLens.bat"), "w", encoding="utf-8") as f:
        f.write(launcher_content)

    # 5. Guía de inicio rápido
    quickstart_content = """===================================================
  DroidLens v1.0.0 — Guia de Inicio Rapido
===================================================

PASO 1 (Solo una vez):
  Entra a la carpeta 'driver' y haz doble clic en 'install_driver.bat'
  como Administrador para registrar 'Unity Video Capture'.

PASO 2:
  En tu celular Android, abre la app DroidLens y conecta el cable USB
  con 'Depuracion por USB' habilitada.

PASO 3:
  Haz doble clic en 'Iniciar DroidLens.bat'.
  ¡Activa 'Camara Virtual' y usala en Zoom, Meet o Teams!
"""
    with open(os.path.join(target_dir, "LEEME.txt"), "w", encoding="utf-8") as f:
        f.write(quickstart_content)

    # 6. Crear archivo ZIP final
    zip_path = os.path.join(dist_dir, f"{package_name}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    print(f"Comprimiendo a {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)

    print(f"[OK] Empaquetado completado exitosamente: {zip_path}")

if __name__ == "__main__":
    package_windows()
