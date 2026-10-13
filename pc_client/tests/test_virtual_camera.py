"""
Unit tests for multi-backend VirtualCameraManager and MFVirtualCamBridge (ctypes).
"""

import os
import sys
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.virtual_camera import (
    VirtualCamBackend,
    VCAM_BACKEND_LABELS,
    LABEL_TO_VCAM_BACKEND,
    MFVirtualCamBridge,
    VirtualCameraManager,
)


def test_mf_bridge_calls_native_exports_with_contiguous_bgr():
    fake_dll = MagicMock()
    fake_dll.dl_mf_is_supported.return_value = 1
    fake_dll.dl_mf_start.return_value = 1
    fake_dll.dl_mf_send_frame.return_value = 1

    bridge = MFVirtualCamBridge(dll_path="fake.dll", dll_loader=lambda _: fake_dll)
    assert bridge.is_supported() is True
    assert bridge.start(1280, 720, 30) is True

    # Non-contiguous slice should be made contiguous automatically
    raw = np.zeros((720, 1280, 4), dtype=np.uint8)
    non_contig_bgr = raw[:, :, :3]
    assert not non_contig_bgr.flags["C_CONTIGUOUS"]

    assert bridge.send_frame(non_contig_bgr) is True
    fake_dll.dl_mf_send_frame.assert_called_once()
    bridge.stop()
    fake_dll.dl_mf_stop.assert_called_once()


def test_vcam_manager_switches_backends_and_reports_device_name():
    fake_bridge = MagicMock()
    fake_bridge.is_supported.return_value = True
    fake_bridge.start.return_value = True
    fake_bridge.send_frame.return_value = True

    mgr = VirtualCameraManager(
        width=1280,
        height=720,
        fps=30,
        backend=VirtualCamBackend.WINDOWS_MF,
        mf_bridge=fake_bridge,
    )
    assert mgr.start() is True
    assert mgr.is_active is True
    assert mgr.device_name == "DroidLens Virtual Camera"

    frame_small = np.zeros((480, 640, 3), dtype=np.uint8)
    mgr.send_frame(frame_small)
    sent_arg = fake_bridge.send_frame.call_args[0][0]
    assert sent_arg.shape == (720, 1280, 3)

    with patch("core.virtual_camera.pyvirtualcam.Camera") as mock_pyvcam:
        mock_cam_inst = MagicMock()
        mock_cam_inst.device = "Unity Video Capture"
        mock_pyvcam.return_value = mock_cam_inst

        assert mgr.set_backend(VirtualCamBackend.UNITY_CAPTURE) is True
        fake_bridge.stop.assert_called_once()
        assert mgr.is_active is True
        assert mgr.device_name == "Unity Video Capture"


def test_vcam_manager_handles_unsupported_mf_gracefully():
    fake_bridge = MagicMock()
    fake_bridge.is_supported.return_value = False

    mgr = VirtualCameraManager(
        backend=VirtualCamBackend.WINDOWS_MF,
        mf_bridge=fake_bridge,
    )
    assert mgr.start() is False
    assert mgr.is_active is False
    assert "install_driver.bat" in mgr.last_error
