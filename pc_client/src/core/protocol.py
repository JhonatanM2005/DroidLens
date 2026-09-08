"""
Protocolo de empaquetado binario para la transmisión de video en DroidLens.
Cabecera fija de 20 bytes:
  [0..3]   MAGIC        -> 4 bytes: 'APCM' (0x41, 0x50, 0x43, 0x4D)
  [4..7]   FRAME_ID     -> uint32 (big-endian)
  [8..15]  TIMESTAMP_MS -> uint64 ms epoch (big-endian)
  [16..19] LENGTH       -> uint32 payload length (big-endian)
Cuerpo:
  [20..N]  PAYLOAD      -> bytes JPEG de la imagen
"""

import struct
from typing import Optional, Tuple

MAGIC = b"APCM"
HEADER_FORMAT = ">4sIQI"  # 4 bytes magic, uint32 frame_id, uint64 timestamp_ms, uint32 length
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Exactamente 20 bytes

def pack_frame(frame_id: int, timestamp_ms: int, jpeg_bytes: bytes) -> bytes:
    """Empaqueta un fotograma JPEG con la cabecera APCM."""
    header = struct.pack(HEADER_FORMAT, MAGIC, frame_id, timestamp_ms, len(jpeg_bytes))
    return header + jpeg_bytes

def parse_header(header_bytes: bytes) -> Optional[Tuple[int, int, int]]:
    """
    Parsea la cabecera de 20 bytes.
    Retorna (frame_id, timestamp_ms, length) o None si el MAGIC no coincide.
    """
    if len(header_bytes) < HEADER_SIZE:
        return None

    magic, frame_id, timestamp_ms, length = struct.unpack(HEADER_FORMAT, header_bytes)
    if magic != MAGIC:
        return None

    return frame_id, timestamp_ms, length
