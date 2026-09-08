"""
Interfaz gráfica de usuario de escritorio para DroidLens.
Desarrollada con CustomTkinter para un diseño moderno y oscuro.
Permite ver el preview en vivo, controlar la rotación, el modo espejo,
activar la cámara virtual, seleccionar dispositivos USB y monitorear métricas en tiempo real.
"""

import os
import json
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import customtkinter as ctk
import cv2
from PIL import Image

try:
    from core.receiver import StreamReceiver, FrameStatus
    from core.processor import FrameProcessor
    from core.virtual_camera import VirtualCameraManager
    from adb.adb_manager import ADBManager
    from utils.paths import get_settings_file, get_captures_dir, find_adb_binary
except ImportError:
    from ..core.receiver import StreamReceiver, FrameStatus
    from ..core.processor import FrameProcessor
    from ..core.virtual_camera import VirtualCameraManager
    from ..adb.adb_manager import ADBManager
    from ..utils.paths import get_settings_file, get_captures_dir, find_adb_binary

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

OUTPUT_PRESETS = {
    "1080p Full HD (1920x1080)": (1920, 1080, 30),
    "720p HD (1280x720)": (1280, 720, 30),
    "480p SD (854x480)": (854, 480, 24)
}

class DroidLensApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("DroidLens — Webcam USB para Windows")
        self.geometry("1020x720")
        self.minsize(860, 600)

        # Cargar configuración persistida
        self.settings = self._load_settings()

        # Componentes del núcleo
        adb_bin = find_adb_binary()
        self.adb_manager = ADBManager(custom_adb_path=adb_bin or None, selected_serial=self.settings.get("last_serial"))
        self.receiver = StreamReceiver(host="127.0.0.1", port=8080)

        preset_name = self.settings.get("output_preset", "720p HD (1280x720)")
        initial_w, initial_h, initial_fps = OUTPUT_PRESETS.get(preset_name, (1280, 720, 30))

        self.processor = FrameProcessor(target_width=initial_w, target_height=initial_h)
        self.processor.rotation_degrees = self.settings.get("rotation", 0)
        self.processor.flip_horizontal = self.settings.get("mirror", True)
        self.processor.show_diagnostic_overlay = self.settings.get("overlay", False)

        self.vcam = VirtualCameraManager(width=initial_w, height=initial_h, fps=initial_fps)
        self._pending_vcam_resolution: Optional[Tuple[int, int, int]] = None

        self.is_running = True
        self.is_vcam_enabled = False
        self._latest_display_frame = None
        self._is_in_standby = True
        self._latest_frame_id = -1
        self._last_rendered_id = -2
        self._device_map: Dict[str, str] = {}

        # Configurar diseño de interfaz
        self._create_ui()

        # Iniciar receptor y bucles secundarios
        self.receiver.start()
        self._video_thread = threading.Thread(target=self._video_loop, daemon=True, name="VirtualCamVideoThread")
        self._video_thread.start()

        self._usb_monitor_thread = threading.Thread(target=self._usb_monitor_loop, daemon=True, name="UsbMonitorThread")
        self._usb_monitor_thread.start()

        # Iniciar refresco del preview en el hilo principal de la GUI
        self.after(33, self._ui_refresh_tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_settings(self) -> Dict[str, Any]:
        default_settings = {
            "rotation": 0,
            "mirror": True,
            "output_preset": "720p HD (1280x720)",
            "overlay": False,
            "last_serial": None
        }
        settings_file = get_settings_file()
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_settings.update(data)
            except Exception:
                pass
        return default_settings

    def _save_settings(self):
        try:
            with open(get_settings_file(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _create_ui(self):
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
        self.controls_frame = ctk.CTkScrollableFrame(self, corner_radius=10, width=310)
        self.controls_frame.grid(row=0, column=1, padx=(0, 16), pady=16, sticky="nsew")

        panel_title = ctk.CTkLabel(
            self.controls_frame,
            text="Controles",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        panel_title.pack(pady=(12, 8), padx=12, anchor="w")

        # Switch de Cámara Virtual
        self.vcam_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Cámara Virtual",
            font=ctk.CTkFont(size=14, weight="bold"),
            progress_color="#FF8C00",
            command=self._toggle_vcam
        )
        self.vcam_switch.pack(pady=6, padx=12, anchor="w")

        self.vcam_desc = ctk.CTkLabel(
            self.controls_frame,
            text="Dispositivo: Unity Video Capture\nCompatible con Zoom, Meet, Teams, Discord.",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            justify="left"
        )
        self.vcam_desc.pack(pady=(0, 10), padx=12, anchor="w")

        self._add_separator()

        # Configuración de Salida Windows (DirectShow)
        ctk.CTkLabel(self.controls_frame, text="Salida Virtual Windows", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(6, 2), padx=12, anchor="w")
        self.preset_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=list(OUTPUT_PRESETS.keys()),
            command=self._on_preset_changed
        )
        self.preset_menu.set(self.settings.get("output_preset", "720p HD (1280x720)"))
        self.preset_menu.pack(fill="x", padx=12, pady=4)

        self.vcam_status_note = ctk.CTkLabel(
            self.controls_frame,
            text="💡 Resolución de captura: cámbiala en la app del móvil.",
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            justify="left"
        )
        self.vcam_status_note.pack(pady=(0, 6), padx=12, anchor="w")

        self._add_separator()

        # Orientación y Espejo
        ctk.CTkLabel(self.controls_frame, text="Orientación de Imagen", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(6, 2), padx=12, anchor="w")

        rot_val = self.processor.rotation_degrees
        self.btn_rotate = ctk.CTkButton(
            self.controls_frame,
            text=f"Rotar 90° ({rot_val}°)",
            command=self._rotate_frame,
            fg_color="#2A2D32",
            hover_color="#3A3D42"
        )
        self.btn_rotate.pack(fill="x", padx=12, pady=4)

        self.mirror_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Modo Espejo (Flip)",
            progress_color="#00E5FF",
            command=self._toggle_mirror
        )
        if self.processor.flip_horizontal:
            self.mirror_switch.select()
        else:
            self.mirror_switch.deselect()
        self.mirror_switch.pack(pady=6, padx=12, anchor="w")

        self.overlay_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Overlay de Diagnóstico",
            progress_color="#00E676",
            command=self._toggle_overlay
        )
        if self.processor.show_diagnostic_overlay:
            self.overlay_switch.select()
        else:
            self.overlay_switch.deselect()
        self.overlay_switch.pack(pady=6, padx=12, anchor="w")

        # Botón Snapshot
        self.btn_snapshot = ctk.CTkButton(
            self.controls_frame,
            text="📸 Guardar Foto (Snapshot)",
            command=self._take_snapshot,
            fg_color="#2C3E50",
            hover_color="#34495E"
        )
        self.btn_snapshot.pack(fill="x", padx=12, pady=6)

        self._add_separator()

        # Selector de Dispositivos USB
        ctk.CTkLabel(self.controls_frame, text="Dispositivo Android (USB)", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(6, 2), padx=12, anchor="w")

        self.device_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=["Buscando dispositivos..."],
            command=self._on_device_selected
        )
        self.device_menu.pack(fill="x", padx=12, pady=4)

        self.device_info_label = ctk.CTkLabel(
            self.controls_frame,
            text="Enchufa el celular por USB con Depuración activa.",
            font=ctk.CTkFont(size=11),
            text_color="#AAAAAA",
            justify="left"
        )
        self.device_info_label.pack(pady=4, padx=12, anchor="w")

        self.btn_reconnect_adb = ctk.CTkButton(
            self.controls_frame,
            text="Reescanear USB",
            command=self._reconnect_usb_async,
            fg_color="#1E3A5F",
            hover_color="#2B4C7E"
        )
        self.btn_reconnect_adb.pack(fill="x", padx=12, pady=(6, 12))

    def _add_separator(self):
        sep = ctk.CTkProgressBar(self.controls_frame, height=2)
        sep.set(1.0)
        sep.pack(fill="x", padx=12, pady=8)

    def _toggle_vcam(self):
        self.is_vcam_enabled = self.vcam_switch.get()
        if self.is_vcam_enabled:
            # Aplicar resolución pendiente si existía antes de iniciar
            if self._pending_vcam_resolution:
                pw, ph, pfps = self._pending_vcam_resolution
                self.vcam.update_resolution(pw, ph, pfps)
                self.processor.set_target_size(pw, ph)
                self._pending_vcam_resolution = None
                self.vcam_status_note.configure(text="💡 Resolución de captura: cámbiala en la app móvil.", text_color="#888888")

            if not self.vcam.start():
                self.vcam_switch.deselect()
                self.is_vcam_enabled = False
                self.vcam_desc.configure(
                    text="Error al iniciar cámara virtual.\n¿Ejecutaste driver\\install_driver.bat?",
                    text_color="#FF5252"
                )
            else:
                self.vcam_desc.configure(
                    text="Cámara Virtual ACTIVA.\nSelecciona 'Unity Video Capture' en tu app.",
                    text_color="#00E676"
                )
        else:
            self.vcam.stop()
            self.vcam_desc.configure(text="Cámara Virtual DETENIDA.", text_color="#888888")
            if self._pending_vcam_resolution:
                pw, ph, pfps = self._pending_vcam_resolution
                self.vcam.update_resolution(pw, ph, pfps)
                self.processor.set_target_size(pw, ph)
                self._pending_vcam_resolution = None
                self.vcam_status_note.configure(text="💡 Resolución de captura: cámbiala en la app móvil.", text_color="#888888")

    def _on_preset_changed(self, preset_name: str):
        if preset_name in OUTPUT_PRESETS:
            w, h, fps = OUTPUT_PRESETS[preset_name]
            self.settings["output_preset"] = preset_name
            self._save_settings()

            if self.is_vcam_enabled and self.vcam.is_active:
                # Bloque 4: No cortar videollamadas activas; guardar como pendiente
                self._pending_vcam_resolution = (w, h, fps)
                self.vcam_status_note.configure(
                    text="⚠️ Salida cambiará al reiniciar la Cámara Virtual.",
                    text_color="#FFBB33"
                )
            else:
                self.processor.set_target_size(w, h)
                self.vcam.update_resolution(w, h, fps)
                self._pending_vcam_resolution = None
                self.vcam_status_note.configure(
                    text="💡 Resolución de captura: cámbiala en la app móvil.",
                    text_color="#888888"
                )

    def _rotate_frame(self):
        new_rot = (self.processor.rotation_degrees + 90) % 360
        self.processor.rotation_degrees = new_rot
        self.btn_rotate.configure(text=f"Rotar 90° ({new_rot}°)")
        self.settings["rotation"] = new_rot
        self._save_settings()

    def _toggle_mirror(self):
        val = self.mirror_switch.get()
        self.processor.flip_horizontal = val
        self.settings["mirror"] = val
        self._save_settings()

    def _toggle_overlay(self):
        val = self.overlay_switch.get()
        self.processor.show_diagnostic_overlay = val
        self.settings["overlay"] = val
        self._save_settings()

    def _take_snapshot(self):
        frame = self._latest_display_frame
        if frame is None:
            return

        try:
            captures_dir = get_captures_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snapshot_{timestamp}.png"
            filepath = os.path.join(captures_dir, filename)
            cv2.imwrite(filepath, frame)

            self.btn_snapshot.configure(text="✓ ¡Foto Guardada!", fg_color="#007E33")
            self.after(2000, lambda: self.btn_snapshot.configure(text="📸 Guardar Foto (Snapshot)", fg_color="#2C3E50"))
        except Exception:
            self.btn_snapshot.configure(text="✗ Error al guardar", fg_color="#CC0000")
            self.after(2000, lambda: self.btn_snapshot.configure(text="📸 Guardar Foto (Snapshot)", fg_color="#2C3E50"))

    def _on_device_selected(self, display_name: str):
        serial = self._device_map.get(display_name)
        if serial:
            self.adb_manager.set_selected_serial(serial)
            self.settings["last_serial"] = serial
            self._save_settings()
            threading.Thread(target=lambda: self.adb_manager.setup_port_forward(8080, 8080, serial=serial), daemon=True).start()

    def _reconnect_usb_async(self):
        def _task():
            self.adb_manager.restart_server()
            time.sleep(0.5)
            serial = self.adb_manager.selected_serial
            self.adb_manager.setup_port_forward(8080, 8080, serial=serial)
        threading.Thread(target=_task, daemon=True).start()

    def _usb_monitor_loop(self):
        last_devices = []
        while self.is_running:
            devices = self.adb_manager.list_devices()
            if devices != last_devices:
                last_devices = devices
                self.after(0, self._update_devices_ui, devices)
            time.sleep(2.5)

    def _update_devices_ui(self, devices: List[Dict[str, str]]):
        self._device_map.clear()
        if not devices:
            self.device_menu.configure(values=["Ningún celular detectado"])
            self.device_menu.set("Ningún celular detectado")
            self.status_badge.configure(text="Buscando USB...", fg_color="#333333")
            self.device_info_label.configure(
                text="Desconectado\nEnchufa el celular por USB con Depuración activa.",
                text_color="#AAAAAA"
            )
            return

        display_names = []
        selected_name = None
        current_serial = self.adb_manager.selected_serial

        for d in devices:
            serial = d["serial"]
            model = d["model"]
            state = d["state"]
            name = f"{model} ({serial[-4:]})"
            if state != "device":
                name += f" [{state.upper()}]"
            self._device_map[name] = serial
            display_names.append(name)

            if serial == current_serial:
                selected_name = name

        if not selected_name and display_names:
            selected_name = display_names[0]
            first_serial = self._device_map[selected_name]
            self.adb_manager.set_selected_serial(first_serial)
            # Solo forward si el estado es 'device'
            threading.Thread(target=lambda: self.adb_manager.setup_port_forward(8080, 8080, serial=first_serial), daemon=True).start()

        self.device_menu.configure(values=display_names)
        if selected_name:
            self.device_menu.set(selected_name)

        active_dev = next((d for d in devices if d["serial"] == self.adb_manager.selected_serial), devices[0])
        if active_dev["state"] == "device":
            self.status_badge.configure(text="USB Conectado", fg_color="#007E33")
            self.device_info_label.configure(
                text=f"Modelo: {active_dev['model']}\nEstado: Listo (Túnel USB tcp:8080)",
                text_color="#00E676"
            )
        elif active_dev["state"] == "unauthorized":
            self.status_badge.configure(text="Autorizar en Celular", fg_color="#FF8800")
            self.device_info_label.configure(
                text="Acepta el diálogo de 'Permitir depuración por USB'\nen la pantalla de tu celular.",
                text_color="#FFBB33"
            )
        else:
            self.status_badge.configure(text="Dispositivo Offline", fg_color="#555555")
            self.device_info_label.configure(
                text=f"Estado: {active_dev['state']}\nReconecta el cable USB.",
                text_color="#AAAAAA"
            )

    def _video_loop(self):
        """Bucle dedicado que sincroniza el ritmo FPS del preset y alimenta la cámara virtual."""
        while self.is_running:
            target_fps = self.vcam.fps
            frame_interval = 1.0 / max(target_fps, 10)
            loop_start = time.time()

            result = self.receiver.get_latest_frame(timeout=0.033)

            if result.status in (FrameStatus.NEW_FRAME, FrameStatus.STALE_CACHED) and result.frame is not None:
                self._is_in_standby = False
                self._latest_frame_id = result.meta.get("frame_id", self._latest_frame_id + 1)
                processed = self.processor.process_frame(result.frame, meta=result.meta)
            else:
                # Bloque 1: Expired o desconectado -> pasar a standby animado inmediatamente
                self._is_in_standby = True
                msg = "Esperando stream del celular..." if self.receiver.connected else "Esperando conexion USB..."
                processed = self.processor.generate_standby_frame(msg)

            if self.is_vcam_enabled and self.vcam.is_active:
                self.vcam.send_frame(processed)

            self._latest_display_frame = processed

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _ui_refresh_tick(self):
        """Actualiza el canvas y las métricas en el hilo principal de Tkinter."""
        if not self.is_running:
            return

        frame = self._latest_display_frame
        # En standby repintar siempre para animar el círculo; en stream pintar solo en frame nuevo
        should_render = self._is_in_standby or (self._latest_frame_id != self._last_rendered_id)

        if frame is not None and should_render:
            self._last_rendered_id = self._latest_frame_id
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
        lat_val = stats['latency_ms']
        lat_text = f"{lat_val:.0f} ms" if (stats['connected'] and lat_val > 0) else "-- ms"
        self.latency_label.configure(text=f"Latencia: {lat_text}")

        self.after(33, self._ui_refresh_tick)

    def _on_close(self):
        self.is_running = False
        try:
            self.adb_manager.remove_port_forward(8080)
        except Exception:
            pass
        self.receiver.stop()
        self.vcam.stop()
        self.destroy()

if __name__ == "__main__":
    app = DroidLensApp()
    app.mainloop()
