"""
Módulo de gestión de ADB (Android Debug Bridge) para DroidLens.
Se encarga de:
1. Localizar el ejecutable portable de adb.exe.
2. Detectar celulares Android conectados por cable USB.
3. Configurar y limpiar reglas de reenvío de puertos (adb forward).
"""

import os
import subprocess
import shutil
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger("DroidLens.ADB")

class ADBManager:
    def __init__(self, custom_adb_path: Optional[str] = None):
        self.adb_path = custom_adb_path or self._find_adb()
        if not self.adb_path:
            logger.warning("No se encontro un ejecutable de ADB. El modo USB automatico requerira ADB en el PATH.")
        else:
            logger.info(f"ADB localizado en: {self.adb_path}")

    @staticmethod
    def _find_adb() -> Optional[str]:
        """Busca adb en la carpeta portable de pc_client/bin/adb o en el PATH del sistema."""
        # 1. Carpeta portable relativa a este archivo
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        portable_adb = os.path.join(base_dir, "bin", "adb", "adb.exe")
        if os.path.exists(portable_adb):
            return portable_adb

        # 2. PATH del sistema
        system_adb = shutil.which("adb")
        if system_adb:
            return system_adb

        # 3. Ubicaciones comunes en AppData
        local_sdk_adb = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
        if os.path.exists(local_sdk_adb):
            return local_sdk_adb

        return None

    def _run_command(self, args: List[str], timeout: float = 5.0) -> Tuple[int, str, str]:
        """Ejecuta un comando de adb de forma segura."""
        if not self.adb_path:
            return -1, "", "ADB no esta disponible."

        cmd = [self.adb_path] + args
        try:
            startupinfo = None
            if os.name == 'nt':
                # Evitar que se abra una ventana negra de consola en Windows
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='replace'
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout esperando respuesta de ADB."
        except Exception as e:
            return -1, "", str(e)

    def is_available(self) -> bool:
        """Comprueba si el binario de ADB responde correctamente."""
        code, out, _ = self._run_command(["version"])
        return code == 0 and "Android Debug Bridge" in out

    def list_devices(self) -> List[Dict[str, str]]:
        """
        Retorna la lista de dispositivos conectados por USB con sus estados.
        Formato: [{'serial': '...', 'state': 'device|unauthorized|offline', 'model': '...'}]
        """
        code, out, _ = self._run_command(["devices", "-l"])
        if code != 0 or not out:
            return []

        devices = []
        lines = out.splitlines()
        for line in lines[1:]:  # Omitir cabecera 'List of devices attached'
            line = line.strip()
            if not line or line.startswith("*"):
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]  # 'device', 'unauthorized', 'offline'
                model = "Android Device"
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.replace("model:", "").replace("_", " ")
                        break

                devices.append({
                    "serial": serial,
                    "state": state,
                    "model": model,
                    "raw": line
                })

        return devices

    def setup_port_forward(self, local_port: int = 8080, remote_port: int = 8080) -> bool:
        """
        Configura la regla de reenvio 'adb forward tcp:LOCAL tcp:REMOTE'.
        Permite a la PC conectar a localhost:LOCAL y hablar con la app Android.
        """
        code, out, err = self._run_command(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"])
        if code == 0:
            logger.info(f"Reenvio de puertos activo: PC (tcp:{local_port}) -> Android (tcp:{remote_port})")
            return True
        else:
            logger.error(f"Fallo al configurar reenvio de puertos: {err or out}")
            return False

    def remove_port_forward(self, local_port: int = 8080) -> bool:
        """Elimina la regla de reenvio para el puerto especificado."""
        code, _, _ = self._run_command(["forward", "--remove", f"tcp:{local_port}"])
        return code == 0

    def get_forward_list(self) -> List[str]:
        """Consulta todas las reglas de reenvio activas."""
        code, out, _ = self._run_command(["forward", "--list"])
        if code == 0 and out:
            return out.splitlines()
        return []

if __name__ == "__main__":
    # Test de funcionamiento rápido
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    mgr = ADBManager()
    print("ADB Disponible:", mgr.is_available())
    devices = mgr.list_devices()
    print(f"Dispositivos detectados ({len(devices)}):")
    for d in devices:
        print(f" - Serial: {d['serial']} | Estado: {d['state']} | Modelo: {d['model']}")
    
    if devices:
        res = mgr.setup_port_forward(8080, 8080)
        print("Regla de reenvío aplicada:", res)
        print("Reglas activas:", mgr.get_forward_list())
