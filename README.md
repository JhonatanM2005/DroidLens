# AppCam 📱➡️💻

> Convierte tu celular Android en una webcam de alta definición para Windows por cable USB con latencia ultra baja, sin necesidad de OBS Studio ni software pesado de terceros.

---

## 🚀 Características

- **Conexión por cable USB:** Comunicación de alta velocidad y latencia mínima (< 80 ms) mediante ADB port forwarding o USB Tethering.
- **Driver DirectShow independiente:** Incluye el filtro DirectShow `UnityCapture` registrado como dispositivo del sistema operativo, compatible con Zoom, Google Meet, Microsoft Teams, Discord, OBS y navegadores.
- **Sin suites pesadas:** No requiere tener instalado ni abierto OBS Studio.
- **ADB Portable incluido:** No necesitas instalar Android Studio ni configurar variables de entorno para la comunicación USB en la PC.
- **Móvil Android optimizado:** Captura con Jetpack CameraX, control de exposición/enfoque, selector de cámaras y modo de pantalla apagada para evitar sobrecalentamiento térmico.

---

## 📁 Estructura del Repositorio

```text
AppCam/
├── driver/                # Driver DirectShow independiente (UnityCapture)
│   ├── install_driver.bat # Registro del driver en Windows con permisos UAC
│   ├── uninstall_driver.bat
│   ├── UnityCaptureFilter64.dll
│   └── UnityCaptureFilter32.dll
├── pc_client/             # Aplicación receptora en Python
│   ├── bin/adb/           # Binarios portables de ADB (adb.exe)
│   ├── requirements.txt   # pyvirtualcam, opencv-python, customtkinter
│   └── src/               # Código fuente del cliente PC
├── android/               # Aplicación nativa en Kotlin para Android (CameraX)
├── scripts/               # Scripts de prueba y automatización
│   └── test_virtualcam.py # Prueba sintética de la cámara virtual
├── plan-desarrollo.md     # Documento maestro con las 7 fases del proyecto
└── README.md
```

---

## ⚡ Inicio Rápido (Fase 0 - Prueba de Cámara Virtual)

### 1. Registrar el Driver DirectShow en Windows
1. Abre la carpeta `driver/`.
2. Haz clic derecho en `install_driver.bat` y selecciona **"Ejecutar como administrador"** (o haz doble clic y acepta el diálogo UAC).
3. Verás el mensaje de confirmación: `[OK] Driver instalado y registrado con exito!`.

### 2. Probar la Cámara Virtual
1. Abre una terminal en la raíz del proyecto.
2. Ejecuta la prueba con el entorno virtual de Python:
   ```powershell
   pc_client\.venv\Scripts\python.exe scripts\test_virtualcam.py
   ```
3. Abre la aplicación **"Cámara"** de Windows o entra a [webcamtests.com](https://webcamtests.com) y selecciona **"Unity Video Capture"**. Verás el patrón animado con contador de FPS en tiempo real.
