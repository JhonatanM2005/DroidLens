"""
Script de compilación y empaquetado para distribución en Windows.
Etapa 1: Congela la aplicación PC con PyInstaller en modo --onedir (dist/DroidLens/).
Etapa 2: Si Inno Setup está disponible (ISCC), compila el instalador DroidLens-Setup.exe.
"""

import os
import sys
import shutil
import subprocess
import zipfile

def find_inno_setup() -> str:
    """Busca el compilador de Inno Setup (ISCC.exe) en las rutas habituales."""
    candidates = [
        shutil.which("ISCC"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""

def build_distribution():
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dist_dir = os.path.join(repo_dir, "dist")
    spec_file = os.path.join(repo_dir, "pc_client", "droidlens.spec")
    iss_file = os.path.join(repo_dir, "installer", "droidlens.iss")

    print("===================================================")
    print("      DroidLens - Pipeline de Empaquetado Windows   ")
    print("===================================================")

    # 1. Compilar con PyInstaller en modo onedir
    print("\n[Etapa 1/2] Compilando con PyInstaller (modo --onedir)...")
    cmd_pyinstaller = [
        sys.executable, "-m", "PyInstaller",
        spec_file,
        "--distpath", dist_dir,
        "--workpath", os.path.join(repo_dir, "build", "pyinstaller"),
        "--noconfirm"
    ]

    try:
        subprocess.run(cmd_pyinstaller, check=True)
        print("[OK] PyInstaller finalizado: dist/DroidLens/DroidLens.exe creado.")
    except Exception as e:
        print(f"[ERROR] Falló la compilación con PyInstaller: {e}")
        return False

    # Copiar scripts de drivers dentro de la carpeta portable para comodidad
    app_dist_dir = os.path.join(dist_dir, "DroidLens")
    driver_dist = os.path.join(app_dist_dir, "driver")
    if os.path.exists(os.path.join(repo_dir, "driver")) and not os.path.exists(driver_dist):
        shutil.copytree(os.path.join(repo_dir, "driver"), driver_dist)

    # Crear ZIP de la versión portable
    zip_path = os.path.join(dist_dir, "DroidLens-Windows-Portable-v1.0.0.zip")
    print(f"\nGenerando archivo ZIP portable en {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(app_dist_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir)
                zipf.write(full_path, rel_path)
    print(f"[OK] ZIP portable generado con éxito.")

    # 2. Compilar con Inno Setup si está instalado
    print("\n[Etapa 2/2] Verificando Inno Setup para instalador ejecutable...")
    iscc = find_inno_setup()
    if iscc:
        print(f"Inno Setup encontrado en: {iscc}")
        try:
            subprocess.run([iscc, iss_file], check=True)
            print("[OK] Instalador DroidLens-Setup-v1.0.0.exe generado en dist/")
        except Exception as e:
            print(f"[AVISO] No se pudo compilar con Inno Setup: {e}")
    else:
        print("[AVISO] Inno Setup (ISCC.exe) no está instalado en el sistema.")
        print("  Puedes descargar Inno Setup gratis desde: https://jrsoftware.org/isdl.php")
        print("  El ejecutable portable dist/DroidLens/DroidLens.exe y el ZIP están listos para usarse.")

    return True

if __name__ == "__main__":
    build_distribution()
