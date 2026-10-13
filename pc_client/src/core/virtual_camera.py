"""
Controlador Multi-Motor de Cámara Virtual en Windows:
1. Windows 11 Nativo (Media Foundation IMFVirtualCamera via DroidLensMF.dll + Memoria Compartida)
2. DirectShow Clásico (UnityCapture via pyvirtualcam)
"""

import ctypes
from enum import Enum
import logging
import os
import time
from typing import Callable, Dict, Optional
import numpy as np
import cv2
import pyvirtualcam

try:
    from utils.paths import find_driver_script
except ImportError:
    from ..utils.paths import find_driver_script

logger = logging.getLogger("DroidLens.VirtualCamera")


class VirtualCamBackend(str, Enum):
    WINDOWS_MF = "mf_virtualcam"
    UNITY_CAPTURE = "unitycapture"


VCAM_BACKEND_LABELS: Dict[VirtualCamBackend, str] = {
    VirtualCamBackend.WINDOWS_MF: "Windows 11 Nativo (DroidLens Camera)",
    VirtualCamBackend.UNITY_CAPTURE: "DirectShow (Unity Video Capture)",
}

LABEL_TO_VCAM_BACKEND: Dict[str, VirtualCamBackend] = {
    v: k for k, v in VCAM_BACKEND_LABELS.items()
}


class MFVirtualCamBridge:
    """Puente ctypes hacia driver/DroidLensMF.dll (IMFVirtualCamera + Memoria Compartida)."""

    def __init__(
        self,
        dll_path: Optional[str] = None,
        dll_loader: Optional[Callable[[str], object]] = None,
    ):
        self._dll_path = dll_path or find_driver_script("DroidLensMF.dll")
        self._dll_loader = dll_loader or ctypes.WinDLL
        self._dll = None
        self._started = False

    def _load(self) -> bool:
        if self._dll is not None:
            return True
        if not self._dll_path or (self._dll_loader is ctypes.WinDLL and not os.path.exists(self._dll_path)):
            return False
        try:
            dll = self._dll_loader(self._dll_path)
            if hasattr(dll.dl_mf_is_supported, "restype"):
                dll.dl_mf_is_supported.argtypes = []
                dll.dl_mf_is_supported.restype = ctypes.c_int

                dll.dl_mf_start.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
                dll.dl_mf_start.restype = ctypes.c_int

                dll.dl_mf_send_frame.argtypes = [
                    ctypes.POINTER(ctypes.c_uint8),
                    ctypes.c_int,
                    ctypes.c_int,
                ]
                dll.dl_mf_send_frame.restype = ctypes.c_int

                dll.dl_mf_stop.argtypes = []
                dll.dl_mf_stop.restype = None
            self._dll = dll
            return True
        except Exception as e:
            logger.error(f"Error cargando DroidLensMF.dll: {e}")
            self._dll = None
            return False

    def is_supported(self) -> bool:
        if not self._load():
            return False
        try:
            return bool(self._dll.dl_mf_is_supported() == 1)
        except Exception:
            return False

    def start(self, width: int, height: int, fps: int) -> bool:
        if not self._load():
            return False
        try:
            ok = self._dll.dl_mf_start(int(width), int(height), int(fps)) == 1
            self._started = bool(ok)
            return self._started
        except Exception as e:
            logger.error(f"Error en dl_mf_start: {e}")
            self._started = False
            return False

    def send_frame(self, bgr_frame: np.ndarray) -> bool:
        if not self._dll or not self._started:
            return False
        try:
            contig = np.ascontiguousarray(bgr_frame, dtype=np.uint8)
            h, w = contig.shape[:2]
            ptr = contig.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
            return bool(self._dll.dl_mf_send_frame(ptr, int(w), int(h)) == 1)
        except Exception as e:
            logger.error(f"Error en dl_mf_send_frame: {e}")
            return False

    def stop(self) -> None:
        if self._dll and self._started:
            try:
                self._dll.dl_mf_stop()
            except Exception:
                pass
        self._started = False


class VirtualCameraManager:
    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        backend: VirtualCamBackend = VirtualCamBackend.WINDOWS_MF,
        mf_bridge: Optional[MFVirtualCamBridge] = None,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.backend = backend
        self._mf_bridge = mf_bridge or MFVirtualCamBridge()
        self._cam: Optional[pyvirtualcam.Camera] = None
        self.is_active = False
        self.last_error = ""

        # Métricas de salida
        self.frames_sent = 0
        self.last_fps_time = time.time()
        self.fps_output = 0.0

    @property
    def device_name(self) -> str:
        if self.backend == VirtualCamBackend.WINDOWS_MF:
            return "DroidLens Virtual Camera"
        if self._cam is not None and getattr(self._cam, "device", None):
            return str(self._cam.device)
        return "Unity Video Capture"

    def set_backend(self, backend: VirtualCamBackend) -> bool:
        """Cambia entre el motor nativo Windows 11 (IMFVirtualCamera) y DirectShow (UnityCapture)."""
        if self.backend == backend:
            return True

        was_active = self.is_active
        if was_active:
            self.stop()

        self.backend = backend
        if was_active:
            return self.start()
        return True

    def start(self) -> bool:
        """Inicia el dispositivo de cámara virtual en el backend seleccionado."""
        if self.is_active:
            return True

        self.last_error = ""
        if self.backend == VirtualCamBackend.WINDOWS_MF:
            if not self._mf_bridge.is_supported():
                self.last_error = (
                    "Driver Windows 11 (DroidLensMF.dll) no registrado.\n"
                    "Pulsa 'Registrar Driver' o ejecuta driver\\install_driver.bat."
                )
                logger.error(self.last_error)
                self.is_active = False
                return False

            if not self._mf_bridge.start(self.width, self.height, self.fps):
                self.last_error = (
                    "No se pudo iniciar IMFVirtualCamera en Windows 11.\n"
                    "Verifica driver\\install_driver.bat como Administrador."
                )
                logger.error(self.last_error)
                self.is_active = False
                return False

            self.is_active = True
            logger.info(
                f"[OK] Camara virtual Windows 11 activa: '{self.device_name}' ({self.width}x{self.height} @ {self.fps} FPS)"
            )
            return True

        # Backend DirectShow (UnityCapture)
        try:
            self._cam = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.BGR,
                backend="unitycapture",
            )
            self.is_active = True
            logger.info(
                f"[OK] Camara virtual DirectShow activa: '{self._cam.device}' ({self.width}x{self.height} @ {self.fps} FPS)"
            )
            return True
        except Exception as e:
            self.last_error = (
                "Error al iniciar UnityCapture DirectShow.\n"
                "¿Ejecutaste driver\\install_driver.bat?"
            )
            logger.error(f"No se pudo iniciar la camara virtual DirectShow: {e}")
            self.is_active = False
            self._cam = None
            return False

    def update_resolution(self, width: int, height: int, fps: int = 30) -> bool:
        """Cambia la resolución de salida reiniciando el dispositivo si está activo."""
        if self.width == width and self.height == height and self.fps == fps and self.is_active:
            return True

        was_active = self.is_active
        if was_active:
            self.stop()

        self.width = width
        self.height = height
        self.fps = fps

        if was_active:
            return self.start()
        return True

    def send_frame(self, frame: np.ndarray):
        """Envía un fotograma BGR a la cámara virtual activa garantizando concordancia dimensional."""
        if not self.is_active:
            return

        try:
            fh, fw = frame.shape[:2]
            if fw != self.width or fh != self.height:
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

            if self.backend == VirtualCamBackend.WINDOWS_MF:
                self._mf_bridge.send_frame(frame)
            elif self._cam is not None:
                self._cam.send(frame)
                self._cam.sleep_until_next_frame()

            self.frames_sent += 1
            now = time.time()
            dt = now - self.last_fps_time
            if dt >= 1.0:
                self.fps_output = self.frames_sent / dt
                self.frames_sent = 0
                self.last_fps_time = now

        except Exception as e:
            logger.error(f"Error al enviar frame a la camara virtual: {e}")

    def stop(self):
        """Cierra el canal de la cámara virtual activa."""
        if self.backend == VirtualCamBackend.WINDOWS_MF:
            self._mf_bridge.stop()
        if self._cam:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        self.is_active = False
        logger.info("Camara virtual cerrada")
