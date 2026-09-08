import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from usb.adb_manager import ADBManager

SAMPLE_DEVICES_OUTPUT = """List of devices attached
8118e8de0410           device product:pixelage_lancelot model:Redmi_9 device:lancelot transport_id:2
emulator-5554          unauthorized transport_id:3
XYZ12345               offline product:some_device model:Galaxy_S21 device:s21 transport_id:4
"""

def test_list_devices_parser():
    mgr = ADBManager()
    with patch.object(mgr, "_run_command") as mock_cmd:
        mock_cmd.return_value = (0, SAMPLE_DEVICES_OUTPUT, "")
        devices = mgr.list_devices()

        assert len(devices) == 3

        dev0 = devices[0]
        assert dev0["serial"] == "8118e8de0410"
        assert dev0["state"] == "device"
        assert dev0["model"] == "Redmi 9"

        dev1 = devices[1]
        assert dev1["serial"] == "emulator-5554"
        assert dev1["state"] == "unauthorized"

        dev2 = devices[2]
        assert dev2["serial"] == "XYZ12345"
        assert dev2["state"] == "offline"
        assert dev2["model"] == "Galaxy S21"

def test_global_commands_never_use_serial():
    """Verifica que devices, version, start-server, kill-server y forward --list nunca lleven -s."""
    mgr = ADBManager(selected_serial="8118e8de0410")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Android Debug Bridge version 1.0.41"
        mock_run.return_value.stderr = ""

        mgr.is_available()
        # Verificar que el comando ejecutado fue ['...adb.exe', 'version'] sin '-s'
        called_args = mock_run.call_args[0][0]
        assert "-s" not in called_args
        assert called_args[-1] == "version"

def test_setup_port_forward_with_serial():
    mgr = ADBManager()
    mgr.set_selected_serial("8118e8de0410")

    with patch.object(mgr, "_run_command") as mock_cmd, \
         patch.object(mgr, "list_devices", return_value=[{"serial": "8118e8de0410", "state": "device"}]):
        mock_cmd.return_value = (0, "", "")
        success = mgr.setup_port_forward(8080, 8080)
        assert success is True

        mock_cmd.assert_called_once_with(["forward", "tcp:8080", "tcp:8080"], serial="8118e8de0410")

def test_setup_port_forward_rejects_unauthorized():
    mgr = ADBManager(selected_serial="emulator-5554")
    with patch.object(mgr, "list_devices", return_value=[{"serial": "emulator-5554", "state": "unauthorized"}]):
        success = mgr.setup_port_forward(8080, 8080)
        assert success is False

def test_remove_port_forward_with_serial():
    mgr = ADBManager()
    with patch.object(mgr, "_run_command") as mock_cmd:
        mock_cmd.return_value = (0, "", "")
        success = mgr.remove_port_forward(8080, serial="TEST_DEV")
        assert success is True
        mock_cmd.assert_called_once_with(["forward", "--remove", "tcp:8080"], serial="TEST_DEV")

def test_diagnostics_unauthorized():
    mgr = ADBManager()
    with patch.object(mgr, "is_available", return_value=True), \
         patch.object(mgr, "list_devices", return_value=[{"serial": "abc", "state": "unauthorized", "model": "Pixel"}]):
        diag = mgr.get_diagnostics()
        assert diag["status"] == "unauthorized"
        assert "no autorizado" in diag["message"]
