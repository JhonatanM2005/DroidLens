# DroidLens 📱➡️💻

> Convierte tu celular Android en una webcam de alta definición para Windows por cable USB con latencia ultra baja (< 50 ms), sin necesidad de OBS Studio ni software pesado de terceros.

---

## ✨ Características

- **Conexión por cable USB:** Comunicación de alta velocidad y latencia mínima (< 50 ms) mediante ADB port forwarding (`adb forward tcp:8080 tcp:8080`) o USB Tethering.
- **Driver DirectShow independiente:** Filtro `UnityCapture` registrado directamente en Windows. Reconocido nativamente por Zoom, Google Meet, Microsoft Teams, Discord, Skype, OBS y navegadores web.
- **Sin suites pesadas:** No requiere tener instalado ni abierto OBS Studio ni software de terceros en segundo plano.
- **ADB Portable incluido:** No necesitas instalar Android Studio ni configurar variables de entorno para usar la aplicación en la PC.
- **App Android Nativa con Jetpack CameraX:**
  - Selector de cámara trasera principal y frontal.
  - Activación de linterna / flash continuo.
  - Selector de resolución (720p HD / 1080p Full HD).
  - **Modo Ahorro de Energía / Pantalla Oscura:** Apaga los píxeles de la pantalla AMOLED mientras transmite video para evitar el sobrecalentamiento del teléfono en reuniones largas.
- **Interfaz Moderna de PC (CustomTkinter):**
  - Vista previa en vivo con métricas de FPS, bitrate y latencia en tiempo real.
  - Controles de rotación (0°, 90°, 180°, 270°) y modo espejo (flip horizontal).
  - Pantalla de standby elegante para no congelar las llamadas si se desconecta el cable.

---

## 📁 Estructura del Repositorio

```text
DroidLens/
├── driver/                      # Driver DirectShow independiente (UnityCapture)
│   ├── install_driver.bat       # Registro del driver en Windows con permisos UAC
│   ├── uninstall_driver.bat     # Desinstalación limpia
│   ├── UnityCaptureFilter64.dll # Filtro 64 bits
│   └── UnityCaptureFilter32.dll # Filtro 32 bits
│
├── pc_client/                   # Aplicación receptora en PC (Windows)
│   ├── bin/adb/                 # Binarios portables de ADB (adb.exe)
│   ├── requirements.txt         # pyvirtualcam, opencv-python, customtkinter
│   ├── main.py                  # Punto de entrada de la app de escritorio
│   ├── run.bat                  # Lanzador rápido
│   └── src/
│       ├── core/                # Protocolo binario APCM, buffer LIFO y cámara virtual
│       ├── usb/                 # Gestor ADB y reenvío automático de puertos
│       └── ui/                  # Interfaz gráfica moderna con CustomTkinter
│
├── android/                     # Aplicación móvil nativa en Kotlin (CameraX)
│   ├── app/src/main/
│   │   ├── AndroidManifest.xml
│   │   ├── java/com/droidlens/app/
│   │   │   ├── MainActivity.kt  # UI móvil, controles y modo ahorro
│   │   │   ├── camera/          # Jetpack CameraX, control de lentes y linterna
│   │   │   ├── network/         # Servidor TCP de streaming y protocolo APCM
│   │   │   └── util/            # Conversión YUV_420_888 a JPEG
│   │   └── res/                 # Layouts y recursos visuales
│   ├── build.gradle.kts
│   └── settings.gradle.kts
│
├── scripts/                     # Herramientas y pruebas automatizadas
│   ├── test_virtualcam.py       # Prueba sintética del driver virtual
│   ├── simulate_phone_stream.py # Simulador del stream de Android para PC
│   ├── test_pipeline.py         # Test de integración E2E del receptor
│   └── build_apk.bat            # Compilador rápido del APK de Android
│
├── run.bat                      # Iniciar DroidLens en PC con un solo clic
├── plan-desarrollo.md           # Plan maestro de 7 fases
└── README.md
```

---

## 🚀 Guía de Uso Paso a Paso

### Paso 1: Instalar el Driver DirectShow en Windows (Solo una vez)
1. Abre la carpeta `driver/`.
2. Haz doble clic en `install_driver.bat` y pulsa **"Sí"** en el diálogo de administrador.
3. El driver queda registrado para siempre en Windows con el nombre **"Unity Video Capture"**.

### Paso 2: Instalar la App en tu Celular Android
1. Abre **Android Studio** en tu PC.
2. Selecciona **File -> Open** y elige la carpeta `android` de este proyecto.
3. Conecta tu celular por USB, asegúrate de tener activada la **Depuración por USB** (en *Opciones de desarrollador*).
4. Pulsa el botón verde **Run (▶)** en Android Studio para instalarla y abrirla en tu móvil.
*(O compila el APK con `scripts\build_apk.bat` e instálalo con `adb install app-debug.apk`).*

### Paso 3: Iniciar DroidLens en la PC
1. Conecta el celular por cable USB a la computadora.
2. Haz doble clic en el archivo [**`run.bat`**](file:///c:/Users/Usuario/Documents/AppCam/run.bat) en la raíz del proyecto.
3. En la ventana de DroidLens:
   - Activa el interruptor **"Cámara Virtual"**.
   - En tu app de videollamadas (Google Meet, Zoom, Teams, Discord o navegador), selecciona **"Unity Video Capture"** como tu cámara.

¡Listo! Disfruta de la calidad de los lentes de tu celular con cero latencia y sin sobrecalentar el teléfono.
