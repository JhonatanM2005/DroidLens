import pytest
import struct
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.protocol import (
    MAGIC,
    HEADER_SIZE,
    PacketType,
    StreamMode,
    pack_frame,
    pack_control_mode,
    parse_header,
    parse_control_mode,
)


def test_pack_and_parse_valid_header():
    frame_id = 42
    timestamp_ms = 1718000000123
    fake_jpeg = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100 + b"\xFF\xD9"

    packet = pack_frame(frame_id, timestamp_ms, fake_jpeg)
    assert HEADER_SIZE == 21
    assert len(packet) == HEADER_SIZE + len(fake_jpeg)

    header_bytes = packet[:HEADER_SIZE]
    parsed = parse_header(header_bytes)
    assert parsed is not None

    parsed_type, parsed_fid, parsed_ts, parsed_len = parsed
    assert parsed_type == PacketType.VIDEO_JPEG
    assert parsed_fid == frame_id
    assert parsed_ts == timestamp_ms
    assert parsed_len == len(fake_jpeg)


def test_pack_and_parse_audio_and_control():
    pcm = b"\x00\x01" * 960
    audio_pkt = pack_frame(7, 5000, pcm, packet_type=PacketType.AUDIO_PCM)
    assert parse_header(audio_pkt[:HEADER_SIZE]) == (PacketType.AUDIO_PCM, 7, 5000, 1920)

    ctrl_pkt = pack_control_mode(StreamMode.AUDIO_ONLY, seq_id=3, timestamp_ms=9000)
    parsed = parse_header(ctrl_pkt[:HEADER_SIZE])
    assert parsed == (PacketType.CONTROL_MODE, 3, 9000, 1)
    assert parse_control_mode(ctrl_pkt[HEADER_SIZE:]) == StreamMode.AUDIO_ONLY


def test_reject_unknown_packet_type_and_invalid_control_mode():
    bad_header = struct.pack(">4sBIQI", MAGIC, 99, 1, 1000, 10)
    assert parse_header(bad_header) is None
    assert parse_control_mode(b"") is None
    assert parse_control_mode(b"\x99") is None


def test_parse_truncated_header():
    short_bytes = b"APCM\x01\x00\x00\x00\x01"  # Only 9 bytes instead of 21
    assert parse_header(short_bytes) is None


def test_parse_invalid_magic():
    invalid_header = b"BADM" + b"\x01" + b"\x00" * 16
    assert parse_header(invalid_header) is None


def test_stream_resynchronization():
    """Verifica que el receptor puede encontrar el MAGIC tras bytes corruptos de basura."""
    frame_id = 101
    timestamp_ms = 1718000000456
    fake_jpeg = b"\xFF\xD8\xFF" + b"\x12" * 50

    garbage = b"GARBAGE_NOISE_BYTES\x00\xFF\xAA\xBB"
    valid_packet = pack_frame(frame_id, timestamp_ms, fake_jpeg)
    stream_buffer = garbage + valid_packet

    magic_pos = stream_buffer.find(MAGIC)
    assert magic_pos != -1

    recovered_packet = stream_buffer[magic_pos:]
    parsed = parse_header(recovered_packet[:HEADER_SIZE])
    assert parsed is not None
    r_type, r_fid, r_ts, r_len = parsed
    assert r_type == PacketType.VIDEO_JPEG
    assert r_fid == frame_id
    assert r_ts == timestamp_ms
    assert r_len == len(fake_jpeg)
