import time
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
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

    # Inyectar un frame artificialmente simulando el hilo de red
    fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    fake_meta = {"frame_id": 1, "timestamp_ms": int(time.time() * 1000)}

    with receiver._frame_lock:
        receiver._latest_frame = fake_frame
        receiver._latest_meta = fake_meta
        receiver._has_unconsumed_frame = True
        receiver.last_frame_received_at = time.time()

    # 1. Primera lectura: debe ser NEW_FRAME
    res1 = receiver.get_latest_frame(timeout=0.01)
    assert res1.status == FrameStatus.NEW_FRAME
    assert res1.frame is not None
    assert res1.meta["frame_id"] == 1

    # 2. Segunda lectura inmediata (sin nuevo frame en socket pero <250ms): STALE_CACHED
    res2 = receiver.get_latest_frame(timeout=0.01)
    assert res2.status == FrameStatus.STALE_CACHED
    assert res2.frame is not None

    # 3. Simular paso del tiempo > 250 ms
    with receiver._frame_lock:
        receiver.last_frame_received_at = time.time() - 0.26

    res3 = receiver.get_latest_frame(timeout=0.01)
    assert res3.status == FrameStatus.EXPIRED_OR_DISCONNECTED
    assert res3.frame is None

def test_receiver_dropped_frames_count():
    receiver = StreamReceiver()
    receiver.connected = True

    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Simular llegada de 5 frames sin que el consumidor los lea
    for i in range(5):
        with receiver._frame_lock:
            if receiver._has_unconsumed_frame:
                receiver.total_frames_dropped += 1
            receiver._latest_frame = fake_frame
            receiver._has_unconsumed_frame = True
            receiver.last_frame_received_at = time.time()

    # El primero no se descarta (se guarda), los siguientes 4 se descartan
    assert receiver.total_frames_dropped == 4
