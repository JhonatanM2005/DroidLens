"""
Módulo de procesamiento y transformación de imagen para DroidLens.
Aplica rotación, modo espejo y genera la pantalla de standby cuando
el dispositivo no está transmitiendo video.
"""

import math
import time
from typing import Tuple
import numpy as np
import cv2

class FrameProcessor:
    def __init__(self, target_width: int = 1280, target_height: int = 720):
        self.target_width = target_width
        self.target_height = target_height

        # Ajustes de transformación
        self.rotation_degrees = 0  # 0, 90, 180, 270
        self.flip_horizontal = True  # Modo espejo (activo por defecto para webcams)
        self.flip_vertical = False

        self._standby_counter = 0

    def set_target_size(self, width: int, height: int):
        self.target_width = width
        self.target_height = height

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Aplica transformaciones de orientación y tamaño al fotograma."""
        # 1. Rotación
        if self.rotation_degrees == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation_degrees == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotation_degrees == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # 2. Espejo (Flip horizontal)
        if self.flip_horizontal and not self.flip_vertical:
            frame = cv2.flip(frame, 1)
        elif self.flip_vertical and not self.flip_horizontal:
            frame = cv2.flip(frame, 0)
        elif self.flip_horizontal and self.flip_vertical:
            frame = cv2.flip(frame, -1)

        # 3. Ajuste estricto a 16:9 sin deformar la imagen
        h, w = frame.shape[:2]
        target_w, target_h = self.target_width, self.target_height
        current_aspect = w / h
        target_aspect = target_w / target_h

        if abs(current_aspect - target_aspect) < 0.02:
            # Misma relación 16:9: escalado directo
            if w != target_w or h != target_h:
                frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        else:
            # Proporción distinta (ej. teléfono en vertical): escalar preservando proporción y centrar en canvas 16:9
            scale = min(target_w / w, target_h / h)
            nw, nh = int(w * scale), int(h * scale)
            resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)

            canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            canvas[:] = (18, 16, 14)  # Fondo oscuro elegante
            x_offset = (target_w - nw) // 2
            y_offset = (target_h - nh) // 2
            canvas[y_offset:y_offset + nh, x_offset:x_offset + nw] = resized
            frame = canvas

        return frame

    def generate_standby_frame(self, message: str = "Conectando con celular Android por USB...") -> np.ndarray:
        """Genera una pantalla de espera elegante cuando la cámara no está transmitiendo."""
        self._standby_counter += 1
        t = self._standby_counter * 0.05

        width, height = self.target_width, self.target_height
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (26, 24, 22)  # Fondo gris oscuro azulado (#16181A)

        # Líneas de cuadrícula tenues
        grid = 40
        for x in range(0, width, grid):
            cv2.line(frame, (x, 0), (x, height), (38, 35, 32), 1)
        for y in range(0, height, grid):
            cv2.line(frame, (0, y), (width, y), (38, 35, 32), 1)

        # Centro
        cx, cy = width // 2, height // 2

        # Círculo pulsante animado
        pulse_radius = int(45 + 8 * math.sin(t))
        cv2.circle(frame, (cx, cy - 40), pulse_radius + 15, (50, 45, 40), 2)
        cv2.circle(frame, (cx, cy - 40), pulse_radius, (255, 140, 0), -1)  # Naranja DroidLens
        cv2.circle(frame, (cx, cy - 40), 18, (255, 255, 255), -1)

        # Textos principales
        title = "DroidLens"
        cv2.putText(frame, title, (cx - 100, cy + 50),
                    cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)

        # Subtexto de estado con puntos animados
        dots = "." * (int(t * 1.5) % 4)
        status_text = f"{message}{dots}"
        text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 1)[0]
        tx = cx - text_size[0] // 2
        cv2.putText(frame, status_text, (tx, cy + 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 1, cv2.LINE_AA)

        # Pie informativo
        tip = "Conecta el cable USB con 'Depuracion USB' activada en la app móvil"
        tip_size = cv2.getTextSize(tip, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        cv2.putText(frame, tip, (cx - tip_size[0] // 2, height - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (110, 110, 110), 1, cv2.LINE_AA)

        return frame
