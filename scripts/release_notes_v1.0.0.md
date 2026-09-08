# 🚀 DroidLens v1.0.0 — Lanzamiento Oficial

Convierte tu dispositivo Android en una webcam de alta definición para Windows por cable USB con latencia ultra baja (15 a 35 ms) y sin necesidad de OBS ni software pesado de terceros.

---

### 📦 Archivos Disponibles para Descarga

| Archivo | Plataforma | Descripción |
| :--- | :--- | :--- |
| **[DroidLens-Setup-v1.0.0.exe](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens-Setup-v1.0.0.exe)** | Windows 10/11 | **Instalador oficial recomendado** (asistente de instalación Inno Setup con registro automático del driver DirectShow y accesos directos). |
| **[DroidLens-Windows-Portable-v1.0.0.zip](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens-Windows-Portable-v1.0.0.zip)** | Windows 10/11 | Versión **portable lista para descomprimir y ejecutar** sin necesidad de instalación. |
| **[DroidLens.apk](https://github.com/JhonatanM2005/DroidLens/releases/download/v1.0.0/DroidLens.apk)** | Android 7.0+ | **Aplicación para teléfono Android** con Jetpack CameraX, streaming continuo en segundo plano y perfiles de vídeo optimizados. |

---

### ✨ Novedades y Características de la Versión 1.0.0

- **Streaming Persistente en Segundo Plano:** `CamStreamService` implementado como `LifecycleService` desacoplado de la actividad con `WakeLock` parcial; la transmisión no se interrumpe al apagar la pantalla, rotar el teléfono o minimizar la app.
- **Recuperación Inmediata ante Desconexión (<250 ms):** Contrato reactivo LIFO con transición instantánea a pantalla de standby animada al desconectar el cable o sufrir micro-cortes, sin congelar la videollamada.
- **Instalador Wizard Inno Setup:** Instalador rápido per-user con opción de registrar el driver de cámara virtual DirectShow (`UnityCapture`) con permisos de administrador.
- **Driver DirectShow Nativo:** Compatible con Zoom, Google Meet, Microsoft Teams, Discord, Skype, OBS Studio y navegadores web (Chrome, Edge, Firefox).
- **Latencia Ultra Baja (15 a 35 ms):** Protocolo binario APCM con transporte de cero copias sobre túnel ADB local (`127.0.0.1`).
- **Métricas en Tiempo Real:** Visualización HUD de FPS recibidos, FPS consumidos, bitrate (Kbps) y latencia filtrada contra desincronización de reloj.
- **Controles Avanzados:** Enfoque táctil (Tap-to-Focus), zoom digital (Pinch-to-Zoom), modo pantalla oscura (AMOLED Power Save), rotación (0°, 90°, 180°, 270°) y modo espejo horizontal.

---

### 📋 Instrucciones Rápidas de Instalación

1. **En tu PC con Windows:**
   - Descarga y ejecuta **`DroidLens-Setup-v1.0.0.exe`**.
   - Sigue el asistente de instalación (asegúrate de mantener marcada la casilla para registrar el driver de cámara virtual DirectShow).
2. **En tu teléfono Android:**
   - Descarga **`DroidLens.apk`** en tu teléfono e instálalo (permite instalar fuentes desconocidas si te lo solicita).
   - Activa la **Depuración por USB** en las *Opciones de Desarrollador* de Android.
3. **Uso:**
   - Conecta tu teléfono al PC mediante cable USB.
   - Abre DroidLens en el PC y pulsa **"Iniciar Cámara"**.
   - En tu app de videollamadas (Zoom, Meet, etc.), selecciona la cámara **"Unity Video Capture"**.
