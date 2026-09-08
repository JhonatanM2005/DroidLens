"""
Controlador de la Cámara Virtual DirectShow en Windows (UnityCapture).
Se encarga de inyectar los fotogramas en memoria compartida para que
Zoom, Meet, Teams, Discord y los navegadores detecten la señal.
"""

import logging
from typing import Optional
import numpy as np
import pyvirtualcam

logger = logging.getLogger("DroidLens.VirtualCamera")

class VirtualCameraManager:
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._cam: Optional[pyvirtualcam.Camera] = None
        self.is_active = False

    def start(self) -> bool:
        """Inicia el dispositivo de cámara virtual en Windows."""
        if self.is_active:
            return True

        try:
            self._cam = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.BGR,
                backend='unitycapture'
            )
            self.is_active = True
            logger.info(f"[OK] Camara virtual activa: '{self._cam.device}' ({self.width}x{self.height} @ {self.fps} FPS)")
            return True
        except Exception as e:
            logger.error(f"No se pudo iniciar la camara virtual: {e}")
            self.is_active = False
            self._cam = None
            return False

    def send_frame(self, frame: np.ndarray):
        """Envía un fotograma BGR a la cámara virtual."""
        if self._cam and self.is_active:
            try:
                self._cam.send(frame)
                self._cam.sleep_until_next_frame()
            except Exception as e:
                logger.error(f"Error al enviar frame a la camara virtual: {e}")

    def stop(self):
        """Cierra el canal de la cámara virtual."""
        if self._cam:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        self.is_active = False
        logger.info("Camara virtual cerrada")
