"""
Receptor de video TCP de ultra baja latencia para DroidLens.
Implementa una política LIFO (buffer de 1 solo frame) para descartar
fotogramas atrasados y asegurar que el video en vivo no acumule retraso.
"""

import socket
import threading
import time
import logging
from typing import Optional, Tuple, Dict, Any
import numpy as np
import cv2

from .protocol import MAGIC, HEADER_SIZE, parse_header

logger = logging.getLogger("DroidLens.Receiver")

class StreamReceiver:
    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
        self.running = False
        self.connected = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

        # Buffer LIFO de un solo fotograma
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Dict[str, Any] = {}
        self._new_frame_event = threading.Event()

        # Métricas de rendimiento
        self.total_frames_received = 0
        self.total_frames_dropped = 0
        self.fps_received = 0.0
        self.bitrate_kbps = 0.0
        self.latency_ms = 0.0

        self._last_stats_time = time.time()
        self._frames_since_stat = 0
        self._bytes_since_stat = 0

    def start(self):
        """Inicia el hilo receptor de frames en segundo plano."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="StreamReceiverThread")
        self.thread.start()
        logger.info(f"Receptor iniciado en {self.host}:{self.port}")

    def stop(self):
        """Detiene el receptor y cierra conexiones."""
        self.running = False
        self._close_socket()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        logger.info("Receptor detenido")

    def _close_socket(self):
        self.connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _read_exact(self, num_bytes: int) -> Optional[bytes]:
        """Lee exactamente num_bytes del socket o retorna None si se corta la conexión."""
        buffer = bytearray()
        while len(buffer) < num_bytes and self.running:
            try:
                chunk = self.sock.recv(num_bytes - len(buffer))
                if not chunk:
                    return None
                buffer.extend(chunk)
            except (socket.timeout, BlockingIOError):
                continue
            except Exception as e:
                logger.debug(f"Error en socket recv: {e}")
                return None
        return bytes(buffer) if len(buffer) == num_bytes else None

    def _run_loop(self):
        """Bucle principal de conexión y lectura continua."""
        while self.running:
            if not self.connected:
                # Intentar conectar
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512 * 1024)
                    s.settimeout(2.0)
                    s.connect((self.host, self.port))
                    s.settimeout(0.5)
                    self.sock = s
                    self.connected = True
                    logger.info(f"[OK] Conectado exitosamente al stream en {self.host}:{self.port}")
                except Exception:
                    time.sleep(1.0)
                    continue

            # Lectura de paquetes
            try:
                header_bytes = self._read_exact(HEADER_SIZE)
                if not header_bytes:
                    logger.warning("Conexion cerrada por el emisor.")
                    self._close_socket()
                    continue

                parsed = parse_header(header_bytes)
                if not parsed:
                    # Pérdida de sincronización: buscar el byte mágico siguiente
                    logger.warning("Cabecera corrupta, resincronizando...")
                    while self.running:
                        b = self.sock.recv(1)
                        if not b:
                            break
                        if b == MAGIC[:1]:
                            next_3 = self._read_exact(3)
                            if next_3 and (b + next_3) == MAGIC:
                                rest = self._read_exact(HEADER_SIZE - 4)
                                if rest:
                                    parsed = parse_header(MAGIC + rest)
                                    break
                    if not parsed:
                        self._close_socket()
                        continue

                frame_id, timestamp_ms, length = parsed
                if length <= 0 or length > 20_000_000:  # Límite de seguridad 20MB
                    logger.warning(f"Longitud de frame invalida: {length} bytes")
                    self._close_socket()
                    continue

                payload = self._read_exact(length)
                if not payload:
                    self._close_socket()
                    continue

                # Actualizar métricas de red
                self.total_frames_received += 1
                self._frames_since_stat += 1
                self._bytes_since_stat += HEADER_SIZE + length

                now_ms = int(time.time() * 1000)
                if timestamp_ms > 0 and now_ms >= timestamp_ms:
                    self.latency_ms = float(now_ms - timestamp_ms)

                # Decodificar JPEG a imagen BGR de OpenCV
                img_array = np.frombuffer(payload, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                if frame is not None:
                    with self._frame_lock:
                        if self._latest_frame is not None and not self._new_frame_event.is_set():
                            self.total_frames_dropped += 1

                        self._latest_frame = frame
                        self._latest_meta = {
                            "frame_id": frame_id,
                            "timestamp_ms": timestamp_ms,
                            "latency_ms": self.latency_ms,
                            "shape": frame.shape
                        }
                        self._new_frame_event.set()

                self._update_stats()

            except Exception as e:
                logger.error(f"Error procesando frame: {e}")
                self._close_socket()
                time.sleep(0.5)

    def _update_stats(self):
        """Calcula FPS reales y bitrate sostenido cada segundo."""
        now = time.time()
        dt = now - self._last_stats_time
        if dt >= 1.0:
            self.fps_received = self._frames_since_stat / dt
            self.bitrate_kbps = (self._bytes_since_stat * 8) / (dt * 1000)
            self._frames_since_stat = 0
            self._bytes_since_stat = 0
            self._last_stats_time = now

    def get_latest_frame(self, timeout: float = 0.1) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """
        Retorna el fotograma más fresco disponible y sus metadatos.
        Si no hay frame nuevo en el timeout, retorna el último disponible o None.
        """
        self._new_frame_event.wait(timeout=timeout)
        self._new_frame_event.clear()
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy(), dict(self._latest_meta)
            return None, {}

    def get_stats(self) -> Dict[str, Any]:
        """Retorna las métricas actuales de transmisión."""
        return {
            "connected": self.connected,
            "fps": round(self.fps_received, 1),
            "bitrate_kbps": round(self.bitrate_kbps, 1),
            "latency_ms": round(self.latency_ms, 1),
            "frames_received": self.total_frames_received,
            "frames_dropped": self.total_frames_dropped
        }
