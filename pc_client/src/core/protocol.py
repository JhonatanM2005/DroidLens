"""
Protocolo de empaquetado binario APCM v2 para transmisión multiplexada en DroidLens.
Cabecera fija de 21 bytes (Big-Endian):
  [0..3]   MAGIC        -> 4 bytes: 'APCM' (0x41, 0x50, 0x43, 0x4D)
  [4]      PACKET_TYPE  -> uint8 (1: VIDEO_JPEG, 2: AUDIO_PCM, 3: CONTROL_MODE)
  [5..8]   SEQ_ID       -> uint32 (big-endian)
  [9..16]  TIMESTAMP_MS -> uint64 ms epoch (big-endian)
  [17..20] LENGTH       -> uint32 payload length (big-endian)
Cuerpo:
  [21..N]  PAYLOAD      -> bytes JPEG, chunk PCM 16-bit o byte de modo
"""

from enum import IntEnum
import struct
from typing import Optional, Tuple

MAGIC = b"APCM"
HEADER_FORMAT = ">4sBIQI"  # 4B magic, uint8 packet_type, uint32 seq_id, uint64 timestamp_ms, uint32 length
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Exactamente 21 bytes


class PacketType(IntEnum):
    VIDEO_JPEG = 1
    AUDIO_PCM = 2
    CONTROL_MODE = 3


class StreamMode(IntEnum):
    VIDEO_ONLY = 1
    AUDIO_ONLY = 2
    AUDIO_VIDEO = 3


STREAM_MODE_LABELS = {
    StreamMode.AUDIO_VIDEO: "Cámara + Micrófono",
    StreamMode.VIDEO_ONLY: "Solo Cámara",
    StreamMode.AUDIO_ONLY: "Solo Micrófono",
}

LABEL_TO_STREAM_MODE = {v: k for k, v in STREAM_MODE_LABELS.items()}


def pack_frame(
    frame_id: int,
    timestamp_ms: int,
    payload_bytes: bytes,
    packet_type: int = PacketType.VIDEO_JPEG,
) -> bytes:
    """Empaqueta un payload (JPEG, PCM o control) con la cabecera APCM v2 de 21 bytes."""
    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        int(packet_type),
        frame_id,
        timestamp_ms,
        len(payload_bytes),
    )
    return header + payload_bytes


def pack_control_mode(
    mode: StreamMode, seq_id: int = 0, timestamp_ms: int = 0
) -> bytes:
    """Empaqueta un comando bidireccional de cambio de modo de transmisión."""
    payload = struct.pack(">B", int(mode))
    return pack_frame(seq_id, timestamp_ms, payload, packet_type=PacketType.CONTROL_MODE)


def parse_header(header_bytes: bytes) -> Optional[Tuple[int, int, int, int]]:
    """
    Parsea la cabecera de 21 bytes.
    Retorna (packet_type, seq_id, timestamp_ms, length) o None si MAGIC o packet_type son inválidos.
    """
    if len(header_bytes) < HEADER_SIZE:
        return None

    magic, packet_type, seq_id, timestamp_ms, length = struct.unpack(
        HEADER_FORMAT, header_bytes[:HEADER_SIZE]
    )
    if magic != MAGIC:
        return None

    if packet_type not in (
        PacketType.VIDEO_JPEG,
        PacketType.AUDIO_PCM,
        PacketType.CONTROL_MODE,
    ):
        return None

    return PacketType(packet_type), seq_id, timestamp_ms, length


def parse_control_mode(payload: bytes) -> Optional[StreamMode]:
    """Extrae y valida el StreamMode de un payload CONTROL_MODE."""
    if not payload:
        return None
    mode_val = payload[0]
    if mode_val in (
        StreamMode.VIDEO_ONLY,
        StreamMode.AUDIO_ONLY,
        StreamMode.AUDIO_VIDEO,
    ):
        return StreamMode(mode_val)
    return None
