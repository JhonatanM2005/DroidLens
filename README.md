# DroidLens 📱➡️💻

> Convierte tu celular Android en una webcam de alta definición para Windows por cable USB con latencia ultra baja (15 a 35 ms típica), sin necesidad de OBS Studio ni software pesado de terceros.

[![Descargar APK](https://img.shields.io/badge/Descargar%20APK-v1.1.0-orange?style=for-the-badge&logo=android)](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.1.0/DroidLens.apk)
[![Instalador Windows](https://img.shields.io/badge/Instalador%20Windows-v1.1.0-blue?style=for-the-badge&logo=windows)](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.1.0/DroidLens-Setup-v1.1.0.exe)
[![Portable Windows](https://img.shields.io/badge/Portable%20Windows-v1.1.0-lightgrey?style=for-the-badge&logo=windows)](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.1.0/DroidLens-Windows-Portable-v1.1.0.zip)
[![GitHub Release](https://img.shields.io/github/v/release/JhonatanM2005/DroidLens?style=for-the-badge)](https://github.com/JhonatanM2005/DroidLens/releases)
[![CI Build](https://github.com/JhonatanM2005/DroidLens/actions/workflows/ci.yml/badge.svg)](https://github.com/JhonatanM2005/DroidLens/actions/workflows/ci.yml)

---

## ✨ Características Principales

- **Conexión por Cable USB con Túnel Seguro y Aislado:**
  - Comunicación de alta velocidad mediante ADB port forwarding (`adb -s <serial> forward tcp:8080 tcp:8080`).
  - Servidor enlazado a `127.0.0.1` de forma predeterminada para evitar que el flujo quede expuesto a redes Wi-Fi públicas o externas.
  - Selección de dispositivo objetivo en PC cuando hay múltiples teléfonos o emuladores conectados.
  - Comandos globales (`devices`, `version`, `kill-server`) protegidos para no heredar seriales persistidos.
  - Limpieza automática de reglas de reenvío al cerrar la aplicación.
- **Doble Motor de Cámara Virtual (Windows 11 `IMFVirtualCamera` + DirectShow `UnityCapture`):**
  - **Motor Nativo Windows 11 (`DroidLensMF.dll`):** Basado en `IMFVirtualCamera` y `IMFMediaSourceEx` sobre memoria compartida (`Local\DroidLens_MF_SharedVideo`), exponiendo **`"DroidLens Virtual Camera"`** en la app Cámara de Windows 11, Microsoft Teams, Zoom, Google Meet, Discord y navegadores modernos.
  - **Motor DirectShow Clásico (`UnityCapture`):** Compatible con Windows 10/11 y aplicaciones DirectShow heredadas, seleccionable desde la interfaz gráfica.
- **Modo Segundo Plano en Bandeja del Sistema (System Tray):**
  - Al minimizar o pulsar la `X`, DroidLens se oculta en la bandeja del sistema (junto al reloj), desaparece de la barra de tareas para evitar cierres accidentales y pausa el renderizado visual de Tkinter para ahorrar CPU mientras el video y el micrófono continúan activos.
- **Recuperación Inmediata ante Desconexión (<250 ms):**
  - Contrato de recepción reactivo (`NEW_FRAME`, `STALE_CACHED`, `EXPIRED_OR_DISCONNECTED`).
  - Si el cable se desconecta o la señal se interrumpe por más de 250 ms, la aplicación cambia instantáneamente a la pantalla de standby animada sin congelar la imagen ni desconectar la videollamada.
- **3 Modos de Transmisión Bidireccionales y Captura de Micrófono:**
  - Conmutación en vivo desde el celular o desde la PC entre **`Cámara + Micrófono`**, **`Solo Cámara`** y **`Solo Micrófono`** sin reiniciar la conexión USB.
  - Captura de audio de baja latencia (`AudioRecord` PCM 16-bit, 48 kHz, Mono, chunks de 20 ms) con `NoiseSuppressor` y `AcousticEchoCanceler` por hardware cuando el dispositivo lo soporta.
  - En modo **`Solo Micrófono`**, el sensor de cámara en Android se pausa para ahorrar batería y temperatura, mientras la PC emite un lienzo optimizado de `"MODO SOLO MICRÓFONO"`.
  - Enrutamiento de audio en Windows con autodetección de **`VB-Audio Virtual Cable`** (`CABLE Input`) para exponer el micrófono del celular en Zoom, Meet, Teams y Discord.
- **Protocolo APCM v2 Multiplexado con Transporte de Cero Copias:**
  - Cabecera binaria de 21 bytes (`Magic 'APCM'` + `PACKET_TYPE` + `SEQ_ID` + `TIMESTAMP_MS` + `PAYLOAD_LEN`) que multiplexa video JPEG (`0x01`), audio PCM (`0x02`) y comandos de control bidireccionales (`0x03`) sobre el mismo túnel TCP.
- **Ciclo de Vida Persistente (ForegroundService):**
  - Servicio en primer plano (`CamStreamService` como `LifecycleService` con tipos `camera|microphone`) propietario de CameraX, `AudioCaptureManager` y del servidor de streaming.
  - La captura continúa de forma ininterrumpida al minimizar la app, rotar la pantalla o bloquear el teléfono.
  - `WakeLock` parcial gestionado automáticamente y acción unificada "Detener" en app y notificación.
- **App Android Nativa con Jetpack CameraX:**
  - **Perfiles Centralizados:** 1080p Full HD (30 FPS), 720p HD (30 FPS) y 480p Bajo Consumo (24 FPS).
  - Pausa total de análisis y compresión de imagen cuando no se transmite video, reduciendo el consumo y la temperatura.
  - Botón rápido de modo de transmisión sincronizado en tiempo real con la PC.
  - Enfoque táctil (Tap-to-Focus) y zoom digital fluido (Pinch-to-Zoom).
  - Detección segura de linterna/flash físico mediante `hasFlashUnit()`.
  - **Modo Pantalla Oscura (AMOLED Power Save):** Apaga los píxeles de la pantalla con un toque para evitar el sobrecalentamiento.
- **Cliente Moderno para Windows (CustomTkinter):**
  - Vista previa en vivo con escalado inteligente y bajo consumo de CPU.
  - Selector de modo de transmisión (`Cámara + Micrófono`, `Solo Cámara`, `Solo Micrófono`) y selector de salida de audio (`VB-Cable` o altavoces).
  - Métricas precisas de FPS recibidos, FPS consumidos, bitrate (Kbps) y latencia USB en tiempo real filtrada contra desincronización de reloj.
  - Selección de resolución de salida Windows (DirectShow) con cambio no destructivo durante videollamadas.
  - Selector de rotación (0°, 90°, 180°, 270°) y modo espejo (flip horizontal).
  - Botón de **Snapshot** instantáneo en alta resolución guardado en `captures/`.
  - Overlay de diagnóstico HUD conmutable.
  - Persistencia automática de configuración en `settings.json` o `%LOCALAPPDATA%\DroidLens`.

---

## 📁 Estructura del Repositorio

```text
DroidLens/
├── DroidLens.apk                # APK compilado listo para instalar en Android
├── dist/                        # Instaladores y binarios compilados listos para usar
│   ├── DroidLens-Setup-v1.0.0.exe        # Instalador wizard para Windows (Inno Setup)
│   ├── DroidLens-Windows-Portable-v1.0.0.zip # Versión portable sin instalación
│   └── DroidLens/                        # Carpeta del ejecutable compilado (PyInstaller)
│       └── DroidLens.exe                 # Binario principal de escritorio
│
├── driver/                      # Drivers de cámara DirectShow y micrófono virtual
│   ├── install_driver.bat       # Registro del driver de cámara en Windows con permisos UAC
│   ├── install_vbcable.bat      # Descarga e instalación automática de VB-Cable (micrófono virtual)
│   ├── uninstall_driver.bat     # Desinstalación limpia del filtro de cámara
│   ├── UnityCaptureFilter64.dll # Filtro de vídeo 64 bits
│   └── UnityCaptureFilter32.dll # Filtro de vídeo 32 bits
│
├── installer/                   # Definición de instaladores
│   └── droidlens.iss            # Script de Inno Setup 6 con elevación UAC selectiva
│
├── pc_client/                   # Aplicación de escritorio para Windows (Python)
│   ├── droidlens.spec           # Especificación de PyInstaller (--onedir)
│   ├── requirements.txt         # Dependencias de producción
│   ├── requirements-dev.txt     # Dependencias de desarrollo y testing (pytest)
│   ├── bin/adb/                 # Binarios portables de ADB (adb.exe y DLLs)
│   ├── main.py                  # Punto de entrada de la aplicación
│   ├── run.bat                  # Lanzador rápido con venv automático
│   ├── tests/                   # Suite de 26 pruebas unitarias (pytest)
│   │   ├── test_adb.py          # Pruebas de ADB, aislamiento de serial y comandos
│   │   ├── test_audio_output.py # Pruebas de enrutamiento de audio y autodetección VB-Cable
│   │   ├── test_processor.py    # Pruebas de transformación de imagen, standby y solo audio
│   │   ├── test_protocol.py     # Pruebas de empaquetado y resincronización APCM v2
│   │   └── test_receiver.py     # Pruebas de demultiplexación video/audio/control y desconexión
│   └── src/
│       ├── core/                # Receptor demultiplexor, AudioOutputManager, protocolo APCM v2
│       ├── ui/                  # Interfaz gráfica moderna (CustomTkinter)
│       ├── adb/                 # Gestor multi-dispositivo y forward con serial
│       └── utils/               # Gestor de rutas portables (paths.py)
│
├── android/                     # Aplicación móvil nativa en Kotlin (CameraX + AudioRecord)
│   ├── gradlew / gradlew.bat    # Gradle Wrapper oficial reproducible (v8.13)
│   ├── app/src/main/
│   │   ├── AndroidManifest.xml  # Permisos de cámara, micrófono y ForegroundService
│   │   ├── java/com/droidlens/app/
│   │   │   ├── MainActivity.kt  # UI móvil, selector de modo y cliente de servicio
│   │   │   ├── audio/           # AudioCaptureManager (PCM 48kHz + DSP hardware)
│   │   │   ├── camera/          # VideoProfile, CameraManager, pausa de sensor, zoom y enfoque
│   │   │   ├── model/           # StreamMode (CAMERA_AND_MIC, CAMERA_ONLY, MIC_ONLY)
│   │   │   ├── network/         # StreamServer y PacketProtocol APCM v2 (21 bytes)
│   │   │   ├── service/         # CamStreamService (LifecycleService con WakeLock)
│   │   │   └── util/            # Conversión acelerada por hardware (libyuv)
│   │   └── res/                 # Layouts y recursos visuales
│   └── app/src/test/            # Tests unitarios JUnit para protocolo APCM v2
│
├── scripts/                     # Herramientas de automatización y testing
│   ├── build_windows_dist.py    # Pipeline de dos etapas: PyInstaller + Inno Setup
│   ├── package_windows.py       # Empaquetador zip portable
│   ├── build_apk.bat            # Compilador rápido de APK con gradlew
│   ├── simulate_phone_stream.py # Simulador del feed de Android para PC
│   └── test_pipeline.py         # Test de integración E2E
│
├── .github/workflows/ci.yml     # Pipeline de integración continua (CI) en GitHub Actions
├── DroidLens.apk                # APK precompilado listo para instalar
├── run.bat                      # Iniciar DroidLens en PC con un solo clic
└── README.md
```

---

## 📡 Especificación del Protocolo APCM v2

La comunicación entre el celular y la PC utiliza un socket TCP bidireccional sobre el túnel ADB con una cabecera binaria fija de **21 bytes** (Big-Endian):

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       'A'     |       'P'     |       'C'     |       'M'     | -> Magic (4 bytes: 'APCM')
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  PACKET_TYPE  |                                               | -> uint8 (0x01=Video, 0x02=Audio, 0x03=Control)
+-+-+-+-+-+-+-+-+                    SEQ_ID                     +
|                                               |               | -> uint32 (4 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                        TIMESTAMP_MS                           | -> uint64 (8 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         PAYLOAD_LEN                           | -> uint32 (4 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           PAYLOAD                             | -> N bytes (JPEG / PCM 48kHz / StreamMode)
|                            ...                                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

---

## 📦 Distribución e Instalación en Windows

DroidLens ofrece dos opciones de distribución oficiales para Windows (descargables desde [GitHub Releases](https://github.com/JhonatanM2005/DroidLens/releases)):

1. **Instalador Wizard ([`DroidLens-Setup-v1.0.0.exe`](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens-Setup-v1.0.0.exe)):**
   - Instalación per-user sin requerir permisos de administrador para la app.
   - Opciones durante la instalación para registrar el driver de cámara DirectShow (`UnityCapture`) e instalar el driver de micrófono virtual (`VB-Cable`) con elevación UAC.
   - Crea accesos directos en el Menú Inicio y Escritorio con desinstalador limpio.
2. **Ejecutable Portable ([`DroidLens-Windows-Portable-v1.0.0.zip`](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens-Windows-Portable-v1.0.0.zip)):**
   - No requiere instalación: descomprimir y ejecutar `DroidLens.exe`.

---

## 🚀 Guía de Uso Paso a Paso

### Paso 1: Instalar los Drivers de Cámara y Micrófono Virtual en Windows (Solo una vez)
1. **Driver de Cámara Virtual (`Unity Video Capture`):**
   - Abre la carpeta `driver/` (o marca la casilla en el instalador), haz doble clic en `install_driver.bat` y acepta los permisos de administrador.
2. **Driver de Micrófono Virtual (`VB-Audio Virtual Cable` — requerido para usar el micrófono en Discord, Meet, Zoom o Teams):**
   - Haz doble clic en `driver/install_vbcable.bat` (o pulsa el botón **"📥 Instalar Micrófono Virtual (VB-Cable)"** directamente dentro de la app DroidLens en PC) y haz clic en **"Install Driver"** en la ventana que se abre.

### Paso 2: Instalar la App en tu Celular Android
1. Instala el APK [**`DroidLens.apk`**](file:///c:/Users/Usuario/Documents/AppCam/DroidLens.apk) directamente en tu teléfono:
   ```powershell
   adb install -r DroidLens.apk
   ```
2. Conecta el cable USB y activa la **Depuración por USB** en *Opciones de desarrollador* de tu móvil.
3. Abre DroidLens y concede los permisos de **Cámara** y **Micrófono**.

### Paso 3: Iniciar DroidLens en la PC y Configurar Discord / Meet / Zoom
1. Conecta el celular por cable USB a la computadora.
2. Abre `DroidLens.exe` (o ejecuta `run.bat` en desarrollo).
3. En la ventana de DroidLens:
   - Si tienes varios teléfonos, elige tu celular en el menú desplegable.
   - En **Salida de Audio / Micrófono**, verifica que esté seleccionado **`CABLE Input (VB-Audio Virtual Cable)`** (se autodetecta al tener VB-Cable instalado).
   - Activa el interruptor **"Cámara Virtual"**.
4. En tu app de videollamadas (**Discord**, Google Meet, Zoom, Microsoft Teams o navegador):
   - **Cámara / Dispositivo de Video:** selecciona **`Unity Video Capture`**.
   - **Micrófono / Dispositivo de Entrada:** selecciona **`CABLE Output (VB-Audio Virtual Cable)`**.

---

## 🧪 Pruebas Automatizadas y CI

### Pruebas de la Aplicación de PC (Python)
```powershell
& "pc_client\.venv\Scripts\pytest.exe" pc_client/tests -v
```

### Pruebas Unitarias de Android (Kotlin)
```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

### Compilación del APK de Android
```powershell
cd android
.\gradlew.bat assembleDebug
```

### Compilación de la Distribución Windows (PyInstaller + Inno Setup)
```powershell
& "pc_client\.venv\Scripts\python.exe" scripts/build_windows_dist.py
```

---

## 🔍 Diagnóstico y Solución de Problemas

| Síntoma | Causa Probable | Solución |
| :--- | :--- | :--- |
| **"Buscando USB..."** | Cable no detectado o depuración inactiva. | Usa un cable de datos (no solo de carga) y confirma que la Depuración USB está encendida. |
| **"Autorizar en Celular"** | Permiso RSA de depuración pendiente. | Desbloquea la pantalla del celular y pulsa "Permitir siempre desde esta computadora". |
| **"Error al iniciar cámara virtual"** | Driver DirectShow no registrado. | Ejecuta `driver\install_driver.bat` como Administrador. |
| **Discord / Meet no detecta el micrófono o me escucho en mis altavoces** | `VB-Audio Virtual Cable` no está instalado en Windows. | Pulsa **"📥 Instalar Micrófono Virtual (VB-Cable)"** en DroidLens (o ejecuta `driver\install_vbcable.bat`), elige `CABLE Input` en DroidLens y `CABLE Output` como micrófono en Discord. |
| **Latencia > 100 ms** | Hub USB saturado o puerto USB 2.0 antiguo. | Conecta el celular a un puerto USB 3.0 directo de la placa base de la PC. |
| **Desconexión rápida a standby** | Cable USB flojo o app Android cerrada. | Al reconectar el cable o abrir la app, la señal se recupera automáticamente sin reiniciar DroidLens en la PC. |
