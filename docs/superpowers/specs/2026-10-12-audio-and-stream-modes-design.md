# DroidLens Audio Capture and Bidirectional Stream Modes Specification

## 1. Overview & Goal
Extend DroidLens to capture microphone audio from the Android device, multiplex audio and video over the existing USB ADB TCP tunnel (`127.0.0.1:8080`), route audio output on Windows (with auto-detection for virtual microphone drivers such as `VB-Audio Virtual Cable`), and allow live switching between three streaming modes (`AUDIO_VIDEO`, `VIDEO_ONLY`, `AUDIO_ONLY`) from either the Android app or the Windows PC client.

## 2. Requirements & Constraints
1. **Three Operating Modes (`StreamMode`):**
   - `VIDEO_ONLY` (`0x01` — UI label: `"Solo Cámara"`): CameraX active, `AudioRecord` stopped.
   - `AUDIO_ONLY` (`0x02` — UI label: `"Solo Micrófono"`): CameraX unbound/stopped (sensor powered down), `AudioRecord` active. Windows virtual camera renders an audio-active standby frame so active video calls do not drop.
   - `AUDIO_VIDEO` (`0x03` — UI label: `"Cámara + Micrófono"`): Both CameraX and `AudioRecord` active.
2. **Bidirectional Mode Synchronization:**
   - Either endpoint (Android or PC) can initiate a mode change over the connected TCP socket on port `8080`.
   - Receiving a `CONTROL_MODE` packet immediately updates local hardware state and UI selection without creating a feedback loop.
3. **Low-Latency PCM Audio Format:**
   - Sample rate: `48000 Hz`
   - Channels: `1` (Mono)
   - Encoding: `16-bit signed PCM little-endian` (`int16`)
   - Frame chunk duration: `20 ms` (`960 samples` = `1920 bytes` per packet)
4. **Windows Audio Output Routing:**
   - Use `sounddevice>=0.4.6` (`RawOutputStream`) for low-latency WASAPI/MME output.
   - Auto-detect any output device containing `"CABLE Input"` (VB-Audio Virtual Cable) as the default target when no user preference is saved.
   - Provide a dropdown selector in the Windows UI to pick any available output device or `"Silenciado"` (muted).

## 3. Binary Protocol Specification (`APCM` v2)
The fixed header increases from 20 bytes to **21 bytes** (Big-Endian `>4sBIQI`):

| Offset | Field | Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0..3` | `MAGIC` | `char[4]` | 4 B | `'APCM'` (`0x41, 0x50, 0x43, 0x4D`) |
| `4` | `PACKET_TYPE` | `uint8` | 1 B | `0x01` = `VIDEO_JPEG`, `0x02` = `AUDIO_PCM`, `0x03` = `CONTROL_MODE` |
| `5..8` | `SEQ_ID` | `uint32` | 4 B | Monotonic sequence ID per stream |
| `9..16` | `TIMESTAMP_MS` | `uint64` | 8 B | Capture epoch timestamp in milliseconds |
| `17..20` | `LENGTH` | `uint32` | 4 B | Payload size in bytes (`1..20_000_000`) |
| `21..N` | `PAYLOAD` | `bytes` | `LENGTH` | JPEG frame, PCM audio chunk, or 1-byte mode code |

## 4. Component Architecture

### 4.1 Android App (`com.droidlens.app`)
1. **`StreamMode` (`camera/StreamMode.kt`):**
   - Enum with `VIDEO_ONLY(1, "Solo Cámara")`, `AUDIO_ONLY(2, "Solo Micrófono")`, `AUDIO_VIDEO(3, "Cámara + Micrófono")`.
2. **`PacketProtocol` (`network/PacketProtocol.kt`):**
   - Constants `HEADER_SIZE = 21`, `TYPE_VIDEO = 1.toByte()`, `TYPE_AUDIO = 2.toByte()`, `TYPE_CONTROL_MODE = 3.toByte()`.
   - Methods `createHeader(packetType: Byte, seqId: Int, timestampMs: Long, payloadLength: Int): ByteArray`, `packFrame(...)`, and `parseHeader(headerBytes: ByteArray): Header?`.
3. **`AudioCaptureManager` (`audio/AudioCaptureManager.kt`):**
   - Uses `AudioRecord` with `MediaRecorder.AudioSource.VOICE_COMMUNICATION`, `48000 Hz`, `AudioFormat.CHANNEL_IN_MONO`, `AudioFormat.ENCODING_PCM_16BIT`.
   - Attaches `NoiseSuppressor` and `AcousticEchoCanceler` when `isAvailable()` is true.
   - Reads exact `1920-byte` chunks on a dedicated background thread and invokes `onAudioChunkCaptured(pcmBytes: ByteArray)`.
4. **`StreamServer` (`network/StreamServer.kt`):**
   - Maintains `frameChannel = Channel<ByteArray>(Channel.CONFLATED)` for video and `audioChannel = Channel<ByteArray>(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)` for audio.
   - Runs a reader coroutine on `clientSocket.getInputStream()` to parse incoming `TYPE_CONTROL_MODE` packets from the PC client and invoke `callback.onRemoteModeChanged(mode: StreamMode)`.
   - Exposes `sendAudio(pcmBytes: ByteArray)` and `sendControlMode(mode: StreamMode)`.
5. **`CamStreamService` (`service/CamStreamService.kt`) & `AndroidManifest.xml`:**
   - Adds `RECORD_AUDIO` and `FOREGROUND_SERVICE_MICROPHONE` permissions; sets `android:foregroundServiceType="camera|microphone"`.
   - Owns both `CameraManager` and `AudioCaptureManager`.
   - Implements `setStreamMode(mode: StreamMode, notifyRemote: Boolean = true)` to start/stop camera and microphone hardware according to `mode`.
   - Falls back to `VIDEO_ONLY` if `RECORD_AUDIO` permission is not granted when an audio mode is requested.
6. **`MainActivity` (`MainActivity.kt` & `activity_main.xml`):**
   - Requests `RECORD_AUDIO` alongside `CAMERA`.
   - Adds a mode selector (`Spinner` or segmented button) with the 3 modes, synchronized with `CamStreamService`.

### 4.2 Windows PC Client (`pc_client`)
1. **`protocol.py` (`pc_client/src/core/protocol.py`):**
   - Updates `HEADER_FORMAT = ">4sBIQI"` (`HEADER_SIZE = 21`).
   - Defines `PacketType` (`VIDEO_JPEG = 1`, `AUDIO_PCM = 2`, `CONTROL_MODE = 3`) and `StreamMode` (`VIDEO_ONLY = 1`, `AUDIO_ONLY = 2`, `AUDIO_VIDEO = 3`).
   - Updates `pack_frame(frame_id, timestamp_ms, payload_bytes, packet_type=PacketType.VIDEO_JPEG)`, `pack_control_mode(mode: StreamMode)`, and `parse_header(header_bytes) -> Optional[Tuple[int, int, int, int]]` returning `(packet_type, seq_id, timestamp_ms, length)`.
2. **`audio_output.py` (`pc_client/src/core/audio_output.py`):**
   - `AudioOutputManager`: enumerates output devices via `sounddevice.query_devices()`, auto-selects `"CABLE Input"` when available, manages a thread-safe `RawOutputStream(samplerate=48000, channels=1, dtype='int16', blocksize=960)`, and exposes `write_chunk(pcm_bytes: bytes)`, `set_device(device_name: Optional[str])`, and `set_muted(muted: bool)`.
3. **`receiver.py` (`pc_client/src/core/receiver.py`):**
   - Demultiplexes incoming packets by `packet_type`:
     - `VIDEO_JPEG`: existing OpenCV decode + LIFO slot update.
     - `AUDIO_PCM`: forwards payload to `on_audio_chunk` callback and updates audio bitrate metrics.
     - `CONTROL_MODE`: updates `self.remote_stream_mode` and invokes `on_mode_changed(StreamMode)` callback.
   - Exposes `send_control_mode(mode: StreamMode) -> bool` using a socket write lock.
4. **`processor.py` & `app_window.py`:**
   - Adds a mode selector (`"Cámara + Micrófono"`, `"Solo Cámara"`, `"Solo Micrófono"`) and an audio output device selector in the sidebar.
   - When mode is `AUDIO_ONLY`, renders a dedicated standby visual (`"MODO SOLO MICRÓFONO ACTIVO"`) so the virtual camera stays alive without freezing.
5. **Packaging (`requirements.txt`, `droidlens.spec`):**
   - Adds `sounddevice>=0.4.6` to `requirements.txt` and `hiddenimports` in `droidlens.spec`.

## 5. Error Handling & Edge Cases
- **Permission Denied on Android:** If the user denies `RECORD_AUDIO`, selecting `AUDIO_ONLY` or `AUDIO_VIDEO` automatically reverts to `VIDEO_ONLY`, notifies the PC via `CONTROL_MODE`, and displays a toast on Android.
- **Audio Device Disconnected on Windows:** If `sounddevice` raises `PortAudioError` during playback, `AudioOutputManager` logs the error, disables the broken stream cleanly, and continues video reception uninterrupted.
- **Mode Feedback Loop Prevention:** `setStreamMode(..., notifyRemote = false)` is used when applying a mode received from the remote peer so packets do not bounce infinitely.

## 6. Testing Strategy
- **Python Unit Tests (`pytest`):**
  - `test_protocol.py`: 21-byte header packing/parsing for `VIDEO_JPEG`, `AUDIO_PCM`, and `CONTROL_MODE`, plus stream resynchronization.
  - `test_receiver.py`: Audio chunk routing to callback, remote `CONTROL_MODE` handling, bidirectional `send_control_mode`, and `AUDIO_ONLY` state behavior.
  - `test_audio_output.py`: Device enumeration, `"CABLE Input"` auto-detection, mute/unmute, and graceful failure when `sounddevice` raises an error.
- **Android Unit Tests (`JUnit`):**
  - `PacketProtocolTest.kt`: 21-byte header creation, parsing, and `CONTROL_MODE` packet encoding/decoding.
