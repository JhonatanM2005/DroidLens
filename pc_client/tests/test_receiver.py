import time
from unittest.mock import MagicMock
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.protocol import HEADER_SIZE, PacketType, StreamMode, pack_control_mode, parse_header, parse_control_mode
from core.receiver import StreamReceiver, FrameStatus, FrameResult


def test_receiver_expired_when_disconnected():
    receiver = StreamReceiver()
    receiver.connected = False
    result = receiver.get_latest_frame(timeout=0.01)
    assert result.status == FrameStatus.EXPIRED_OR_DISCONNECTED
    assert result.frame is None


def test_receiver_new_frame_and_stale_transition():
    receiver = StreamReceiver()
    receiver.connected = True

    fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    fake_meta = {"frame_id": 1, "timestamp_ms": int(time.time() * 1000)}

    with receiver._frame_lock:
        receiver._latest_frame = fake_frame
        receiver._latest_meta = fake_meta
        receiver._has_unconsumed_frame = True
        receiver.last_frame_received_at = time.time()

    res1 = receiver.get_latest_frame(timeout=0.01)
    assert res1.status == FrameStatus.NEW_FRAME
    assert res1.frame is not None
    assert res1.meta["frame_id"] == 1

    res2 = receiver.get_latest_frame(timeout=0.01)
    assert res2.status == FrameStatus.STALE_CACHED
    assert res2.frame is not None

    with receiver._frame_lock:
        receiver.last_frame_received_at = time.time() - 0.26

    res3 = receiver.get_latest_frame(timeout=0.01)
    assert res3.status == FrameStatus.EXPIRED_OR_DISCONNECTED
    assert res3.frame is None


def test_receiver_dropped_frames_count():
    receiver = StreamReceiver()
    receiver.connected = True

    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    for _ in range(5):
        with receiver._frame_lock:
            if receiver._has_unconsumed_frame:
                receiver.total_frames_dropped += 1
            receiver._latest_frame = fake_frame
            receiver._has_unconsumed_frame = True
            receiver.last_frame_received_at = time.time()

    assert receiver.total_frames_dropped == 4


def test_receiver_dispatches_audio_and_control_packets():
    received_audio = []
    received_modes = []
    receiver = StreamReceiver(
        on_audio_chunk=lambda b: received_audio.append(b),
        on_mode_changed=lambda m: received_modes.append(m),
    )
    receiver.connected = True

    pcm_chunk = b"\x01\x02" * 960
    receiver._handle_packet(PacketType.AUDIO_PCM, 1, 1000, pcm_chunk)
    assert len(received_audio) == 1
    assert received_audio[0] == pcm_chunk
    assert receiver.total_audio_packets_received == 1

    ctrl_payload = pack_control_mode(StreamMode.AUDIO_ONLY)[HEADER_SIZE:]
    receiver._handle_packet(PacketType.CONTROL_MODE, 2, 1005, ctrl_payload)
    assert receiver.stream_mode == StreamMode.AUDIO_ONLY
    assert received_modes == [StreamMode.AUDIO_ONLY]

    res = receiver.get_latest_frame(timeout=0.01)
    assert res.status == FrameStatus.AUDIO_ONLY_MODE
    assert res.frame is None

    # Ignore invalid control mode payload without crashing
    receiver._handle_packet(PacketType.CONTROL_MODE, 3, 1010, b"\x99")
    assert receiver.stream_mode == StreamMode.AUDIO_ONLY


def test_receiver_send_control_mode_over_socket():
    receiver = StreamReceiver()
    mock_sock = MagicMock()
    receiver.sock = mock_sock
    receiver.connected = True

    assert receiver.set_stream_mode(StreamMode.VIDEO_ONLY, notify_remote=True) is True
    assert receiver.stream_mode == StreamMode.VIDEO_ONLY
    mock_sock.sendall.assert_called_once()
    sent_bytes = mock_sock.sendall.call_args[0][0]
    parsed = parse_header(sent_bytes[:HEADER_SIZE])
    assert parsed is not None
    assert parsed[0] == PacketType.CONTROL_MODE
    assert parse_control_mode(sent_bytes[HEADER_SIZE:]) == StreamMode.VIDEO_ONLY
