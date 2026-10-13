"""
Unit tests for TrayManager (System Tray background mode and quick actions)
and version resolution helper.
"""

import os
import sys
from unittest.mock import MagicMock
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.protocol import StreamMode
from ui.tray_manager import TrayManager, create_tray_icon_image
from utils.paths import get_app_version


def test_create_tray_icon_image_returns_valid_rgba_image():
    img = create_tray_icon_image(size=64)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_tray_manager_invokes_restore_mode_and_quit_callbacks():
    restored = []
    modes = []
    quitted = []
    fake_icon = MagicMock()
    fake_icon_factory = MagicMock(return_value=fake_icon)

    manager = TrayManager(
        on_restore=lambda: restored.append(True),
        on_select_mode=lambda m: modes.append(m),
        on_quit=lambda: quitted.append(True),
        get_current_mode=lambda: StreamMode.AUDIO_VIDEO,
        icon_factory=fake_icon_factory,
    )

    manager.start()
    assert manager.is_running is True
    fake_icon.run_detached.assert_called_once()

    manager.trigger_restore()
    assert restored == [True]

    manager.trigger_select_mode(StreamMode.AUDIO_ONLY)
    assert modes == [StreamMode.AUDIO_ONLY]

    manager.trigger_quit()
    assert quitted == [True]

    manager.stop()
    fake_icon.stop.assert_called_once()
    assert manager.is_running is False


def test_get_app_version_prefers_env_var_and_strips_v_prefix(monkeypatch):
    monkeypatch.setenv("DROIDLENS_VERSION", "v1.2.3")
    assert get_app_version() == "1.2.3"


def test_get_app_version_falls_back_to_version_file(monkeypatch):
    monkeypatch.delenv("DROIDLENS_VERSION", raising=False)
    ver = get_app_version()
    assert isinstance(ver, str)
    assert len(ver.split(".")) >= 3
