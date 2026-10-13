# DroidLens Native Windows 11 IMFVirtualCamera Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native 64-bit C++ Windows 11 `IMFVirtualCamera` driver (`driver/DroidLensMF.dll`), integrate it with `VirtualCameraManager` via `ctypes` and shared memory, expose a backend selector in the desktop UI, and compile the DLL automatically in GitHub Actions.

**Architecture:** A unified 64-bit C++ COM DLL (`DroidLensMF.dll`) implements both the `IMFMediaSourceEx` / `IMFMediaStream` loaded out-of-process by `Windows Camera Frame Server` (`CLSID {D819C48B-A324-4B2D-9B8A-7012354A0002}`) and the `dl_mf_*` C exports called by `DroidLens.exe` over `ctypes`, exchanging `RGB32` frames through a named shared memory mapping (`Local\DroidLens_MF_SharedVideo`). `VirtualCameraManager` abstracts both `VirtualCamBackend.WINDOWS_MF` and `VirtualCamBackend.UNITY_CAPTURE` behind a unified interface selectable in `DroidLensApp`.

**Tech Stack:** C++17 (MSVC x64, Windows 11 SDK `mfplat.lib`, `mfuuid.lib`, `mf.lib`, `mfsensorgroup.lib`, `shlwapi.lib`), Python 3.11 (`ctypes`, `numpy`, `cv2`, `customtkinter`, `pytest`), GitHub Actions (`windows-latest`, `ilammy/msvc-dev-cmd@v1`).

**Spec:** `docs/superpowers/specs/2026-10-12-imfvirtualcamera-driver-design.md`

## Global Constraints

- Virtual camera friendly name on Windows 11: `"DroidLens Virtual Camera"`
- MediaSource COM CLSID: `{D819C48B-A324-4B2D-9B8A-7012354A0002}`
- Named shared memory path: `Local\DroidLens_MF_SharedVideo` with 32-byte header (`magic = 0x444C4D46`, `version = 1`) + `1920 * 1080 * 4` bytes pixel payload
- Exported C functions (`__stdcall` / `extern "C"`): `dl_mf_is_supported`, `dl_mf_start`, `dl_mf_send_frame`, `dl_mf_stop`
- UI backend labels: `"Windows 11 Nativo (DroidLens Camera)"` (`VirtualCamBackend.WINDOWS_MF`) and `"DirectShow (Unity Video Capture)"` (`VirtualCamBackend.UNITY_CAPTURE`)

## Review Focus

- Non-contiguous or wrong-dtype `numpy.ndarray` passed to `MFVirtualCamBridge.send_frame` must be converted to contiguous `uint8` `BGR24` before passing its pointer to `dl_mf_send_frame`.
- Missing `DroidLensMF.dll` on disk or unregistered CLSID (`dl_mf_is_supported() == 0`) must return `False` from `VirtualCameraManager.start()` and set a clear `last_error` without raising an unhandled `OSError`.
- Live backend switching (`set_backend`) while `VirtualCameraManager.is_active` is `True` must stop the previous backend before starting the new one and rollback/report cleanly if the new backend fails to start.
- Shared memory read in `DroidLensMediaStream::RequestSample` when the producer has not written any frame yet (`frame_index == 0` or mapping closed) must output a valid dark standby `RGB32` buffer rather than uninitialized memory.
- Dimension mismatch between incoming frame and configured `width x height` must resize the frame before calling `dl_mf_send_frame`.

---

### Task 1: Python Multi-Backend `VirtualCameraManager` & `MFVirtualCamBridge`

**Files:**
- Modify: `pc_client/src/core/virtual_camera.py`
- Test: `pc_client/tests/test_virtual_camera.py`

**Interfaces:**
- Consumes: `utils.paths.find_driver_script(script_name: str) -> str`
- Produces:
  - `VirtualCamBackend(str, Enum)`: `WINDOWS_MF = "mf_virtualcam"`, `UNITY_CAPTURE = "unitycapture"`
  - `VCAM_BACKEND_LABELS: Dict[VirtualCamBackend, str]` and `LABEL_TO_VCAM_BACKEND: Dict[str, VirtualCamBackend]`
  - `MFVirtualCamBridge(dll_path: Optional[str] = None, dll_loader: Optional[Callable] = None)` with `.is_supported() -> bool`, `.start(width: int, height: int, fps: int) -> bool`, `.send_frame(bgr_frame: np.ndarray) -> bool`, `.stop() -> None`
  - `VirtualCameraManager(width: int = 1280, height: int = 720, fps: int = 30, backend: VirtualCamBackend = VirtualCamBackend.WINDOWS_MF, mf_bridge: Optional[MFVirtualCamBridge] = None)` with `.set_backend(backend: VirtualCamBackend) -> bool`, `.device_name -> str`, `.last_error -> str`

- [ ] **Step 1: Write failing tests in `pc_client/tests/test_virtual_camera.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_virtual_camera.py -v`
Expected: FAIL with `ImportError: cannot import name 'VirtualCamBackend'`

- [ ] **Step 3: Implement `VirtualCamBackend`, `MFVirtualCamBridge`, and multi-backend `VirtualCameraManager` in `pc_client/src/core/virtual_camera.py`**

Load `DroidLensMF.dll` via `ctypes.WinDLL`, configure `argtypes`/`restype` for `dl_mf_is_supported`, `dl_mf_start`, `dl_mf_send_frame(ctypes.POINTER(ctypes.c_uint8), ctypes.c_int, ctypes.c_int)`, and `dl_mf_stop`, ensure `np.ascontiguousarray(frame, dtype=np.uint8)` before `ctypes.data_as`, and maintain `sleep_until_next_frame` pacing for `UNITY_CAPTURE` while letting the caller's `_video_loop` pace `WINDOWS_MF`.

- [ ] **Step 4: Run test to verify it passes**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_virtual_camera.py -v`
Expected: PASS (`3 passed`)

- [ ] **Step 5: Commit**

```bash
git add pc_client/src/core/virtual_camera.py pc_client/tests/test_virtual_camera.py
git commit -m "feat(pc): add multi-backend VirtualCameraManager with ctypes IMFVirtualCamera bridge"
```

---

### Task 2: Desktop UI Backend Selector & One-Click Driver Registration

**Files:**
- Modify: `pc_client/src/ui/app_window.py`

**Interfaces:**
- Consumes: `VirtualCamBackend`, `VCAM_BACKEND_LABELS`, `LABEL_TO_VCAM_BACKEND` from `core.virtual_camera`
- Produces:
  - `self.vcam_backend_menu` (`CTkOptionMenu`) and `self.btn_install_driver` (`CTkButton`) in `DroidLensApp`
  - `"vcam_backend"` persisted in `settings.json`

- [ ] **Step 1: Add `"vcam_backend"` setting, backend selector menu, and driver registration button in `pc_client/src/ui/app_window.py`**

Initialize `self.vcam` with the saved backend from `settings.json` (defaulting to `VCAM_BACKEND_LABELS[VirtualCamBackend.WINDOWS_MF]`), add `self.vcam_backend_menu` above `self.vcam_switch`, update `self.vcam_desc` dynamically with `self.vcam.device_name` or `self.vcam.last_error`, and show `self.btn_install_driver` (`📥 Registrar Driver de Cámara (Admin)`) when `self.vcam.start()` fails so the user can trigger `driver\install_driver.bat` with UAC elevation from the UI.

- [ ] **Step 2: Verify UI module imports and existing test suite pass**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests -v`
Expected: PASS (`33 passed`)

- [ ] **Step 3: Commit**

```bash
git add pc_client/src/ui/app_window.py
git commit -m "feat(ui): add virtual camera engine selector and driver registration button"
```

---

### Task 3: C++ `DroidLensMF.dll` (`IMFVirtualCamera` + COM `IMFMediaSourceEx` + Shared Memory) & Driver Scripts

**Files:**
- Create: `driver/mf_vcam/DroidLensMF.cpp`
- Create: `driver/mf_vcam/DroidLensMF.def`
- Create: `driver/mf_vcam/build_mf_driver.bat`
- Modify: `driver/install_driver.bat`
- Modify: `driver/uninstall_driver.bat`

**Interfaces:**
- Produces:
  - `driver/mf_vcam/DroidLensMF.cpp` implementing:
    - Shared memory `Local\DroidLens_MF_SharedVideo` (`SharedFrameHeader` + `RGB32` pixel buffer)
    - COM `DroidLensMediaSource` (`IMFMediaSourceEx`, `IMFGetService`) & `DroidLensMediaStream` (`IMFMediaStream2`) registered under `{D819C48B-A324-4B2D-9B8A-7012354A0002}`
    - `DllGetClassObject`, `DllCanUnloadNow`, `DllRegisterServer`, `DllUnregisterServer`
    - `dl_mf_is_supported`, `dl_mf_start`, `dl_mf_send_frame`, `dl_mf_stop`
  - Updated `driver/install_driver.bat` and `driver/uninstall_driver.bat` registering both `UnityCaptureFilter64.dll` and `DroidLensMF.dll`

- [ ] **Step 1: Create `driver/mf_vcam/DroidLensMF.def` and `driver/mf_vcam/DroidLensMF.cpp`**

Implement the complete C++17 COM server and Media Foundation Virtual Camera controller using Windows 11 `MFCreateVirtualCamera` (dynamically resolved via `GetProcAddress(LoadLibraryW(L"mfsensorgroup.dll"), "MFCreateVirtualCamera")` so the DLL also loads safely on older Windows builds without crashing the loader) and `IMFMediaSourceEx`/`IMFMediaStream` serving `MFVideoFormat_RGB32` frames from `Local\DroidLens_MF_SharedVideo`.

- [ ] **Step 2: Create `driver/mf_vcam/build_mf_driver.bat` and update `driver/install_driver.bat` / `driver/uninstall_driver.bat`**

`build_mf_driver.bat` invokes `cl.exe /std:c++17 /O2 /LD /EHsc DroidLensMF.cpp /Fe:..\DroidLensMF.dll /link /DEF:DroidLensMF.def mfplat.lib mfuuid.lib mf.lib shlwapi.lib ole32.lib advapi32.lib user32.lib`. Update `install_driver.bat` and `uninstall_driver.bat` to register/unregister `DroidLensMF.dll` alongside `UnityCaptureFilter64.dll`.

- [ ] **Step 3: Commit**

```bash
git add driver/mf_vcam/DroidLensMF.cpp driver/mf_vcam/DroidLensMF.def driver/mf_vcam/build_mf_driver.bat driver/install_driver.bat driver/uninstall_driver.bat
git commit -m "feat(driver): implement Windows 11 IMFVirtualCamera C++ COM MediaSource and shared memory bridge"
```

---

### Task 4: CI/CD Cloud Compilation of `DroidLensMF.dll` & End-to-End Verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `installer/droidlens.iss`

**Interfaces:**
- Consumes: `driver/mf_vcam/build_mf_driver.bat`
- Produces:
  - Compiled `driver/DroidLensMF.dll` built in GitHub Actions `windows-build` job before `scripts/build_windows_dist.py` runs
  - Dedicated `DroidLensMF-Driver-DLL` workflow artifact so we can download `DroidLensMF.dll` directly into the local `driver/` directory

- [ ] **Step 1: Add MSVC setup and `build_mf_driver.bat` step to `.github/workflows/ci.yml` and update `installer/droidlens.iss` description**

Configure `ilammy/msvc-dev-cmd@v1` (`arch: x64`) in `.github/workflows/ci.yml`, run `cmd /c driver\mf_vcam\build_mf_driver.bat`, verify `driver/DroidLensMF.dll` exists, upload `DroidLensMF.dll` as artifact `DroidLensMF-Driver-DLL`, and include it in the Windows installer/portable build.

- [ ] **Step 2: Commit, push to `origin/master`, wait for GitHub Actions `windows-build` to compile `DroidLensMF.dll`, and download `DroidLensMF.dll` to `driver/`**

Run:
```powershell
git add .github/workflows/ci.yml installer/droidlens.iss
git commit -m "ci(driver): compile native DroidLensMF.dll with MSVC x64 in GitHub Actions"
git push origin master
```
Monitor the workflow run with `gh run watch`, download `DroidLensMF-Driver-DLL` into `driver/DroidLensMF.dll`, and verify `ctypes.WinDLL("driver/DroidLensMF.dll")` loads cleanly on the local Windows 11 machine.
