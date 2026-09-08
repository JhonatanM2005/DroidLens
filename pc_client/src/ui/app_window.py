"""
Interfaz gráfica de usuario de escritorio para DroidLens.
Desarrollada con CustomTkinter para un diseño moderno y oscuro.
Permite ver el preview en vivo, controlar la rotación, el modo espejo,
activar la cámara virtual y monitorear el estado de la conexión USB.
"""

import threading
import time
from typing import Optional
import customtkinter as ctk
import cv2
from PIL import Image

try:
    from core.receiver import StreamReceiver
    from core.processor import FrameProcessor
    from core.virtual_camera import VirtualCameraManager
    from usb.adb_manager import ADBManager
except ImportError:
    from ..core.receiver import StreamReceiver
    from ..core.processor import FrameProcessor
    from ..core.virtual_camera import VirtualCameraManager
    from ..usb.adb_manager import ADBManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class DroidLensApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("DroidLens — Webcam USB para Windows")
        self.geometry("980x660")
        self.minsize(800, 560)

        # Componentes del núcleo
        self.adb_manager = ADBManager()
        self.receiver = StreamReceiver(host="127.0.0.1", port=8080)
        self.processor = FrameProcessor(target_width=1280, target_height=720)
        self.vcam = VirtualCameraManager(width=1280, height=720, fps=30)

        self.is_running = True
        self.is_vcam_enabled = False
        self._latest_display_frame = None

        # Configurar diseño de interfaz
        self._create_ui()

        # Iniciar receptor y bucles
        self.receiver.start()
        self._video_thread = threading.Thread(target=self._video_loop, daemon=True, name="VirtualCamVideoThread")
        self._video_thread.start()

        self._usb_monitor_thread = threading.Thread(target=self._usb_monitor_loop, daemon=True, name="UsbMonitorThread")
        self._usb_monitor_thread.start()

        # Iniciar refresco del preview en el hilo principal de la GUI
        self.after(30, self._ui_refresh_tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_ui(self):
        # Grid principal: 2 columnas (preview a la izquierda, controles a la derecha)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # Panel Izquierdo: Vista Previa
        # ==========================================
        self.preview_frame = ctk.CTkFrame(self, corner_radius=10)
        self.preview_frame.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        self.preview_frame.grid_rowconfigure(1, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        # Barra superior del preview
        self.header_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="DroidLens",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#FF8C00"
        )
        self.title_label.pack(side="left")

        self.status_badge = ctk.CTkLabel(
            self.header_frame,
            text="Buscando USB...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#333333",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.status_badge.pack(side="right")

        # Canvas de visualización
        self.video_canvas = ctk.CTkLabel(self.preview_frame, text="", fg_color="#101010", corner_radius=8)
        self.video_canvas.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")

        # Barra inferior de métricas (FPS, Bitrate, Latencia)
        self.metrics_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        self.metrics_frame.grid(row=2, column=0, padx=16, pady=(6, 12), sticky="ew")

        self.fps_label = ctk.CTkLabel(self.metrics_frame, text="FPS: 0.0", font=ctk.CTkFont(size=13))
        self.fps_label.pack(side="left", padx=(0, 16))

        self.bitrate_label = ctk.CTkLabel(self.metrics_frame, text="Bitrate: 0 Kbps", font=ctk.CTkFont(size=13))
        self.bitrate_label.pack(side="left", padx=(0, 16))

        self.latency_label = ctk.CTkLabel(self.metrics_frame, text="Latencia USB: -- ms", font=ctk.CTkFont(size=13))
        self.latency_label.pack(side="left")

        # ==========================================
        # Panel Derecho: Controles y Ajustes
        # ==========================================
        self.controls_frame = ctk.CTkFrame(self, corner_radius=10, width=280)
        self.controls_frame.grid(row=0, column=1, padx=(0, 16), pady=16, sticky="nsew")
        self.controls_frame.grid_propagate(False)

        panel_title = ctk.CTkLabel(
            self.controls_frame,
            text="Controles",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        panel_title.pack(pady=(16, 12), padx=16, anchor="w")

        # Switch de Cámara Virtual
        self.vcam_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Cámara Virtual",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#FF8C00",
            command=self._toggle_vcam
        )
        self.vcam_switch.pack(pady=8, padx=16, anchor="w")

        self.vcam_desc = ctk.CTkLabel(
            self.controls_frame,
            text="Dispositivo: Unity Video Capture\nVisible en Zoom, Meet, Teams y Chrome.",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            justify="left"
        )
        self.vcam_desc.pack(pady=(0, 16), padx=16, anchor="w")

        # Separador
        sep1 = ctk.CTkProgressBar(self.controls_frame, height=2)
        sep1.set(1.0)
        sep1.pack(fill="x", padx=16, pady=8)

        # Orientación y Espejo
        orient_title = ctk.CTkLabel(self.controls_frame, text="Orientación de Imagen", font=ctk.CTkFont(size=14, weight="bold"))
        orient_title.pack(pady=(8, 4), padx=16, anchor="w")

        self.btn_rotate = ctk.CTkButton(
            self.controls_frame,
            text="Rotar 90° (0°)",
            command=self._rotate_frame,
            fg_color="#2A2D32",
            hover_color="#3A3D42"
        )
        self.btn_rotate.pack(fill="x", padx=16, pady=6)

        self.mirror_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Modo Espejo (Flip)",
            progress_color="#00E5FF",
            command=self._toggle_mirror
        )
        self.mirror_switch.select()
        self.mirror_switch.pack(pady=8, padx=16, anchor="w")

        # Separador
        sep2 = ctk.CTkProgressBar(self.controls_frame, height=2)
        sep2.set(1.0)
        sep2.pack(fill="x", padx=16, pady=8)

        # Información del Celular
        device_title = ctk.CTkLabel(self.controls_frame, text="Dispositivo USB", font=ctk.CTkFont(size=14, weight="bold"))
        device_title.pack(pady=(8, 4), padx=16, anchor="w")

        self.device_info_label = ctk.CTkLabel(
            self.controls_frame,
            text="Desconectado\nEnchufa el celular por USB con Depuración activa.",
            font=ctk.CTkFont(size=12),
            text_color="#AAAAAA",
            justify="left"
        )
        self.device_info_label.pack(pady=4, padx=16, anchor="w")

        self.btn_reconnect_adb = ctk.CTkButton(
            self.controls_frame,
            text="Reescanear USB",
            command=self._reconnect_usb,
            fg_color="#1E3A5F",
            hover_color="#2B4C7E"
        )
        self.btn_reconnect_adb.pack(fill="x", padx=16, pady=(12, 6))

    def _toggle_vcam(self):
        self.is_vcam_enabled = self.vcam_switch.get()
        if self.is_vcam_enabled:
            if not self.vcam.start():
                self.vcam_switch.deselect()
                self.is_vcam_enabled = False
                self.vcam_desc.configure(text="Error al iniciar la cámara virtual.\n¿Ejecutaste driver\\install_driver.bat?", text_color="#FF5252")
            else:
                self.vcam_desc.configure(text="Cámara Virtual ACTIVA.\nSelecciona 'Unity Video Capture' en tu app.", text_color="#00E676")
        else:
            self.vcam.stop()
            self.vcam_desc.configure(text="Cámara Virtual DETENIDA.", text_color="#888888")

    def _rotate_frame(self):
        new_rot = (self.processor.rotation_degrees + 90) % 360
        self.processor.rotation_degrees = new_rot
        self.btn_rotate.configure(text=f"Rotar 90° ({new_rot}°)")

    def _toggle_mirror(self):
        self.processor.flip_horizontal = self.mirror_switch.get()

    def _reconnect_usb(self):
        self.adb_manager.setup_port_forward(8080, 8080)

    def _usb_monitor_loop(self):
        """Monitorea periódicamente si hay celulares conectados por USB."""
        last_serial = None
        while self.is_running:
            devices = self.adb_manager.list_devices()
            if devices:
                dev = devices[0]
                serial = dev['serial']
                model = dev['model']
                state = dev['state']

                if serial != last_serial:
                    last_serial = serial
                    if state == "device":
                        self.adb_manager.setup_port_forward(8080, 8080)

                self.after(0, self._update_device_ui, model, state)
            else:
                last_serial = None
                self.after(0, self._update_device_ui, None, "disconnected")

            time.sleep(2.0)

    def _update_device_ui(self, model: Optional[str], state: str):
        if state == "device":
            self.status_badge.configure(text="USB Conectado", fg_color="#007E33")
            self.device_info_label.configure(text=f"Modelo: {model or 'Android'}\nEstado: Listo (Túnel USB :8080)", text_color="#00E676")
        elif state == "unauthorized":
            self.status_badge.configure(text="Autorizar en Celular", fg_color="#FF8800")
            self.device_info_label.configure(text="Acepta el diálogo de 'Permitir depuración por USB'\nen la pantalla de tu celular.", text_color="#FFBB33")
        else:
            self.status_badge.configure(text="Buscando USB...", fg_color="#333333")
            self.device_info_label.configure(text="Desconectado\nEnchufa el celular por USB con Depuración activa.", text_color="#AAAAAA")

    def _video_loop(self):
        """Bucle de alta velocidad en hilo dedicado para alimentar la cámara virtual sin bloqueos."""
        target_fps = 30
        frame_interval = 1.0 / target_fps

        while self.is_running:
            loop_start = time.time()
            frame, meta = self.receiver.get_latest_frame(timeout=0.033)

            if frame is not None:
                processed = self.processor.process_frame(frame)
            else:
                msg = "Esperando stream del celular..." if self.receiver.connected else "Esperando conexion USB..."
                processed = self.processor.generate_standby_frame(msg)

            # Enviar a la cámara virtual en Windows
            if self.is_vcam_enabled and self.vcam.is_active:
                self.vcam.send_frame(processed)

            # Guardar referencia para que la UI la pinte desde el hilo principal
            self._latest_display_frame = processed

            # Control de ritmo
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _ui_refresh_tick(self):
        """Actualiza el canvas y las métricas en el hilo principal de Tkinter."""
        if not self.is_running:
            return

        frame = self._latest_display_frame
        if frame is not None:
            try:
                cw = max(self.video_canvas.winfo_width(), 320)
                ch = max(self.video_canvas.winfo_height(), 240)
                fh, fw = frame.shape[:2]
                scale = min(cw / fw, ch / fh)
                nw, nh = max(int(fw * scale), 10), max(int(fh * scale), 10)

                resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
                rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_frame)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(nw, nh))
                self.video_canvas.configure(image=ctk_img)
            except Exception:
                pass

        stats = self.receiver.get_stats()
        self.fps_label.configure(text=f"FPS: {stats['fps']:.1f}")
        self.bitrate_label.configure(text=f"Bitrate: {stats['bitrate_kbps']:.0f} Kbps")
        lat_text = f"{stats['latency_ms']:.0f} ms" if stats['latency_ms'] > 0 else "< 20 ms"
        self.latency_label.configure(text=f"Latencia: {lat_text}")

        self.after(33, self._ui_refresh_tick)

    def _on_close(self):
        self.is_running = False
        self.receiver.stop()
        self.vcam.stop()
        self.destroy()

if __name__ == "__main__":
    app = DroidLensApp()
    app.mainloop()
