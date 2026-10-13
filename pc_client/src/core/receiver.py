"""
Receptor multiplexado TCP de ultra baja latencia para DroidLens (APCM v2).
Soporta paquetes de vídeo JPEG (política LIFO de 1 frame), paquetes de audio PCM 16-bit
y control bidireccional de modo de transmisión (Cámara + Micrófono, Solo Cámara, Solo Micrófono).
"""

from enum import Enum
from dataclasses import dataclass
import socket
import threading
import time
import logging
from typing import Optional, Dict, Any, Callable
import numpy as np
import cv2

from .protocol import (
    MAGIC,
    HEADER_SIZE,
    PacketType,
    StreamMode,
    pack_control_mode,
    parse_header,
    parse_control_mode,
)

logger = logging.getLogger("DroidLens.Receiver")


class FrameStatus(Enum):
    NEW_FRAME = "new"
    STALE_CACHED = "stale"
    AUDIO_ONLY_MODE = "audio_only"
    EXPIRED_OR_DISCONNECTED = "expired"


@dataclass
class FrameResult:
    frame: Optional[np.ndarray]
    meta: Dict[str, Any]
    status: FrameStatus

    def __iter__(self):
        """Permite desestructurar como tupla (frame, meta) para compatibilidad."""
        return iter((self.frame, self.meta))


class StreamReceiver:
    STALE_THRESHOLD_SECONDS = 0.25  # 250 ms de tolerancia antes de pasar a standby

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        on_audio_chunk: Optional[Callable[[bytes], Any]] = None,
        on_mode_changed: Optional[Callable[[StreamMode], Any]] = None,
    ):
        self.host = host
        self.port = port
        self.on_audio_chunk = on_audio_chunk
        self.on_mode_changed = on_mode_changed

        self.running = False
        self.connected = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

        self._send_lock = threading.Lock()
        self.stream_mode: StreamMode = StreamMode.AUDIO_VIDEO
        self._control_seq: int = 0

        # Sincronización thread-safe sin pérdida de señales
        self._frame_lock = threading.Lock()
        self._new_frame_cond = threading.Condition(self._frame_lock)
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Dict[str, Any] = {}
        self._has_unconsumed_frame = False

        # Registro de expiración
        self.last_frame_received_at: float = 0.0
        self.last_audio_received_at: float = 0.0

        # Métricas de rendimiento
        self.total_frames_received = 0
        self.total_frames_dropped = 0
        self.total_frames_consumed = 0
        self.total_audio_packets_received = 0
        self.fps_received = 0.0
        self.fps_consumed = 0.0
        self.bitrate_kbps = 0.0
        self.latency_ms = 0.0

        self._last_stats_time = time.time()
        self._frames_since_stat = 0
        self._consumed_since_stat = 0
        self._bytes_since_stat = 0

        # Filtro de offset de reloj para medición precisa de latencia
        self._min_clock_offset: Optional[int] = None
        self._last_offset_reset = time.time()

    def start(self):
        """Inicia el hilo receptor en segundo plano."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop, daemon=True, name="StreamReceiverThread"
        )
        self.thread.start()
        logger.info(f"Receptor iniciado en {self.host}:{self.port}")

    def stop(self):
        """Detiene el receptor y cierra conexiones."""
        self.running = False
        self._close_socket()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        logger.info("Receptor detenido")

    def set_stream_mode(self, mode: StreamMode, notify_remote: bool = True) -> bool:
        """Actualiza el modo de operación local y opcionalmente envía CONTROL_MODE al teléfono."""
        with self._frame_lock:
            self.stream_mode = StreamMode(mode)
            if self.stream_mode == StreamMode.AUDIO_ONLY:
                self._latest_frame = None
                self._has_unconsumed_frame = False
            self._new_frame_cond.notify_all()

        if notify_remote:
            return self.send_control_mode(self.stream_mode)
        return True

    def send_control_mode(self, mode: StreamMode) -> bool:
        """Envía un paquete CONTROL_MODE (22 bytes) al servidor Android por el socket activo."""
        with self._send_lock:
            if not self.connected or self.sock is None:
                return False
            try:
                self._control_seq += 1
                pkt = pack_control_mode(
                    mode,
                    seq_id=self._control_seq,
                    timestamp_ms=int(time.time() * 1000),
                )
                self.sock.sendall(pkt)
                return True
            except Exception as e:
                logger.warning(f"No se pudo enviar cambio de modo al teléfono: {e}")
                return False

    def _close_socket(self):
        with self._frame_lock:
            self.connected = False
            self._has_unconsumed_frame = False
            self._latest_frame = None
            self.last_frame_received_at = 0.0
            self.last_audio_received_at = 0.0
            self._new_frame_cond.notify_all()

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

    def _update_latency(self, timestamp_ms: int) -> None:
        now_ms = int(time.time() * 1000)
        if timestamp_ms > 0:
            raw_offset = now_ms - timestamp_ms
            if self._min_clock_offset is None or raw_offset < self._min_clock_offset:
                self._min_clock_offset = raw_offset
            elif time.time() - self._last_offset_reset > 60.0:
                self._min_clock_offset = raw_offset
                self._last_offset_reset = time.time()

            jitter_latency = max(0.0, float(raw_offset - self._min_clock_offset))
            if self.latency_ms == 0.0:
                self.latency_ms = jitter_latency
            else:
                self.latency_ms = 0.8 * self.latency_ms + 0.2 * jitter_latency

    def _handle_packet(
        self, packet_type: int, seq_id: int, timestamp_ms: int, payload: bytes
    ) -> None:
        """Despacha el paquete recibido según su tipo (VIDEO_JPEG, AUDIO_PCM, CONTROL_MODE)."""
        self._bytes_since_stat += HEADER_SIZE + len(payload)

        if packet_type == PacketType.CONTROL_MODE:
            new_mode = parse_control_mode(payload)
            if new_mode is not None:
                self.set_stream_mode(new_mode, notify_remote=False)
                if self.on_mode_changed is not None:
                    try:
                        self.on_mode_changed(new_mode)
                    except Exception as e:
                        logger.warning(f"Error en callback on_mode_changed: {e}")
            return

        if packet_type == PacketType.AUDIO_PCM:
            self.total_audio_packets_received += 1
            self.last_audio_received_at = time.time()
            self._update_latency(timestamp_ms)
            if (
                self.stream_mode in (StreamMode.AUDIO_ONLY, StreamMode.AUDIO_VIDEO)
                and self.on_audio_chunk is not None
            ):
                try:
                    self.on_audio_chunk(payload)
                except Exception as e:
                    logger.warning(f"Error en callback on_audio_chunk: {e}")
            self._update_stats()
            return

        if packet_type == PacketType.VIDEO_JPEG:
            self.total_frames_received += 1
            self._frames_since_stat += 1
            self._update_latency(timestamp_ms)

            if self.stream_mode == StreamMode.AUDIO_ONLY:
                self._update_stats()
                return

            img_array = np.frombuffer(payload, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is not None:
                recv_time = time.time()
                with self._frame_lock:
                    if self._has_unconsumed_frame:
                        self.total_frames_dropped += 1

                    self._latest_frame = frame
                    self._latest_meta = {
                        "frame_id": seq_id,
                        "timestamp_ms": timestamp_ms,
                        "latency_ms": self.latency_ms,
                        "shape": frame.shape,
                    }
                    self._has_unconsumed_frame = True
                    self.last_frame_received_at = recv_time
                    self._new_frame_cond.notify_all()

            self._update_stats()

    def _run_loop(self):
        """Bucle principal de conexión y lectura continua."""
        while self.running:
            if not self.connected:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512 * 1024)
                    s.settimeout(2.0)
                    s.connect((self.host, self.port))
                    s.settimeout(0.5)
                    self.sock = s
                    with self._frame_lock:
                        self.connected = True
                        self._min_clock_offset = None
                        self._new_frame_cond.notify_all()
                    logger.info(
                        f"[OK] Conectado exitosamente al stream en {self.host}:{self.port}"
                    )
                    # Sincronizar el modo deseado con el teléfono al conectar
                    self.send_control_mode(self.stream_mode)
                except Exception:
                    time.sleep(1.0)
                    continue

            try:
                header_bytes = self._read_exact(HEADER_SIZE)
                if not header_bytes:
                    logger.warning("Conexion cerrada por el emisor.")
                    self._close_socket()
                    continue

                parsed = parse_header(header_bytes)
                if not parsed:
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

                packet_type, seq_id, timestamp_ms, length = parsed
                if length <= 0 or length > 20_000_000:
                    logger.warning(f"Longitud de paquete invalida: {length} bytes")
                    self._close_socket()
                    continue

                payload = self._read_exact(length)
                if not payload:
                    self._close_socket()
                    continue

                self._handle_packet(packet_type, seq_id, timestamp_ms, payload)

            except Exception as e:
                logger.error(f"Error procesando paquete: {e}")
                self._close_socket()
                time.sleep(0.5)

    def _update_stats(self):
        """Calcula FPS reales y bitrate sostenido cada segundo."""
        now = time.time()
        dt = now - self._last_stats_time
        if dt >= 1.0:
            self.fps_received = self._frames_since_stat / dt
            self.fps_consumed = self._consumed_since_stat / dt
            self.bitrate_kbps = (self._bytes_since_stat * 8) / (dt * 1000)
            self._frames_since_stat = 0
            self._consumed_since_stat = 0
            self._bytes_since_stat = 0
            self._last_stats_time = now

    def get_latest_frame(self, timeout: float = 0.033) -> FrameResult:
        """
        Retorna el FrameResult distinguiendo:
        - NEW_FRAME: Frame recién recibido.
        - STALE_CACHED: Último frame válido recibido hace <250 ms.
        - AUDIO_ONLY_MODE: Conectado en modo Solo Micrófono.
        - EXPIRED_OR_DISCONNECTED: Stream desconectado o sin frames por >250 ms.
        """
        now = time.time()
        with self._frame_lock:
            if not self.connected:
                return FrameResult(None, {}, FrameStatus.EXPIRED_OR_DISCONNECTED)

            if self.stream_mode == StreamMode.AUDIO_ONLY:
                return FrameResult(
                    None,
                    {"latency_ms": self.latency_ms, "mode": "audio_only"},
                    FrameStatus.AUDIO_ONLY_MODE,
                )

            if not self._has_unconsumed_frame and timeout > 0:
                self._new_frame_cond.wait(timeout=timeout)
                now = time.time()

            if not self.connected:
                return FrameResult(None, {}, FrameStatus.EXPIRED_OR_DISCONNECTED)

            if self.stream_mode == StreamMode.AUDIO_ONLY:
                return FrameResult(
                    None,
                    {"latency_ms": self.latency_ms, "mode": "audio_only"},
                    FrameStatus.AUDIO_ONLY_MODE,
                )

            if now - self.last_frame_received_at > self.STALE_THRESHOLD_SECONDS:
                return FrameResult(None, {}, FrameStatus.EXPIRED_OR_DISCONNECTED)

            if self._has_unconsumed_frame and self._latest_frame is not None:
                self._has_unconsumed_frame = False
                self._consumed_since_stat += 1
                self.total_frames_consumed += 1
                return FrameResult(
                    self._latest_frame.copy(),
                    dict(self._latest_meta),
                    FrameStatus.NEW_FRAME,
                )

            if self._latest_frame is not None:
                return FrameResult(
                    self._latest_frame.copy(),
                    dict(self._latest_meta),
                    FrameStatus.STALE_CACHED,
                )

            return FrameResult(None, {}, FrameStatus.EXPIRED_OR_DISCONNECTED)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna las métricas actuales de transmisión."""
        return {
            "connected": self.connected,
            "mode": self.stream_mode.name,
            "fps": round(self.fps_received, 1),
            "fps_consumed": round(self.fps_consumed, 1),
            "bitrate_kbps": round(self.bitrate_kbps, 1),
            "latency_ms": round(self.latency_ms, 1),
            "frames_received": self.total_frames_received,
            "frames_dropped": self.total_frames_dropped,
            "frames_consumed": self.total_frames_consumed,
            "audio_packets_received": self.total_audio_packets_received,
        }
