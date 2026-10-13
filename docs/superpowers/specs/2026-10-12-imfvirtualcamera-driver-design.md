# DroidLens Native Windows 11 IMFVirtualCamera Driver Specification

## 1. Overview & Goal
Implement a native Windows 11 Media Foundation Virtual Camera driver (`IMFVirtualCamera`) for DroidLens inside a unified 64-bit C++ COM library (`driver/DroidLensMF.dll`), connected via named shared memory and a `ctypes` C bridge to [`VirtualCameraManager`](file:///c:/Users/Usuario/Documents/AppCam/pc_client/src/core/virtual_camera.py), with an explicit engine selector in the Windows desktop UI allowing users to choose between **Windows 11 Native (`IMFVirtualCamera`)** and **DirectShow (`UnityCapture`)**.

## 2. Requirements & Constraints
1. **Windows 11 Media Foundation Compatibility:**
   - Expose a system-recognized Media Foundation virtual camera named **`"DroidLens Virtual Camera"`** visible to the Windows 11 Camera app, UWP/WinUI applications, Microsoft Teams, Zoom, Discord, OBS Studio, and Chromium/Firefox browsers.
   - Use `MFCreateVirtualCamera` with:
     - `MFVirtualCameraType_SoftwareCameraSource`
     - `MFVirtualCameraLifetime_Session` (camera lifecycle bound to the active DroidLens session; automatically cleaned up on stop/exit)
     - `MFVirtualCameraAccess_CurrentUser` (allows starting/stopping the virtual camera at runtime without requiring UAC elevation on every app launch)
2. **COM MediaSource Registration (`HKLM`):**
   - `Windows Camera Frame Server` (`svchost.exe -k CameraFrameServer`) loads the custom `IMFMediaSourceEx` out-of-process.
   - Register CLSID `{D819C48B-A324-4B2D-9B8A-7012354A0002}` under `HKLM\SOFTWARE\Classes\CLSID\{D819C48B-A324-4B2D-9B8A-7012354A0002}\InprocServer32` with `ThreadingModel = Both` during `driver/install_driver.bat` (`regsvr32 /s DroidLensMF.dll`).
3. **Inter-Process Frame Transport (Shared Memory):**
   - Transport BGR24 frames from the Python `DroidLens.exe` process to the `FrameServer` COM instance using a named file mapping `Local\DroidLens_MF_SharedVideo`.
   - Support resolutions up to `1920x1080` (`RGB32` / `ARGB32` media type for universal Media Foundation sink compatibility without color-space artifacts).
4. **UI Engine Selector & Persistence:**
   - Provide a dropdown selector in [`pc_client/src/ui/app_window.py`](file:///c:/Users/Usuario/Documents/AppCam/pc_client/src/ui/app_window.py) to switch between:
     - `"Windows 11 Nativo (DroidLens Camera)"` (`VirtualCamBackend.WINDOWS_MF`)
     - `"DirectShow (Unity Video Capture)"` (`VirtualCamBackend.UNITY_CAPTURE`)
   - Persist the selected backend in `settings.json` under `"vcam_backend"`.
5. **Cloud Compilation in CI/CD:**
   - Compile `driver/mf_vcam/DroidLensMF.cpp` in GitHub Actions (`windows-latest` with MSVC x64 and Windows 11 SDK) before packaging PyInstaller/Inno Setup, and publish `DroidLensMF.dll` as a build artifact so local environments do not require a multi-gigabyte Visual Studio C++ SDK installation.

## 3. Shared Memory & C Bridge Contract

### 3.1 Named Shared Memory Layout (`Local\DroidLens_MF_SharedVideo`)
Fixed 32-byte header followed by `1920 * 1080 * 4` bytes (`8,294,400` bytes) of bottom-up or top-down `RGB32` (`B, G, R, 0xFF`) pixel data:

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0..3` | `magic` | `uint32` | 4 B | `0x444C4D46` (`'DLMF'`) |
| `4..7` | `version` | `uint32` | 4 B | `1` |
| `8..11` | `width` | `uint32` | 4 B | Active frame width (e.g., `1280`, `1920`, `854`) |
| `12..15` | `height` | `uint32` | 4 B | Active frame height (e.g., `720`, `1080`, `480`) |
| `16..19` | `fps` | `uint32` | 4 B | Target frame rate (e.g., `30`, `24`) |
| `20..23` | `stride` | `uint32` | 4 B | Row stride in bytes (`width * 4`) |
| `24..31` | `frame_index` | `uint64` | 8 B | Monotonically increasing frame counter |
| `32..N` | `pixels` | `uint8[]` | `width * height * 4` | `RGB32` (`BGRA`) pixel buffer |

### 3.2 Exported C Functions in `DroidLensMF.dll`
- `int __stdcall dl_mf_is_supported(void)`:
  - Returns `1` if running on Windows 11+ (`MFCreateVirtualCamera` exists in `mfsensorgroup.dll`) AND CLSID `{D819C48B-A324-4B2D-9B8A-7012354A0002}` is registered in `HKCR\CLSID`; returns `0` otherwise.
- `int __stdcall dl_mf_start(int width, int height, int fps)`:
  - Initializes Media Foundation (`MFStartup`), creates/opens `Local\DroidLens_MF_SharedVideo`, writes the initial header, invokes `MFCreateVirtualCamera` and `IMFVirtualCamera::Start(nullptr)`. Returns `1` on success, `0` on failure.
- `int __stdcall dl_mf_send_frame(const uint8_t* bgr_bytes, int width, int height)`:
  - Converts contiguous `BGR24` (`width * height * 3`) bytes into `RGB32` (`BGRA`, `width * height * 4`) inside the shared memory buffer and atomically increments `frame_index`. Returns `1` on success, `0` on failure.
- `void __stdcall dl_mf_stop(void)`:
  - Calls `IMFVirtualCamera::Stop()`, `IMFVirtualCamera::Remove()`, releases the shared memory mapping, and calls `MFShutdown()`.

## 4. Component Architecture

### 4.1 Native C++ COM & Media Foundation Source (`driver/mf_vcam/`)
1. **`DroidLensMF.cpp` & `DroidLensMF.def`:**
   - **`DroidLensActivate` (`IMFActivate` / `IClassFactory`):** Instantiates `DroidLensMediaSource` when requested by `Windows Camera Frame Server` and sets `MF_DEVICESTREAM_ATTRIBUTE_FRAMESERVER_SHARED = 1`.
   - **`DroidLensMediaSource` (`IMFMediaSourceEx`, `IMFGetService`):**
     - Exposes a single video stream descriptor offering `MFVideoFormat_RGB32` (`1280x720 @ 30fps`, `1920x1080 @ 30fps`, `854x480 @ 24fps`).
     - Implements required camera attributes (`MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID`, `MF_VIRTUALCAMERA_PROVIDE_ASSOCIATED_CAMERA_SOURCES`).
   - **`DroidLensMediaStream` (`IMFMediaStream2`):**
     - Responds to `RequestSample(IUnknown* pToken)` by allocating an `IMFSample` + `IMFMediaBuffer`, copying the latest `RGB32` frame from `Local\DroidLens_MF_SharedVideo` (or rendering a dark slate standby pattern if `Local\DroidLens_MF_SharedVideo` is not open), stamping sample time and duration from the presentation clock, and firing `MEMediaSample`.
   - **Self-Registration (`DllRegisterServer` / `DllUnregisterServer`):**
     - Writes/removes `HKLM\SOFTWARE\Classes\CLSID\{D819C48B-A324-4B2D-9B8A-7012354A0002}` and `InprocServer32` pointing to the DLL path with `ThreadingModel = Both`.

### 4.2 Windows Driver Scripts (`driver/`)
- [`driver/install_driver.bat`](file:///c:/Users/Usuario/Documents/AppCam/driver/install_driver.bat): Registers `UnityCaptureFilter64.dll` / `UnityCaptureFilter32.dll` AND registers `DroidLensMF.dll` if present.
- [`driver/uninstall_driver.bat`](file:///c:/Users/Usuario/Documents/AppCam/driver/uninstall_driver.bat): Unregisters both filters cleanly.

### 4.3 Python Virtual Camera Abstraction (`pc_client/src/core/virtual_camera.py`)
1. **`VirtualCamBackend` (Enum):**
   - `WINDOWS_MF = "mf_virtualcam"`
   - `UNITY_CAPTURE = "unitycapture"`
2. **`MFVirtualCamBridge`:**
   - Locates `DroidLensMF.dll` via [`find_driver_script("DroidLensMF.dll")`](file:///c:/Users/Usuario/Documents/AppCam/pc_client/src/utils/paths.py#L67-L77).
   - Wraps `dl_mf_is_supported`, `dl_mf_start`, `dl_mf_send_frame`, and `dl_mf_stop` via `ctypes.WinDLL`.
3. **`VirtualCameraManager`:**
   - Accepts `backend: VirtualCamBackend` (defaulting to `WINDOWS_MF` if supported, or user selection).
   - `set_backend(backend: VirtualCamBackend) -> bool`: Switches backend cleanly, restarting the active session if `is_active` is `True`.
   - Exposes `device_name` property (`"DroidLens Virtual Camera"` for `WINDOWS_MF`, `"Unity Video Capture"` for `UNITY_CAPTURE`) and `last_error` string for clear UI diagnostics.

### 4.4 Windows Desktop UI (`pc_client/src/ui/app_window.py`)
- Adds a `CTkOptionMenu` (**"Motor de Cámara Virtual"**) above the virtual camera switch with options:
  - `"Windows 11 Nativo (DroidLens Camera)"`
  - `"DirectShow (Unity Video Capture)"`
- Adds a one-click **"📥 Registrar Driver de Cámara"** button that appears if the user tries to start a backend whose DLL is not yet registered in Windows.

## 5. Testing & Verification Plan
- **Python Unit Tests (`pc_client/tests/test_virtual_camera.py`):**
  - Verify `MFVirtualCamBridge` calls `dl_mf_start`, `dl_mf_send_frame` (with contiguous `uint8` `BGR` validation and resizing), and `dl_mf_stop` using a mocked ctypes library.
  - Verify `VirtualCameraManager` switches between `WINDOWS_MF` and `UNITY_CAPTURE` and updates `device_name`.
  - Verify graceful error reporting when `dl_mf_is_supported()` or `dl_mf_start()` returns `0`.
- **CI/CD Native Build Verification (`.github/workflows/ci.yml`):**
  - Compile `DroidLensMF.dll` with MSVC on `windows-latest`, verify zero compiler/linker errors, bundle it into `dist/`, and download the compiled `DroidLensMF.dll` artifact to `driver/DroidLensMF.dll`.
