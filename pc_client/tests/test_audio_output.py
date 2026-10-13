import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from core.audio_output import AudioOutputManager, SILENCED_DEVICE_LABEL

FAKE_DEVICES = [
    {"name": "Speakers (Realtek Audio)", "max_output_channels": 2, "index": 0},
    {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2, "index": 1},
    {"name": "Microphone (Realtek Audio)", "max_output_channels": 0, "index": 2},
]


def test_auto_detects_vb_cable_and_filters_inputs():
    with patch("core.audio_output.sd") as mock_sd:
        mock_sd.query_devices.return_value = FAKE_DEVICES
        mgr = AudioOutputManager()
        devices = mgr.list_output_devices()
        assert len(devices) == 2
        assert mgr.find_preferred_device() == "CABLE Input (VB-Audio Virtual Cable)"


def test_fallback_when_no_vb_cable_present():
    devices_no_cable = [
        {"name": "Speakers (Realtek Audio)", "max_output_channels": 2, "index": 0},
    ]
    with patch("core.audio_output.sd") as mock_sd:
        mock_sd.query_devices.return_value = devices_no_cable
        mgr = AudioOutputManager()
        assert mgr.find_preferred_device() == "Speakers (Realtek Audio)"


def test_write_chunk_handles_odd_bytes_mute_and_portaudio_errors():
    with patch("core.audio_output.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.RawOutputStream.return_value = mock_stream
        mock_sd.query_devices.return_value = FAKE_DEVICES
        mgr = AudioOutputManager()

        assert mgr.start("CABLE Input (VB-Audio Virtual Cable)") is True
        assert mgr.is_active is True

        # Odd byte length rejected safely
        assert mgr.write_chunk(b"\x01") is False
        assert mgr.write_chunk(b"") is False

        # Valid 20ms chunk (1920 bytes)
        assert mgr.write_chunk(b"\x00\x00" * 960) is True
        mock_stream.write.assert_called_once()

        # Muted mode skips writing without error
        mgr.set_muted(True)
        assert mgr.write_chunk(b"\x00\x00" * 960) is False
        mgr.set_muted(False)

        # Silenced device stops active stream cleanly
        assert mgr.set_device(SILENCED_DEVICE_LABEL) is True
        assert mgr.is_active is False

        # Re-open and simulate runtime PortAudio error
        assert mgr.set_device("CABLE Input (VB-Audio Virtual Cable)") is True
        mock_stream.write.side_effect = RuntimeError("Device unplugged")
        assert mgr.write_chunk(b"\x00\x00" * 960) is False
        assert mgr.is_active is False
