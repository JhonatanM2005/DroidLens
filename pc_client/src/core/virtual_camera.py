"""
Controlador de la Cámara Virtual DirectShow en Windows (UnityCapture).
Se encarga de inyectar los fotogramas en memoria compartida para que
Zoom, Meet, Teams, Discord y los navegadores detecten la señal.
"""

import logging
import time
from typing import Optional
import numpy as np
import cv2
import pyvirtualcam

logger = logging.getLogger("DroidLens.VirtualCamera")

class VirtualCameraManager:
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._cam: Optional[pyvirtualcam.Camera] = None
        self.is_active = False

        # Métricas de salida
        self.frames_sent = 0
        self.last_fps_time = time.time()
        self.fps_output = 0.0

    def start(self) -> bool:
        """Inicia el dispositivo de cámara virtual en Windows."""
        if self.is_active and self._cam is not None:
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

    def update_resolution(self, width: int, height: int, fps: int = 30) -> bool:
        """Cambia la resolución de salida (ej. a 1080p o 720p) reiniciando el dispositivo si está activo."""
        if self.width == width and self.height == height and self.fps == fps and self._cam is not None:
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
        """Envía un fotograma BGR a la cámara virtual garantizando concordancia dimensional."""
        if not self._cam or not self.is_active:
            return

        try:
            fh, fw = frame.shape[:2]
            if fw != self.width or fh != self.height:
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

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
        """Cierra el canal de la cámara virtual."""
        if self._cam:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        self.is_active = False
        logger.info("Camara virtual cerrada")
