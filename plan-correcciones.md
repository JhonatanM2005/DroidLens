## Plan de correcciones

### Bloque 1 — Recuperación y desconexión

1. Cambiar el contrato de `StreamReceiver` para distinguir:
   - frame nuevo;
   - último frame almacenado;
   - stream vencido/desconectado.

2. Registrar `last_frame_received_at` y, tras un umbral corto (por ejemplo, 250 ms), devolver estado de espera en vez de reutilizar la imagen anterior.

3. Actualizar el loop de vídeo para generar standby cuando el frame esté vencido, y mantener una revisión propia para repintar la animación de standby aunque no cambie `frame_id`.

4. Corregir el contador de frames descartados y sustituir el `Event` compartido por una cola de tamaño uno o una sincronización que no pierda señales.

5. Añadir pruebas para:
   - desconexión;
   - reconexión;
   - frame vencido;
   - standby visible tanto en preview como en cámara virtual;
   - métrica de frames descartados.

Criterio: desconectar el cable durante una reunión cambia a standby en menos de 250 ms y recupera vídeo sin reiniciar la aplicación.

### Bloque 2 — Streaming Android realmente persistente

1. Extraer el estado y operaciones de streaming a un controlador único, preferiblemente dentro de `CamStreamService`.
2. Convertir el servicio en propietario de CameraX y del `StreamServer`; la actividad pasa a ser solo una interfaz que se vincula al servicio.
3. Usar un ciclo de vida de servicio para CameraX, no el de `MainActivity`.
4. Hacer que la acción “Detener” de la notificación invoque la misma operación central que el botón de la app: detener captura, servidor, wake lock y notificación.
5. Evitar detener el servicio en `MainActivity.onDestroy()` salvo que el usuario haya pedido parar.
6. Implementar una duración renovable del wake lock, o administrar su adquisición/liberación según el estado real del stream.

Criterio: bloquear, minimizar, girar o cerrar la interfaz no interrumpe una transmisión activa; “Detener” la corta siempre.

### Bloque 3 — Robustez de cámara y ADB

1. Hacer que `bindCameraUseCases()` devuelva `Result`/`Boolean`; llamar a `startStreaming()` solo si CameraX quedó enlazado.
2. Marcar el estado compartido entre UI y analizador como seguro para hilos, o eliminar la duplicación entre `isStreaming` e `isStreamingActive`.
3. Separar en ADB el valor “usar serial seleccionado” de “ejecutar comando global”; `devices`, `version`, `kill-server` y `forward --list` no deben heredar un serial persistido.
4. Solo crear un forward para dispositivos con estado `device`.
5. Incluir pruebas con serial previamente guardado, dispositivo desconectado, unauthorized y múltiples dispositivos.

Criterio: la app se recupera de una cámara ocupada, permiso denegado o móvil desconectado sin activar falsamente la transmisión.

### Bloque 4 — Presets y cámara virtual

1. Definir claramente dos configuraciones:
   - perfil de captura Android;
   - perfil de salida Windows.

2. Añadir un canal de control PC→Android si se espera que un preset de PC cambie la captura del teléfono. Si no se implementa, dejarlo explícito en la interfaz.

3. No reiniciar la cámara virtual mientras está activa en una videollamada. En su lugar, mostrar “Aplicar al reiniciar cámara virtual” o pedir confirmación.

4. Hacer que el loop PC use el FPS del preset actual, también en standby.

Criterio: cambiar ajustes no desconecta Zoom/Teams inesperadamente y el usuario sabe qué resolución usa en cada extremo.

### Bloque 5 — Portabilidad, pruebas y documentación

1. Eliminar `org.gradle.java.home` de [gradle.properties](C:/Users/Usuario/Documents/AppCam/android/gradle.properties:2): es una ruta local de Windows y puede romper CI Linux.
2. Añadir `pytest` a dependencias de desarrollo o a un `requirements-dev.txt`.
3. Reemplazar el badge fijo de CI por el badge real del workflow.
4. Eliminar afirmaciones no medidas como “<20 ms” y “GC cero”; publicar resultados reproducibles de una prueba de latencia.
5. Ampliar CI con pruebas de empaquetado Windows y una ejecución básica del binario generado.

---

## ¿`.exe` o wizard en vez de `.bat`?

Mi recomendación: entregar ambos, pero con prioridades distintas.

- Un `.exe` portable para quienes solo quieren abrir la app.
- Un instalador/wizard `.exe` como entrega principal para usuarios finales.

No recomiendo conservar el `.bat` como experiencia de usuario final. Puede quedar para desarrollo y soporte técnico.

### Arquitectura recomendada

```text
DroidLens-Setup.exe
├─ Instala DroidLens Desktop en Windows
├─ Incluye el ejecutable empaquetado
├─ Incluye ADB portable
├─ Ofrece instalar UnityCapture como componente opcional
├─ Crea acceso directo y desinstalador
└─ Abre una guía de primer inicio
```

Para el cliente PC usaría PyInstaller en modo **one-folder** (`--onedir`), no `--onefile`. PyInstaller soporta ambos formatos, además de incluir datos y binarios adicionales; el modo carpeta es el predeterminado y resulta más fácil de depurar y más estable para dependencias nativas como OpenCV, Tk y DLLs. [Documentación oficial de PyInstaller]([https://pyinstaller.org/en/stable/usage.html](<https://pyinstaller.org/en/stable/usage.html>))

El modo `--onefile` es atractivo visualmente, pero extrae componentes temporales al iniciar y suele aumentar el tiempo de arranque; para una aplicación de vídeo con dependencias grandes prefiero evitarlo.

### Stack de distribución

- **PyInstaller**: congela Python, CustomTkinter, OpenCV, NumPy, Pillow y pyvirtualcam en `DroidLens.exe`.
- **Inno Setup**: genera `DroidLens-Setup.exe`, copia archivos, crea accesos directos, desinstalador y componente opcional del driver.
- **Driver UnityCapture**: instalación separada y explícita mediante UAC; la app normal no debe ejecutarse completa como administrador.
- **Firma de código**: como fase posterior, firma el instalador, ejecutable y DLLs para reducir alertas de SmartScreen/antivirus.

### Cambios necesarios para soportarlo

1. Reemplazar rutas relativas al código fuente por:
   - recursos junto al ejecutable;
   - configuración y capturas en `%APPDATA%\DroidLens` o `%LOCALAPPDATA%\DroidLens`.

2. Crear un archivo `droidlens.spec` de PyInstaller que incluya:
   - `pc_client/bin/adb`;
   - módulos dinámicos de OpenCV/CustomTkinter;
   - icono, licencia y archivos de diagnóstico.

3. Crear un script `.iss` de Inno Setup con:
   - instalación per-user por defecto;
   - tarea opcional “Instalar driver UnityCapture”;
   - elevación UAC solo para registrar/desregistrar el driver;
   - desinstalación que pregunte antes de desregistrar el driver.

4. Sustituir [package_windows.py](C:/Users/Usuario/Documents/AppCam/scripts/package_windows.py) por un pipeline en dos etapas:
   - construir `DroidLens.exe`;
   - construir `DroidLens-Setup.exe`.

5. Añadir CI Windows para compilar el ejecutable y publicar ambos artefactos.

El resultado ideal sería que el usuario descargue `DroidLens-Setup.exe`, siga un wizard de tres pasos y no tenga que instalar Python, abrir una terminal ni ejecutar un `.bat`.