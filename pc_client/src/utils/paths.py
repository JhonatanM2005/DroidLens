"""
Gestor centralizado de rutas y recursos de DroidLens.
Compatible tanto con ejecución directa desde código fuente como
con ejecutables congelados con PyInstaller (--onedir / --onefile).
"""

import os
import sys
import shutil

def is_frozen() -> bool:
    """Retorna True si la aplicación se ejecuta compilada con PyInstaller."""
    return getattr(sys, "frozen", False)

def get_bundle_dir() -> str:
    """Directorio donde residen los binarios y recursos empaquetados."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # En desarrollo: raíz del proyecto o pc_client
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_user_data_dir() -> str:
    """
    Directorio para archivos persistentes del usuario (configuración, capturas).
    En modo ejecutable usa %LOCALAPPDATA%\\DroidLens.
    En desarrollo usa la carpeta local de pc_client.
    """
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        data_dir = os.path.join(local_app_data, "DroidLens")
    else:
        data_dir = get_bundle_dir()

    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_settings_file() -> str:
    """Ruta al archivo settings.json de persistencia."""
    return os.path.join(get_user_data_dir(), "settings.json")

def get_captures_dir() -> str:
    """Ruta al directorio donde se guardan los snapshots."""
    captures_dir = os.path.join(get_user_data_dir(), "captures")
    os.makedirs(captures_dir, exist_ok=True)
    return captures_dir

def find_adb_binary() -> str:
    """Localiza el binario de ADB en el bundle, en el PATH o en el SDK."""
    # 1. En el bundle (portable)
    bundle_adb = os.path.join(get_bundle_dir(), "bin", "adb", "adb.exe")
    if os.path.exists(bundle_adb):
        return bundle_adb

    # 2. PATH del sistema
    system_adb = shutil.which("adb")
    if system_adb:
        return system_adb

    # 3. Android SDK común
    local_sdk = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
    if os.path.exists(local_sdk):
        return local_sdk

    return ""
