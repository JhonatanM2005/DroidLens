# Audio Capture and Bidirectional Stream Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend DroidLens to capture 48 kHz mono 16-bit PCM microphone audio on Android, multiplex video/audio/control packets over the USB ADB TCP tunnel (`APCM` v2, 21-byte header), route audio output on Windows via `sounddevice`, and support bidirectional switching between `VIDEO_ONLY`, `AUDIO_ONLY`, and `AUDIO_VIDEO` modes from both Android and Windows UIs.

**Architecture:** The `APCM` header gains a 1-byte `packet_type` field (`>4sBIQI`, 21 bytes total) to multiplex `VIDEO_JPEG` (`0x01`), `AUDIO_PCM` (`0x02`), and `CONTROL_MODE` (`0x03`) over the single TCP connection on `127.0.0.1:8080`. Android's `CamStreamService` coordinates `CameraManager` and a new `AudioCaptureManager` based on the active `StreamMode`, while Windows' `StreamReceiver` demultiplexes audio chunks into `AudioOutputManager` (with auto-detection of `"CABLE Input"` for VB-Audio Virtual Cable) and synchronizes mode changes with `DroidLensApp`.

**Tech Stack:** Python 3.11 (`sounddevice>=0.4.6`, `numpy`, `opencv-python`, `customtkinter`, `pytest`), Kotlin / Android SDK 34 (`AudioRecord`, `CameraX`, `LifecycleService`, `JUnit4`).

**Spec:** `docs/superpowers/specs/2026-10-12-audio-and-stream-modes-design.md`

## Global Constraints

- Binary header format: Big-Endian `>4sBIQI` (`MAGIC = b"APCM"`, `PACKET_TYPE: uint8`, `SEQ_ID: uint32`, `TIMESTAMP_MS: uint64`, `LENGTH: uint32`), `HEADER_SIZE = 21` bytes.
- Packet types: `VIDEO_JPEG = 1`, `AUDIO_PCM = 2`, `CONTROL_MODE = 3`.
- Stream modes: `VIDEO_ONLY = 1` (`"Solo Cámara"`), `AUDIO_ONLY = 2` (`"Solo Micrófono"`), `AUDIO_VIDEO = 3` (`"Cámara + Micrófono"`).
- Audio PCM format: `48000 Hz`, `1 channel (mono)`, `16-bit signed integer little-endian`, `960 samples` (`1920 bytes` = `20 ms`) per packet.
- Mode updates received from the remote peer MUST call `setStreamMode(..., notifyRemote=False)` / `set_stream_mode(..., notify_remote=False)` to prevent infinite echo loops.

## Review Focus

- Unknown `packet_type` byte in `parse_header` (e.g., `0x99`): `parse_header` must return `None` so `StreamReceiver` triggers stream resynchronization instead of dispatching corrupt packets.
- Invalid `StreamMode` byte in `CONTROL_MODE` payload (e.g., `b"\x00"` or empty payload): `parse_control_mode` must return `None` and `StreamReceiver` must ignore it without crashing.
- Odd-length or oversized PCM buffer passed to `AudioOutputManager.write_chunk`: must be ignored or truncated safely without throwing inside the receiver thread.
- `sounddevice` raising an exception during stream open or `write`: `AudioOutputManager` must catch the exception, disable the stream, and return `False` without crashing `StreamReceiver`.
- Mode set to `AUDIO_ONLY` in `StreamReceiver`: `get_latest_frame` must return `FrameStatus.AUDIO_ONLY_MODE` so the UI renders the dedicated audio standby screen instead of treating the connection as expired/disconnected.

---

### Task 1: Python Protocol `APCM` v2 (`pc_client/src/core/protocol.py`)

**Files:**
- Modify: `pc_client/src/core/protocol.py`
- Test: `pc_client/tests/test_protocol.py`

**Interfaces:**
- Consumes: Python stdlib `struct`, `enum.IntEnum`
- Produces:
  - `MAGIC = b"APCM"`
  - `HEADER_FORMAT = ">4sBIQI"`
  - `HEADER_SIZE = 21`
  - `class PacketType(IntEnum)`: `VIDEO_JPEG = 1`, `AUDIO_PCM = 2`, `CONTROL_MODE = 3`
  - `class StreamMode(IntEnum)`: `VIDEO_ONLY = 1`, `AUDIO_ONLY = 2`, `AUDIO_VIDEO = 3`
  - `pack_frame(frame_id: int, timestamp_ms: int, payload_bytes: bytes, packet_type: int = PacketType.VIDEO_JPEG) -> bytes`
  - `pack_control_mode(mode: StreamMode, seq_id: int = 0, timestamp_ms: int = 0) -> bytes`
  - `parse_header(header_bytes: bytes) -> Optional[Tuple[int, int, int, int]]` returning `(packet_type, seq_id, timestamp_ms, length)` or `None` if `len < 21`, `magic != MAGIC`, or `packet_type not in (1, 2, 3)`
  - `parse_control_mode(payload: bytes) -> Optional[StreamMode]`

- [ ] **Step 1: Write failing tests in `pc_client/tests/test_protocol.py`**

```python
from core.protocol import (
    MAGIC, HEADER_SIZE, PacketType, StreamMode,
    pack_frame, pack_control_mode, parse_header, parse_control_mode
)

def test_pack_and_parse_valid_header():
    packet = pack_frame(42, 1718000000123, b"\xFF\xD8\xFF\xD9")
    assert HEADER_SIZE == 21
    assert len(packet) == 21 + 4
    assert parse_header(packet[:HEADER_SIZE]) == (PacketType.VIDEO_JPEG, 42, 1718000000123, 4)

def test_pack_and_parse_audio_and_control():
    pcm = b"\x00\x01" * 960
    audio_pkt = pack_frame(7, 5000, pcm, packet_type=PacketType.AUDIO_PCM)
    assert parse_header(audio_pkt[:HEADER_SIZE]) == (PacketType.AUDIO_PCM, 7, 5000, 1920)

    ctrl_pkt = pack_control_mode(StreamMode.AUDIO_ONLY, seq_id=3, timestamp_ms=9000)
    ptype, sid, ts, length = parse_header(ctrl_pkt[:HEADER_SIZE])
    assert (ptype, sid, ts, length) == (PacketType.CONTROL_MODE, 3, 9000, 1)
    assert parse_control_mode(ctrl_pkt[HEADER_SIZE:]) == StreamMode.AUDIO_ONLY

def test_reject_unknown_packet_type_and_invalid_control_mode():
    bad_header = struct.pack(">4sBIQI", MAGIC, 99, 1, 1000, 10)
    assert parse_header(bad_header) is None
    assert parse_control_mode(b"") is None
    assert parse_control_mode(b"\x99") is None
```

- [ ] **Step 2: Run `pytest` to verify tests fail**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_protocol.py -v`
Expected: FAIL with `ImportError: cannot import name 'PacketType'`

- [ ] **Step 3: Implement `PacketType`, `StreamMode`, `pack_frame`, `pack_control_mode`, `parse_header`, and `parse_control_mode` in `pc_client/src/core/protocol.py`**

- [ ] **Step 4: Run `pytest` to verify tests pass**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add pc_client/src/core/protocol.py pc_client/tests/test_protocol.py
git commit -m "feat(protocol): upgrade APCM binary header to v2 with packet types and stream modes"
```

---

### Task 2: Windows Audio Output Manager (`pc_client/src/core/audio_output.py`)

**Files:**
- Modify: `pc_client/requirements.txt`
- Modify: `pc_client/droidlens.spec`
- Create: `pc_client/src/core/audio_output.py`
- Create: `pc_client/tests/test_audio_output.py`

**Interfaces:**
- Consumes: `sounddevice`
- Produces:
  - `SAMPLE_RATE = 48000`, `CHANNELS = 1`, `CHUNK_SAMPLES = 960`, `CHUNK_BYTES = 1920`
  - `SILENCED_DEVICE_LABEL = "Silenciado"`
  - `class AudioOutputManager`:
    - `list_output_devices() -> List[Dict[str, Any]]` (each item `{"index": int, "name": str}`)
    - `find_preferred_device() -> Optional[str]` (returns first device name containing `"cable input"` case-insensitively, else default output device name)
    - `start(device_name: Optional[str] = None) -> bool`
    - `stop() -> None`
    - `set_device(device_name: Optional[str]) -> bool`
    - `set_muted(muted: bool) -> None`
    - `write_chunk(pcm_bytes: bytes) -> bool`

- [ ] **Step 1: Install `sounddevice` in virtualenv and add to `pc_client/requirements.txt` and `pc_client/droidlens.spec`**

Run: `& "pc_client\.venv\Scripts\pip.exe" install "sounddevice>=0.4.6"`

- [ ] **Step 2: Write failing tests in `pc_client/tests/test_audio_output.py`**

```python
from unittest.mock import MagicMock, patch
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

def test_write_chunk_handles_odd_bytes_and_portaudio_errors():
    with patch("core.audio_output.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.RawOutputStream.return_value = mock_stream
        mock_sd.query_devices.return_value = FAKE_DEVICES
        mgr = AudioOutputManager()
        assert mgr.start("CABLE Input (VB-Audio Virtual Cable)") is True
        assert mgr.write_chunk(b"\x01") is False  # Odd byte length rejected
        assert mgr.write_chunk(b"\x00\x00" * 960) is True
        mock_stream.write.side_effect = RuntimeError("Device unplugged")
        assert mgr.write_chunk(b"\x00\x00" * 960) is False
        assert mgr.is_active is False
```

- [ ] **Step 3: Run `pytest` to verify tests fail**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_audio_output.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.audio_output'`

- [ ] **Step 4: Implement `AudioOutputManager` in `pc_client/src/core/audio_output.py`**

- [ ] **Step 5: Run `pytest` to verify tests pass**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_audio_output.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```powershell
git add pc_client/requirements.txt pc_client/droidlens.spec pc_client/src/core/audio_output.py pc_client/tests/test_audio_output.py
git commit -m "feat(pc-audio): add AudioOutputManager with VB-Cable auto-detection and fault tolerance"
```

---

### Task 3: Bidirectional `StreamReceiver` & Audio Standby Frame (`pc_client/src/core/receiver.py`, `processor.py`)

**Files:**
- Modify: `pc_client/src/core/receiver.py`
- Modify: `pc_client/src/core/processor.py`
- Modify: `pc_client/tests/test_receiver.py`
- Modify: `pc_client/tests/test_processor.py`

**Interfaces:**
- Consumes: `PacketType`, `StreamMode`, `pack_control_mode`, `parse_header`, `parse_control_mode` from `core.protocol`
- Produces:
  - `FrameStatus.AUDIO_ONLY_MODE = "audio_only"`
  - `StreamReceiver(host="127.0.0.1", port=8080, on_audio_chunk: Optional[Callable[[bytes], None]] = None, on_mode_changed: Optional[Callable[[StreamMode], None]] = None)`
  - `StreamReceiver.stream_mode: StreamMode` (default `StreamMode.AUDIO_VIDEO`)
  - `StreamReceiver.set_stream_mode(mode: StreamMode, notify_remote: bool = True) -> bool`
  - `StreamReceiver.send_control_mode(mode: StreamMode) -> bool`
  - `FrameProcessor.generate_audio_only_frame(audio_active: bool = True) -> np.ndarray`

- [ ] **Step 1: Write failing tests in `pc_client/tests/test_receiver.py` and `pc_client/tests/test_processor.py`**

```python
from core.protocol import PacketType, StreamMode, pack_frame, pack_control_mode

def test_receiver_dispatches_audio_and_control_packets():
    received_audio = []
    received_modes = []
    receiver = StreamReceiver(
        on_audio_chunk=lambda b: received_audio.append(b),
        on_mode_changed=lambda m: received_modes.append(m),
    )
    receiver.connected = True
    receiver._handle_packet(PacketType.AUDIO_PCM, 1, 1000, b"\x01\x02" * 960)
    assert len(received_audio) == 1

    ctrl_payload = pack_control_mode(StreamMode.AUDIO_ONLY)[21:]
    receiver._handle_packet(PacketType.CONTROL_MODE, 2, 1005, ctrl_payload)
    assert receiver.stream_mode == StreamMode.AUDIO_ONLY
    assert received_modes == [StreamMode.AUDIO_ONLY]
    assert receiver.get_latest_frame(timeout=0.01).status == FrameStatus.AUDIO_ONLY_MODE
```

- [ ] **Step 2: Run `pytest` to verify tests fail**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests/test_receiver.py pc_client/tests/test_processor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement packet demultiplexing, `send_control_mode`, and `AUDIO_ONLY_MODE` in `receiver.py`, plus `generate_audio_only_frame` in `processor.py`**

- [ ] **Step 4: Run `pytest` to verify tests pass**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add pc_client/src/core/receiver.py pc_client/src/core/processor.py pc_client/tests/test_receiver.py pc_client/tests/test_processor.py
git commit -m "feat(receiver): demultiplex audio and bidirectional control packets in StreamReceiver"
```

---

### Task 4: Windows UI Controls for Stream Mode and Audio Device (`pc_client/src/ui/app_window.py`)

**Files:**
- Modify: `pc_client/src/ui/app_window.py`

**Interfaces:**
- Consumes: `StreamMode` (`core.protocol`), `AudioOutputManager`, `SILENCED_DEVICE_LABEL` (`core.audio_output`), `FrameStatus.AUDIO_ONLY_MODE` (`core.receiver`)
- Produces:
  - Mode selector `CTkOptionMenu` (`"Cámara + Micrófono"`, `"Solo Cámara"`, `"Solo Micrófono"`)
  - Audio output selector `CTkOptionMenu` with refresh button and persistence in `settings.json` (`"stream_mode"`, `"audio_output_device"`)

- [ ] **Step 1: Integrate `AudioOutputManager` and mode/audio selectors into `DroidLensApp` in `pc_client/src/ui/app_window.py`**

Wire `on_audio_chunk=self.audio_output.write_chunk` and `on_mode_changed=self._on_remote_mode_changed`. Render `self.processor.generate_audio_only_frame()` when `frame_result.status == FrameStatus.AUDIO_ONLY_MODE`.

- [ ] **Step 2: Run full Python test suite**

Run: `& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests -v`
Expected: PASS

- [ ] **Step 3: Commit**

```powershell
git add pc_client/src/ui/app_window.py
git commit -m "feat(pc-ui): add stream mode selector and audio output routing controls"
```

---

### Task 5: Android Protocol v2, `StreamMode`, and `AudioCaptureManager`

**Files:**
- Create: `android/app/src/main/java/com/droidlens/app/camera/StreamMode.kt`
- Modify: `android/app/src/main/java/com/droidlens/app/network/PacketProtocol.kt`
- Create: `android/app/src/main/java/com/droidlens/app/audio/AudioCaptureManager.kt`
- Modify: `android/app/src/test/java/com/droidlens/app/PacketProtocolTest.kt`

**Interfaces:**
- Produces:
  - `enum class StreamMode(val code: Byte, val title: String)`: `VIDEO_ONLY(1, "Solo Cámara")`, `AUDIO_ONLY(2, "Solo Micrófono")`, `AUDIO_VIDEO(3, "Cámara + Micrófono")`, `companion object { fun fromCode(code: Byte): StreamMode? }`
  - `PacketProtocol`: `HEADER_SIZE = 21`, `TYPE_VIDEO = 1.toByte()`, `TYPE_AUDIO = 2.toByte()`, `TYPE_CONTROL_MODE = 3.toByte()`, `createHeader(packetType: Byte, frameId: Int, timestampMs: Long, payloadLength: Int): ByteArray`, `packControlMode(mode: StreamMode, seqId: Int = 0): ByteArray`, `parseHeader(bytes: ByteArray): Header?`
  - `class AudioCaptureManager(val onAudioChunk: (ByteArray) -> Unit)`: `start(): Boolean`, `stop()`

- [ ] **Step 1: Update `PacketProtocolTest.kt` with 21-byte header and `StreamMode` control packet tests**

```kotlin
@Test
fun testHeaderV2AndControlMode() {
    val header = PacketProtocol.createHeader(PacketProtocol.TYPE_AUDIO, 10, 5000L, 1920)
    assertEquals(21, header.size)
    val parsed = PacketProtocol.parseHeader(header)
    assertNotNull(parsed)
    assertEquals(PacketProtocol.TYPE_AUDIO, parsed!!.packetType)
    assertEquals(1920, parsed.payloadLength)

    val ctrl = PacketProtocol.packControlMode(StreamMode.AUDIO_ONLY, seqId = 2)
    val ctrlHeader = PacketProtocol.parseHeader(ctrl.sliceArray(0 until 21))
    assertEquals(PacketProtocol.TYPE_CONTROL_MODE, ctrlHeader!!.packetType)
    assertEquals(StreamMode.AUDIO_ONLY, StreamMode.fromCode(ctrl[21]))
}
```

- [ ] **Step 2: Run Gradle unit test to verify it fails**

Run: `.\gradlew.bat testDebugUnitTest` (in `c:\Users\Usuario\Documents\AppCam\android`)
Expected: FAIL (compilation error on new `StreamMode` and `PacketProtocol` signatures)

- [ ] **Step 3: Implement `StreamMode.kt`, `PacketProtocol.kt`, and `AudioCaptureManager.kt`**

- [ ] **Step 4: Run Gradle unit test to verify it passes**

Run: `.\gradlew.bat testDebugUnitTest` (in `c:\Users\Usuario\Documents\AppCam\android`)
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: Commit**

```powershell
git add android/app/src/main/java/com/droidlens/app/camera/StreamMode.kt android/app/src/main/java/com/droidlens/app/network/PacketProtocol.kt android/app/src/main/java/com/droidlens/app/audio/AudioCaptureManager.kt android/app/src/test/java/com/droidlens/app/PacketProtocolTest.kt
git commit -m "feat(android-audio): implement APCM v2 protocol, StreamMode, and AudioCaptureManager"
```

---

### Task 6: Android `StreamServer`, `CamStreamService`, and `MainActivity` Integration

**Files:**
- Modify: `android/app/src/main/AndroidManifest.xml`
- Modify: `android/app/src/main/java/com/droidlens/app/network/StreamServer.kt`
- Modify: `android/app/src/main/java/com/droidlens/app/camera/CameraManager.kt`
- Modify: `android/app/src/main/java/com/droidlens/app/service/CamStreamService.kt`
- Modify: `android/app/src/main/res/layout/activity_main.xml`
- Modify: `android/app/src/main/java/com/droidlens/app/MainActivity.kt`

**Interfaces:**
- Consumes: `StreamMode`, `PacketProtocol`, `AudioCaptureManager`
- Produces:
  - `StreamServer.sendAudio(pcmBytes: ByteArray)`, `StreamServer.sendControlMode(mode: StreamMode)`, and incoming `CONTROL_MODE` reader loop calling `ServerCallback.onRemoteModeChanged(mode: StreamMode)`
  - `CamStreamService.setStreamMode(mode: StreamMode, notifyRemote: Boolean = true)`
  - `MainActivity` mode cycling button (`btnStreamMode`) and `RECORD_AUDIO` permission handling with fallback to `VIDEO_ONLY`

- [ ] **Step 1: Update `AndroidManifest.xml`, `StreamServer.kt`, `CameraManager.kt`, `CamStreamService.kt`, `activity_main.xml`, and `MainActivity.kt`**

- [ ] **Step 2: Run Android unit tests and build `assembleDebug`**

Run: `.\gradlew.bat testDebugUnitTest assembleDebug` (in `c:\Users\Usuario\Documents\AppCam\android`)
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: Copy updated APK to root `DroidLens.apk` and rebuild Windows distribution**

Run:
```powershell
Copy-Item "android\app\build\outputs\apk\debug\app-debug.apk" "DroidLens.apk" -Force
& "pc_client\.venv\Scripts\python.exe" scripts/build_windows_dist.py
```

- [ ] **Step 4: Commit all changes**

```powershell
git add android/ DroidLens.apk
git commit -m "feat(android): integrate bidirectional stream modes and microphone capture in service and UI"
```
