import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.processor import FrameProcessor

def test_processor_dimensions_and_scaling():
    processor = FrameProcessor(target_width=1280, target_height=720)
    processor.rotation_degrees = 0
    processor.flip_horizontal = False

    # Frame 1920x1080 (16:9) debe redimensionarse exactamente a 1280x720
    sample = np.zeros((1080, 1920, 3), dtype=np.uint8)
    out = processor.process_frame(sample)
    assert out.shape == (720, 1280, 3)

def test_processor_rotation():
    processor = FrameProcessor(target_width=1280, target_height=720)
    processor.flip_horizontal = False

    # Probar rotaciones 0, 90, 180, 270
    sample = np.zeros((720, 1280, 3), dtype=np.uint8)
    sample[0, 0] = [255, 0, 0]

    for rot in [0, 90, 180, 270]:
        processor.rotation_degrees = rot
        out = processor.process_frame(sample)
        assert out.shape == (720, 1280, 3)

def test_processor_portrait_aspect_ratio_padding():
    """Un teléfono en vertical (ej. 1080x1920) debe preservarse y centrarse en canvas 16:9."""
    processor = FrameProcessor(target_width=1280, target_height=720)
    portrait_frame = np.full((1920, 1080, 3), 200, dtype=np.uint8)

    out = processor.process_frame(portrait_frame)
    assert out.shape == (720, 1280, 3)
    # Los bordes izquierdo y derecho deben tener el fondo oscuro del canvas
    assert not np.array_equal(out[:, 0, :], [200, 200, 200])

def test_processor_standby_frame():
    processor = FrameProcessor(target_width=1280, target_height=720)
    standby = processor.generate_standby_frame("Probando Standby")
    assert standby.shape == (720, 1280, 3)
    assert np.any(standby > 0)

def test_processor_diagnostic_overlay():
    processor = FrameProcessor(target_width=1280, target_height=720)
    processor.show_diagnostic_overlay = True
    meta = {"frame_id": 99, "latency_ms": 14.5, "shape": (720, 1280, 3)}

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    out = processor.process_frame(frame, meta=meta)
    assert out.shape == (720, 1280, 3)
    # Verificar que el overlay dibujó algo en la esquina superior izquierda
    assert np.any(out[12:100, 12:260] > 0)
