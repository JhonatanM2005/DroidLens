"""
Gestor de salida de audio en tiempo real para DroidLens en Windows.
Enruta paquetes PCM 16-bit (48 kHz, mono) hacia un dispositivo de salida seleccionable,
con autodetección de 'CABLE Input (VB-Audio Virtual Cable)' para micrófono virtual.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

try:
    import sounddevice as sd
except Exception:
    sd = None

logger = logging.getLogger("DroidLens.AudioOutput")

SAMPLE_RATE = 48000
CHANNELS = 1
CHUNK_SAMPLES = 960  # 20 ms a 48 kHz
CHUNK_BYTES = CHUNK_SAMPLES * 2  # 1920 bytes (int16)
SILENCED_DEVICE_LABEL = "Silenciado"


class AudioOutputManager:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self._lock = threading.Lock()
        self._stream: Optional[Any] = None
        self.current_device_name: Optional[str] = None
        self.is_active: bool = False
        self.muted: bool = False

    def list_output_devices(self) -> List[Dict[str, Any]]:
        """Retorna la lista de dispositivos con capacidad de salida de audio."""
        if sd is None:
            return []
        try:
            raw_devices = sd.query_devices()
            output_devices: List[Dict[str, Any]] = []
            seen_names = set()
            for idx, dev in enumerate(raw_devices):
                max_out = int(dev.get("max_output_channels", 0))
                name = str(dev.get("name", "")).strip()
                if max_out > 0 and name and name not in seen_names:
                    seen_names.add(name)
                    output_devices.append(
                        {
                            "index": int(dev.get("index", idx)),
                            "name": name,
                        }
                    )
            return output_devices
        except Exception as e:
            logger.warning(f"No se pudieron consultar dispositivos de audio: {e}")
            return []

    def find_preferred_device(self) -> Optional[str]:
        """Prioriza 'CABLE Input' (VB-Audio Virtual Cable) si está disponible; si no, el primer dispositivo."""
        devices = self.list_output_devices()
        for dev in devices:
            if "cable input" in dev["name"].lower():
                return dev["name"]
        if devices:
            return devices[0]["name"]
        return None

    def _resolve_device_index(self, device_name: Optional[str]) -> Optional[int]:
        devices = self.list_output_devices()
        if not devices:
            return None
        if device_name:
            for dev in devices:
                if dev["name"] == device_name:
                    return dev["index"]
            for dev in devices:
                if device_name.lower() in dev["name"].lower():
                    return dev["index"]
        preferred = self.find_preferred_device()
        for dev in devices:
            if dev["name"] == preferred:
                return dev["index"]
        return devices[0]["index"]

    def start(self, device_name: Optional[str] = None) -> bool:
        """Abre el flujo de salida RawOutputStream en el dispositivo indicado."""
        with self._lock:
            self._close_stream_unlocked()

            target_name = device_name or self.current_device_name or self.find_preferred_device()
            self.current_device_name = target_name

            if target_name == SILENCED_DEVICE_LABEL or sd is None:
                self.is_active = False
                return target_name == SILENCED_DEVICE_LABEL

            dev_idx = self._resolve_device_index(target_name)
            if dev_idx is None:
                self.is_active = False
                return False

            try:
                stream = sd.RawOutputStream(
                    samplerate=self.sample_rate,
                    blocksize=CHUNK_SAMPLES,
                    device=dev_idx,
                    channels=self.channels,
                    dtype="int16",
                    latency="low",
                )
                stream.start()
                self._stream = stream
                self.is_active = True
                logger.info(f"[OK] Salida de audio activa en '{target_name}' (idx={dev_idx})")
                return True
            except Exception as e:
                logger.error(f"Error abriendo salida de audio '{target_name}': {e}")
                self._stream = None
                self.is_active = False
                return False

    def stop(self) -> None:
        """Detiene y cierra el flujo de salida de audio."""
        with self._lock:
            self._close_stream_unlocked()

    def _close_stream_unlocked(self) -> None:
        self.is_active = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def set_device(self, device_name: Optional[str]) -> bool:
        """Cambia en caliente el dispositivo de salida de audio."""
        self.current_device_name = device_name
        if device_name == SILENCED_DEVICE_LABEL:
            self.stop()
            return True
        return self.start(device_name)

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)

    def write_chunk(self, pcm_bytes: bytes) -> bool:
        """Escribe un bloque PCM int16 en el stream activo sin bloquear ni propagar excepciones."""
        if self.muted or not pcm_bytes or (len(pcm_bytes) % 2 != 0):
            return False

        with self._lock:
            if not self.is_active or self._stream is None:
                return False
            try:
                self._stream.write(pcm_bytes)
                return True
            except Exception as e:
                logger.warning(f"Fallo escribiendo en dispositivo de audio: {e}")
                self._close_stream_unlocked()
                return False
