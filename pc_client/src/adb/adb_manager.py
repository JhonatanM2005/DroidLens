"""
Módulo de gestión de ADB (Android Debug Bridge) para DroidLens.
Se encarga de:
1. Localizar el ejecutable portable de adb.exe.
2. Detectar celulares Android conectados por cable USB y permitir selección por serial (-s <serial>).
3. Configurar y limpiar reglas de reenvío de puertos (adb forward).
4. Proporcionar diagnósticos accionables sobre el estado del enlace USB.
"""

import os
import subprocess
import shutil
import logging
import socket
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("DroidLens.ADB")

# Comandos globales de ADB que nunca deben heredar el flag -s <serial>
GLOBAL_COMMANDS = {"devices", "version", "start-server", "kill-server"}

class ADBManager:
    def __init__(self, custom_adb_path: Optional[str] = None, selected_serial: Optional[str] = None):
        self.adb_path = custom_adb_path or self._find_adb()
        self.selected_serial: Optional[str] = selected_serial

        if not self.adb_path:
            logger.warning("No se encontro un ejecutable de ADB. El modo USB automatico requerira ADB en el PATH.")
        else:
            logger.info(f"ADB localizado en: {self.adb_path}")

    @staticmethod
    def _find_adb() -> Optional[str]:
        """Busca adb en la carpeta portable de pc_client/bin/adb o en el PATH del sistema."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        portable_adb = os.path.join(base_dir, "bin", "adb", "adb.exe")
        if os.path.exists(portable_adb):
            return portable_adb

        system_adb = shutil.which("adb")
        if system_adb:
            return system_adb

        local_sdk_adb = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
        if os.path.exists(local_sdk_adb):
            return local_sdk_adb

        return None

    def _run_command(self, args: List[str], serial: Optional[str] = None, timeout: float = 5.0) -> Tuple[int, str, str]:
        """
        Ejecuta un comando de adb de forma segura.
        Los comandos globales (devices, version, start-server, kill-server, forward --list)
        nunca usan -s <serial>, garantizando aislamiento total.
        """
        if not self.adb_path:
            return -1, "", "ADB no esta disponible."

        first_arg = args[0] if args else ""
        is_global = first_arg in GLOBAL_COMMANDS or (first_arg == "forward" and "--list" in args)

        cmd = [self.adb_path]
        if not is_global:
            target_serial = serial if serial is not None else self.selected_serial
            if target_serial:
                cmd.extend(["-s", target_serial])
        cmd.extend(args)

        try:
            startupinfo = None
            if os.name == 'nt':
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
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
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

    def set_selected_serial(self, serial: Optional[str]):
        """Define el serial del dispositivo objetivo para las operaciones de reenvío."""
        self.selected_serial = serial

    def setup_port_forward(self, local_port: int = 8080, remote_port: int = 8080, serial: Optional[str] = None, check_state: bool = True) -> bool:
        """
        Configura la regla de reenvio 'adb -s <serial> forward tcp:LOCAL tcp:REMOTE'.
        Solo se aplica si el dispositivo tiene estado 'device'.
        """
        target = serial if serial is not None else self.selected_serial

        if check_state and target:
            devices = self.list_devices()
            dev = next((d for d in devices if d["serial"] == target), None)
            if dev and dev["state"] != "device":
                logger.warning(f"Omitiendo reenvio: dispositivo '{target}' tiene estado '{dev['state']}'")
                return False

        code, out, err = self._run_command(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"], serial=target)
        if code == 0:
            logger.info(f"Reenvio activo [{target or 'default'}]: PC (tcp:{local_port}) -> Android (tcp:{remote_port})")
            return True
        else:
            logger.error(f"Fallo al configurar reenvio [{target}]: {err or out}")
            return False

    def remove_port_forward(self, local_port: int = 8080, serial: Optional[str] = None) -> bool:
        """Elimina de forma segura la regla de reenvio para el puerto y serial especificados."""
        target = serial if serial is not None else self.selected_serial
        code, _, _ = self._run_command(["forward", "--remove", f"tcp:{local_port}"], serial=target)
        return code == 0

    def restart_server(self) -> bool:
        """Reinicia el demonio local de ADB para forzar un reescaneo de todos los buses USB."""
        logger.info("Reiniciando demonio ADB...")
        self._run_command(["kill-server"], timeout=3.0)
        code, _, _ = self._run_command(["start-server"], timeout=5.0)
        return code == 0

    def get_forward_list(self) -> List[str]:
        """Consulta todas las reglas de reenvio activas."""
        code, out, _ = self._run_command(["forward", "--list"])
        if code == 0 and out:
            return out.splitlines()
        return []

    def is_port_in_use(self, port: int = 8080) -> bool:
        """Verifica si el puerto local ya está ocupado por otra aplicación."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    def get_diagnostics(self) -> Dict[str, Any]:
        """Genera un diagnóstico completo y accionable de la conexión USB y ADB."""
        adb_ok = self.is_available()
        if not adb_ok:
            return {
                "status": "error",
                "message": "ADB no encontrado o dañado. Verifique la carpeta bin/adb/.",
                "devices": []
            }

        devices = self.list_devices()
        if not devices:
            return {
                "status": "warning",
                "message": "Ningún celular detectado por USB. Conecte el cable y active 'Depuración USB'.",
                "devices": []
            }

        unauthorized = [d for d in devices if d["state"] == "unauthorized"]
        if unauthorized:
            return {
                "status": "unauthorized",
                "message": f"Dispositivo '{unauthorized[0]['serial']}' no autorizado. Acepte el diálogo en la pantalla del celular.",
                "devices": devices
            }

        return {
            "status": "ready",
            "message": f"{len(devices)} dispositivo(s) listo(s) para streaming.",
            "devices": devices
        }
