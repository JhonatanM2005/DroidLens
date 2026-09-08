# DroidLens 📱➡️💻

> Convierte tu celular Android en una webcam de alta definición para Windows por cable USB con latencia ultra baja (15 a 35 ms típica), sin necesidad de OBS Studio ni software pesado de terceros.

[![Descargar APK](https://img.shields.io/badge/Descargar%20APK-v1.0.0-orange?style=for-the-badge&logo=android)](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens.apk)
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
- **Driver DirectShow Independiente:**
  - Filtro DirectShow `UnityCapture` registrado de forma nativa en Windows.
  - Reconocido directamente por Zoom, Google Meet, Microsoft Teams, Discord, Skype, OBS Studio y navegadores web (Chrome, Edge, Firefox).
- **Recuperación Inmediata ante Desconexión (<250 ms):**
  - Contrato de recepción reactivo (`NEW_FRAME`, `STALE_CACHED`, `EXPIRED_OR_DISCONNECTED`).
  - Si el cable se desconecta o la señal se interrumpe por más de 250 ms, la aplicación cambia instantáneamente a la pantalla de standby animada sin congelar la imagen ni desconectar la videollamada.
- **Protocolo APCM con Transporte de Cero Copias:**
  - Cabecera binaria de 20 bytes enviada directamente al flujo de red antes del payload JPEG, eliminando copias intermedias de memoria.
- **Ciclo de Vida Persistente (ForegroundService):**
  - Servicio en primer plano (`CamStreamService` como `LifecycleService`) propietario de CameraX y del servidor de streaming.
  - La captura continúa de forma ininterrumpida al minimizar la app, rotar la pantalla o bloquear el teléfono.
  - `WakeLock` parcial gestionado automáticamente y acción unificada "Detener" en app y notificación.
- **App Android Nativa con Jetpack CameraX:**
  - **Perfiles Centralizados:** 1080p Full HD (30 FPS), 720p HD (30 FPS) y 480p Bajo Consumo (24 FPS).
  - Pausa total de análisis y compresión de imagen cuando no se transmite video, reduciendo el consumo y la temperatura.
  - Enfoque táctil (Tap-to-Focus) y zoom digital fluido (Pinch-to-Zoom).
  - Detección segura de linterna/flash físico mediante `hasFlashUnit()`.
  - **Modo Pantalla Oscura (AMOLED Power Save):** Apaga los píxeles de la pantalla con un toque para evitar el sobrecalentamiento.
- **Cliente Moderno para Windows (CustomTkinter):**
  - Vista previa en vivo con escalado inteligente y bajo consumo de CPU.
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
├── driver/                      # Driver DirectShow independiente (UnityCapture)
│   ├── install_driver.bat       # Registro del driver en Windows con permisos UAC
│   ├── uninstall_driver.bat     # Desinstalación limpia del filtro
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
│   ├── tests/                   # Suite de 18 pruebas unitarias (pytest)
│   │   ├── test_adb.py          # Pruebas de ADB, aislamiento de serial y comandos
│   │   ├── test_processor.py    # Pruebas de transformación de imagen y standby
│   │   ├── test_protocol.py     # Pruebas de empaquetado y resincronización APCM
│   │   └── test_receiver.py     # Pruebas de desconexión inmediata y frames caídos
│   └── src/
│       ├── core/                # Receptor LIFO reactivo, protocolo y cámara virtual
│       ├── ui/                  # Interfaz gráfica moderna (CustomTkinter)
│       ├── adb/                 # Gestor multi-dispositivo y forward con serial
│       └── utils/               # Gestor de rutas portables (paths.py)
│
├── android/                     # Aplicación móvil nativa en Kotlin (CameraX)
│   ├── gradlew / gradlew.bat    # Gradle Wrapper oficial reproducible (v8.13)
│   ├── app/src/main/
│   │   ├── AndroidManifest.xml  # Permisos de cámara, ForegroundService y backup
│   │   ├── java/com/droidlens/app/
│   │   │   ├── MainActivity.kt  # UI móvil, controles táctiles y cliente de servicio
│   │   │   ├── camera/          # VideoProfile, CameraManager, zoom y enfoque
│   │   │   ├── network/         # StreamServer (127.0.0.1) y transporte cero copias
│   │   │   ├── service/         # CamStreamService (LifecycleService con WakeLock)
│   │   │   └── util/            # Conversión acelerada por hardware (libyuv)
│   │   └── res/                 # Layouts y recursos visuales
│   └── app/src/test/            # Tests unitarios JUnit para Android
│
├── scripts/                     # Herramientas de automatización y testing
│   ├── build_windows_dist.py    # Pipeline de dos etapas: PyInstaller + Inno Setup
│   ├── package_windows.py       # Empaquetador zip portable
│   ├── build_apk.bat            # Compilador rápido de APK con gradlew
│   ├── simulate_phone_stream.py # Simulador del feed de Android para PC
│   └── test_pipeline.py         # Test de integración E2E
│
├── .github/workflows/ci.yml     # Pipeline de integración continua (CI) en GitHub Actions
├── DroidLens.apk                # APK precompilado listo para instalar (6.70 MB)
├── run.bat                      # Iniciar DroidLens en PC con un solo clic
└── README.md
```

---

## 📡 Especificación del Protocolo APCM

La comunicación entre el celular y la PC utiliza un socket TCP sobre el túnel ADB con una cabecera binaria fija de 20 bytes (Big-Endian):

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       'A'     |       'P'     |       'C'     |       'M'     | -> Magic (4 bytes: 'APCM')
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          FRAME_ID                             | -> uint32 (4 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                        TIMESTAMP_MS                           | -> uint64 (8 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         PAYLOAD_LEN                           | -> uint32 (4 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        JPEG_PAYLOAD                           | -> N bytes
|                            ...                                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

---

## 📦 Distribución e Instalación en Windows

DroidLens ofrece dos opciones de distribución para Windows:

1. **Instalador Wizard (`DroidLens-Setup.exe`):**
   - Instalación per-user sin requerir permisos de administrador para la app.
   - Opción durante la instalación para registrar el driver DirectShow con elevación UAC.
   - Crea accesos directos en el Menú Inicio y Escritorio con desinstalador limpio.
2. **Ejecutable Portable (`DroidLens-Windows-Portable-v1.0.0.zip`):**
   - No requiere instalación: descomprimir y ejecutar `DroidLens.exe`.

---

## 🚀 Guía de Uso Paso a Paso

### Paso 1: Instalar el Driver DirectShow en Windows (Solo una vez)
1. Abre la carpeta `driver/` (o selecciona la opción en el instalador).
2. Haz doble clic en `install_driver.bat` y pulsa **"Sí"** en el diálogo de administrador.
3. El driver queda registrado en Windows con el nombre **"Unity Video Capture"**.

### Paso 2: Instalar la App en tu Celular Android
1. Instala el APK [**`DroidLens.apk`**](file:///c:/Users/Usuario/Documents/AppCam/DroidLens.apk) directamente en tu teléfono:
   ```powershell
   adb install -r DroidLens.apk
   ```
2. Conecta el cable USB y activa la **Depuración por USB** en *Opciones de desarrollador* de tu móvil.
3. Abre DroidLens y concede el permiso de cámara.

### Paso 3: Iniciar DroidLens en la PC
1. Conecta el celular por cable USB a la computadora.
2. Abre `DroidLens.exe` (o ejecuta `run.bat` en desarrollo).
3. En la ventana de DroidLens:
   - Si tienes varios teléfonos, elige tu celular en el menú desplegable.
   - Activa el interruptor **"Cámara Virtual"**.
   - En tu app de videollamadas (Google Meet, Zoom, Teams, Discord o navegador), selecciona **"Unity Video Capture"** como tu cámara.

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
| **Latencia > 100 ms** | Hub USB saturado o puerto USB 2.0 antiguo. | Conecta el celular a un puerto USB 3.0 directo de la placa base de la PC. |
| **Desconexión rápida a standby** | Cable USB flojo o app Android cerrada. | Al reconectar el cable o abrir la app, la señal se recupera automáticamente sin reiniciar DroidLens en la PC. |
