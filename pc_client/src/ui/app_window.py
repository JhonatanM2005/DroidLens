"""
Interfaz gráfica de usuario de escritorio para DroidLens.
Desarrollada con CustomTkinter para un diseño moderno y oscuro.
Permite ver el preview en vivo, alternar entre modos (Cámara + Micrófono, Solo Cámara, Solo Micrófono),
enrutar audio hacia dispositivos de salida / micrófono virtual (VB-Cable), controlar orientación,
activar la cámara virtual, seleccionar dispositivos USB y monitorear métricas en tiempo real.
"""

import os
import json
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import customtkinter as ctk
import cv2
from PIL import Image

try:
    from core.protocol import StreamMode, STREAM_MODE_LABELS, LABEL_TO_STREAM_MODE
    from core.receiver import StreamReceiver, FrameStatus
    from core.processor import FrameProcessor
    from core.virtual_camera import (
        VirtualCameraManager,
        VirtualCamBackend,
        VCAM_BACKEND_LABELS,
        LABEL_TO_VCAM_BACKEND,
    )
    from core.audio_output import AudioOutputManager, SILENCED_DEVICE_LABEL
    from adb.adb_manager import ADBManager
    from ui.tray_manager import TrayManager
    from utils.paths import get_settings_file, get_captures_dir, find_adb_binary, find_driver_script, get_app_version
except ImportError:
    from ..core.protocol import StreamMode, STREAM_MODE_LABELS, LABEL_TO_STREAM_MODE
    from ..core.receiver import StreamReceiver, FrameStatus
    from ..core.processor import FrameProcessor
    from ..core.virtual_camera import (
        VirtualCameraManager,
        VirtualCamBackend,
        VCAM_BACKEND_LABELS,
        LABEL_TO_VCAM_BACKEND,
    )
    from ..core.audio_output import AudioOutputManager, SILENCED_DEVICE_LABEL
    from ..adb.adb_manager import ADBManager
    from .tray_manager import TrayManager
    from ..utils.paths import get_settings_file, get_captures_dir, find_adb_binary, find_driver_script, get_app_version

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

        self.app_version = get_app_version()
        self.title(f"DroidLens v{self.app_version} — Webcam y Micrófono USB para Windows")
        self.geometry("1040x760")
        self.minsize(880, 620)

        # Cargar configuración persistida
        self.settings = self._load_settings()

        # Componentes del núcleo
        adb_bin = find_adb_binary()
        self.adb_manager = ADBManager(
            custom_adb_path=adb_bin or None,
            selected_serial=self.settings.get("last_serial"),
        )
        self.audio_output = AudioOutputManager()

        saved_mode_label = self.settings.get("stream_mode", STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO])
        initial_mode = LABEL_TO_STREAM_MODE.get(saved_mode_label, StreamMode.AUDIO_VIDEO)

        self.receiver = StreamReceiver(
            host="127.0.0.1",
            port=8080,
            on_audio_chunk=self.audio_output.write_chunk,
            on_mode_changed=self._on_remote_mode_changed,
        )
        self.receiver.set_stream_mode(initial_mode, notify_remote=False)

        preset_name = self.settings.get("output_preset", "720p HD (1280x720)")
        initial_w, initial_h, initial_fps = OUTPUT_PRESETS.get(preset_name, (1280, 720, 30))

        self.processor = FrameProcessor(target_width=initial_w, target_height=initial_h)
        self.processor.rotation_degrees = self.settings.get("rotation", 0)
        self.processor.flip_horizontal = self.settings.get("mirror", True)
        self.processor.show_diagnostic_overlay = self.settings.get("overlay", False)

        saved_backend_label = self.settings.get(
            "vcam_backend", VCAM_BACKEND_LABELS[VirtualCamBackend.WINDOWS_MF]
        )
        initial_backend = LABEL_TO_VCAM_BACKEND.get(
            saved_backend_label, VirtualCamBackend.WINDOWS_MF
        )
        self.vcam = VirtualCameraManager(
            width=initial_w,
            height=initial_h,
            fps=initial_fps,
            backend=initial_backend,
        )
        self._pending_vcam_resolution: Optional[Tuple[int, int, int]] = None

        self.is_running = True
        self.is_vcam_enabled = False
        self._is_hidden_in_tray = False
        self._latest_display_frame = None
        self._is_in_standby = True
        self._latest_frame_id = -1
        self._last_rendered_id = -2
        self._device_map: Dict[str, str] = {}

        # Configurar diseño de interfaz
        self._create_ui()

        # Inicializar salida de audio según el modo actual
        self._sync_audio_output_with_mode(initial_mode)

        # Iniciar Bandeja del Sistema (System Tray)
        self.tray_manager = TrayManager(
            on_restore=self._restore_from_tray_safe,
            on_select_mode=self._on_tray_mode_selected,
            on_quit=self._quit_app_safe,
            get_current_mode=lambda: self.receiver.stream_mode,
        )
        self.tray_manager.start()

        # Iniciar receptor y bucles secundarios
        self.receiver.start()
        self._video_thread = threading.Thread(
            target=self._video_loop, daemon=True, name="VirtualCamVideoThread"
        )
        self._video_thread.start()

        self._usb_monitor_thread = threading.Thread(
            target=self._usb_monitor_loop, daemon=True, name="UsbMonitorThread"
        )
        self._usb_monitor_thread.start()

        # Iniciar refresco del preview en el hilo principal de la GUI
        self.after(33, self._ui_refresh_tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close_button)
        self.bind("<Unmap>", self._on_window_unmap)

    def _load_settings(self) -> Dict[str, Any]:
        default_settings = {
            "rotation": 0,
            "mirror": True,
            "output_preset": "720p HD (1280x720)",
            "overlay": False,
            "last_serial": None,
            "stream_mode": STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO],
            "audio_output_device": None,
            "close_to_tray": True,
            "vcam_backend": VCAM_BACKEND_LABELS[VirtualCamBackend.WINDOWS_MF],
            "last_wireless_addr": "",
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
        self.controls_frame = ctk.CTkScrollableFrame(self, corner_radius=10, width=320)
        self.controls_frame.grid(row=0, column=1, padx=(0, 16), pady=16, sticky="nsew")

        panel_title = ctk.CTkLabel(
            self.controls_frame,
            text="Controles",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        panel_title.pack(pady=(12, 8), padx=12, anchor="w")

        # Selector de Modo de Transmisión (Cámara + Micrófono / Solo Cámara / Solo Micrófono)
        ctk.CTkLabel(
            self.controls_frame,
            text="Modo de Transmisión",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(4, 2), padx=12, anchor="w")

        mode_values = [
            STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO],
            STREAM_MODE_LABELS[StreamMode.VIDEO_ONLY],
            STREAM_MODE_LABELS[StreamMode.AUDIO_ONLY],
        ]
        self.mode_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=mode_values,
            command=self._on_mode_menu_selected,
        )
        self.mode_menu.set(STREAM_MODE_LABELS.get(self.receiver.stream_mode, mode_values[0]))
        self.mode_menu.pack(fill="x", padx=12, pady=4)

        # Selector de Dispositivo de Salida de Audio / Micrófono Virtual
        ctk.CTkLabel(
            self.controls_frame,
            text="Salida de Audio / Micrófono",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(8, 2), padx=12, anchor="w")

        audio_options = self._build_audio_device_options()
        self.audio_device_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=audio_options,
            command=self._on_audio_device_selected,
        )
        saved_audio_dev = self.settings.get("audio_output_device")
        preferred_audio_dev = (
            saved_audio_dev
            if saved_audio_dev in audio_options
            else (self.audio_output.find_preferred_device() or SILENCED_DEVICE_LABEL)
        )
        self.audio_device_menu.set(preferred_audio_dev)
        self.audio_device_menu.pack(fill="x", padx=12, pady=4)

        self.audio_hint_label = ctk.CTkLabel(
            self.controls_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            wraplength=280,
            justify="left",
        )
        self.audio_hint_label.pack(pady=(0, 4), padx=12, anchor="w")

        self.btn_install_vbcable = ctk.CTkButton(
            self.controls_frame,
            text="📥 Instalar Micrófono Virtual (VB-Cable)",
            command=self._install_vbcable_async,
            fg_color="#8A5A00",
            hover_color="#A86E00",
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._update_audio_hint_ui()

        self._add_separator()

        # Motor y Switch de Cámara Virtual
        ctk.CTkLabel(
            self.controls_frame,
            text="Motor de Cámara Virtual",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(4, 2), padx=12, anchor="w")

        backend_values = [
            VCAM_BACKEND_LABELS[VirtualCamBackend.WINDOWS_MF],
            VCAM_BACKEND_LABELS[VirtualCamBackend.UNITY_CAPTURE],
        ]
        self.vcam_backend_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=backend_values,
            command=self._on_vcam_backend_selected,
        )
        self.vcam_backend_menu.set(
            VCAM_BACKEND_LABELS.get(self.vcam.backend, backend_values[0])
        )
        self.vcam_backend_menu.pack(fill="x", padx=12, pady=4)

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
            text=f"Dispositivo: {self.vcam.device_name}\nCompatible con Windows 11, Zoom, Meet, Teams, Discord.",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            wraplength=280,
            justify="left"
        )
        self.vcam_desc.pack(pady=(0, 6), padx=12, anchor="w")

        self.btn_install_driver = ctk.CTkButton(
            self.controls_frame,
            text="📥 Registrar Driver de Cámara (Admin)",
            command=self._install_vcam_driver_async,
            fg_color="#8A5A00",
            hover_color="#A86E00",
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
        )

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

        # Selector de Dispositivos Android (USB o Depuración Inalámbrica)
        ctk.CTkLabel(
            self.controls_frame,
            text="Dispositivo Android (USB / Wi-Fi)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(6, 2), padx=12, anchor="w")

        self.device_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            values=["Buscando dispositivos..."],
            command=self._on_device_selected
        )
        self.device_menu.pack(fill="x", padx=12, pady=4)

        self.device_info_label = ctk.CTkLabel(
            self.controls_frame,
            text=(
                "Enchufa por USB con Depuración activa.\n"
                "💡 En Honor/Huawei: activa 'Transferencia de archivos (MTP)' y "
                "'Permitir ADB en modo solo carga', o usa Depuración Inalámbrica:"
            ),
            font=ctk.CTkFont(size=10),
            text_color="#AAAAAA",
            wraplength=280,
            justify="left"
        )
        self.device_info_label.pack(pady=4, padx=12, anchor="w")

        self.btn_reconnect_adb = ctk.CTkButton(
            self.controls_frame,
            text="🔄 Reescanear USB",
            command=self._reconnect_usb_async,
            fg_color="#1E3A5F",
            hover_color="#2B4C7E",
            height=28,
        )
        self.btn_reconnect_adb.pack(fill="x", padx=12, pady=(4, 8))

        # Depuración Inalámbrica (Android 11+ / Honor / Huawei)
        ctk.CTkLabel(
            self.controls_frame,
            text="Depuración Inalámbrica (ADB Wi-Fi)",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(pady=(4, 2), padx=12, anchor="w")

        self.wireless_addr_entry = ctk.CTkEntry(
            self.controls_frame,
            placeholder_text="IP:Puerto (ej. 192.168.1.40:41555)",
        )
        saved_wireless = self.settings.get("last_wireless_addr", "")
        if saved_wireless:
            self.wireless_addr_entry.insert(0, saved_wireless)
        self.wireless_addr_entry.pack(fill="x", padx=12, pady=(2, 4))

        self.btn_wireless_connect = ctk.CTkButton(
            self.controls_frame,
            text="📡 Conectar Inalámbrico",
            command=self._connect_wireless_async,
            fg_color="#00695C",
            hover_color="#00897B",
            height=28,
        )
        self.btn_wireless_connect.pack(fill="x", padx=12, pady=(2, 4))

        self.btn_toggle_pair = ctk.CTkButton(
            self.controls_frame,
            text="🔐 Emparejar con código (1ra vez)",
            command=self._toggle_pair_box,
            fg_color="#2A2D32",
            hover_color="#3A3D42",
            height=26,
            font=ctk.CTkFont(size=11),
        )
        self.btn_toggle_pair.pack(fill="x", padx=12, pady=(2, 4))

        self.pair_frame = ctk.CTkFrame(self.controls_frame, fg_color="#181A1F", corner_radius=6)
        self._pair_box_visible = False

        self.pair_addr_entry = ctk.CTkEntry(
            self.pair_frame,
            placeholder_text="IP:Puerto de emparejamiento",
            height=26,
        )
        self.pair_addr_entry.pack(fill="x", padx=8, pady=(6, 3))

        self.pair_code_entry = ctk.CTkEntry(
            self.pair_frame,
            placeholder_text="Código Wi-Fi de 6 dígitos",
            height=26,
        )
        self.pair_code_entry.pack(fill="x", padx=8, pady=3)

        self.btn_pair_confirm = ctk.CTkButton(
            self.pair_frame,
            text="✓ Vincular Dispositivo",
            command=self._pair_wireless_async,
            fg_color="#8A5A00",
            hover_color="#A86E00",
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.btn_pair_confirm.pack(fill="x", padx=8, pady=(3, 6))

        self.wireless_status_label = ctk.CTkLabel(
            self.controls_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            wraplength=280,
            justify="left",
        )
        self.wireless_status_label.pack(pady=(0, 4), padx=12, anchor="w")

        self._add_separator()

        # Segundo Plano (System Tray)
        ctk.CTkLabel(
            self.controls_frame,
            text="Segundo Plano (Bandeja)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(6, 2), padx=12, anchor="w")

        self.close_to_tray_switch = ctk.CTkSwitch(
            self.controls_frame,
            text="Minimizar a bandeja al cerrar (X)",
            progress_color="#00E5FF",
            command=self._toggle_close_to_tray,
        )
        if self.settings.get("close_to_tray", True):
            self.close_to_tray_switch.select()
        else:
            self.close_to_tray_switch.deselect()
        self.close_to_tray_switch.pack(pady=4, padx=12, anchor="w")

        self.btn_hide_to_tray = ctk.CTkButton(
            self.controls_frame,
            text="🔽 Ocultar en Bandeja Ahora",
            command=self._hide_to_tray,
            fg_color="#2A2D32",
            hover_color="#3A3D42",
        )
        self.btn_hide_to_tray.pack(fill="x", padx=12, pady=(4, 12))

    def _build_audio_device_options(self) -> List[str]:
        devices = [d["name"] for d in self.audio_output.list_output_devices()]
        devices.append(SILENCED_DEVICE_LABEL)
        return devices

    def _sync_audio_output_with_mode(self, mode: StreamMode):
        if mode == StreamMode.VIDEO_ONLY:
            self.audio_output.set_muted(True)
        else:
            self.audio_output.set_muted(False)
            selected_dev = self.audio_device_menu.get()
            if not self.audio_output.is_active and selected_dev != SILENCED_DEVICE_LABEL:
                self.audio_output.start(selected_dev)

    def _on_mode_menu_selected(self, label: str):
        mode = LABEL_TO_STREAM_MODE.get(label, StreamMode.AUDIO_VIDEO)
        self.settings["stream_mode"] = label
        self._save_settings()
        self.receiver.set_stream_mode(mode, notify_remote=True)
        self._sync_audio_output_with_mode(mode)
        if hasattr(self, "tray_manager"):
            self.tray_manager.update_menu()

    def _on_remote_mode_changed(self, mode: StreamMode):
        def _apply():
            label = STREAM_MODE_LABELS.get(mode, STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO])
            self.mode_menu.set(label)
            self.settings["stream_mode"] = label
            self._save_settings()
            self._sync_audio_output_with_mode(mode)
            if hasattr(self, "tray_manager"):
                self.tray_manager.update_menu()

        self.after(0, _apply)

    def _on_audio_device_selected(self, device_name: str):
        self.settings["audio_output_device"] = device_name
        self._save_settings()
        self.audio_output.set_device(device_name)
        self._update_audio_hint_ui()

    def _update_audio_hint_ui(self):
        has_cable = self.audio_output.has_virtual_cable()
        selected_dev = self.audio_device_menu.get()
        if has_cable:
            self.btn_install_vbcable.pack_forget()
            if "cable input" in selected_dev.lower():
                self.audio_hint_label.configure(
                    text="✓ Micrófono virtual activo. En Discord/Meet/Zoom elige 'CABLE Output' como micrófono.",
                    text_color="#00E676",
                )
            else:
                self.audio_hint_label.configure(
                    text="💡 Selecciona 'CABLE Input' arriba para que Discord/Meet detecten tu micrófono.",
                    text_color="#888888",
                )
        else:
            self.audio_hint_label.configure(
                text="⚠️ VB-Cable no detectado: el audio saldrá por tus altavoces. Instálalo para usarlo como micrófono en Discord/Meet.",
                text_color="#FFBB33",
            )
            self.btn_install_vbcable.pack(fill="x", padx=12, pady=(2, 6), after=self.audio_hint_label)

    def _install_vbcable_async(self):
        self.btn_install_vbcable.configure(state="disabled", text="⏳ Instalando VB-Cable...")

        def _task():
            script_path = find_driver_script("install_vbcable.bat")
            try:
                if script_path:
                    subprocess.run(["cmd.exe", "/c", script_path], check=False)
                else:
                    ps_cmd = (
                        "$workDir = Join-Path $env:TEMP 'droidlens_vbcable'; "
                        "$zipPath = Join-Path $workDir 'vbcable.zip'; "
                        "New-Item -ItemType Directory -Path $workDir -Force | Out-Null; "
                        "Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip' -OutFile $zipPath -UseBasicParsing; "
                        "Expand-Archive -Path $zipPath -DestinationPath $workDir -Force; "
                        "$exe = if ([Environment]::Is64BitOperatingSystem) { Join-Path $workDir 'VBCABLE_Setup_x64.exe' } else { Join-Path $workDir 'VBCABLE_Setup.exe' }; "
                        "Start-Process -FilePath $exe -Verb RunAs -Wait"
                    )
                    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], check=False)
            except Exception:
                pass
            self.audio_output.refresh_devices()
            self.after(0, self._refresh_audio_ui_after_install)

        threading.Thread(target=_task, daemon=True).start()

    def _refresh_audio_ui_after_install(self):
        self.btn_install_vbcable.configure(state="normal", text="📥 Instalar Micrófono Virtual (VB-Cable)")
        options = self._build_audio_device_options()
        self.audio_device_menu.configure(values=options)
        preferred = self.audio_output.find_preferred_device() or SILENCED_DEVICE_LABEL
        if self.audio_output.has_virtual_cable() and preferred in options:
            self.audio_device_menu.set(preferred)
            self._on_audio_device_selected(preferred)
        else:
            self._update_audio_hint_ui()

    def _add_separator(self):
        sep = ctk.CTkProgressBar(self.controls_frame, height=2)
        sep.set(1.0)
        sep.pack(fill="x", padx=12, pady=8)

    def _on_vcam_backend_selected(self, label: str):
        backend = LABEL_TO_VCAM_BACKEND.get(label, VirtualCamBackend.WINDOWS_MF)
        self.settings["vcam_backend"] = label
        self._save_settings()

        if self.vcam.set_backend(backend):
            self.btn_install_driver.pack_forget()
            if self.is_vcam_enabled and self.vcam.is_active:
                self.vcam_desc.configure(
                    text=f"Cámara Virtual ACTIVA.\nSelecciona '{self.vcam.device_name}' en tu app.",
                    text_color="#00E676",
                )
            else:
                self.vcam_desc.configure(
                    text=f"Dispositivo: {self.vcam.device_name}\nCompatible con Windows 11, Zoom, Meet, Teams, Discord.",
                    text_color="#888888",
                )
        else:
            self.vcam_switch.deselect()
            self.is_vcam_enabled = False
            self.vcam_desc.configure(
                text=self.vcam.last_error or "Error al cambiar el motor de cámara virtual.",
                text_color="#FF5252",
            )
            self.btn_install_driver.pack(fill="x", padx=12, pady=(2, 8), after=self.vcam_desc)

    def _install_vcam_driver_async(self):
        self.btn_install_driver.configure(state="disabled", text="⏳ Registrando Driver...")

        def _task():
            script_path = find_driver_script("install_driver.bat")
            try:
                if script_path:
                    subprocess.run(["cmd.exe", "/c", script_path], check=False)
            except Exception:
                pass
            self.after(0, self._refresh_vcam_ui_after_install)

        threading.Thread(target=_task, daemon=True).start()

    def _refresh_vcam_ui_after_install(self):
        self.btn_install_driver.configure(state="normal", text="📥 Registrar Driver de Cámara (Admin)")
        self.btn_install_driver.pack_forget()
        self.vcam_desc.configure(
            text=f"✓ Driver registrado. Activa el switch de '{self.vcam.device_name}'.",
            text_color="#00E676",
        )

    def _toggle_vcam(self):
        self.is_vcam_enabled = self.vcam_switch.get()
        if self.is_vcam_enabled:
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
                    text=self.vcam.last_error or "Error al iniciar cámara virtual.\n¿Ejecutaste driver\\install_driver.bat?",
                    text_color="#FF5252"
                )
                self.btn_install_driver.pack(fill="x", padx=12, pady=(2, 8), after=self.vcam_desc)
            else:
                self.btn_install_driver.pack_forget()
                self.vcam_desc.configure(
                    text=f"Cámara Virtual ACTIVA.\nSelecciona '{self.vcam.device_name}' en tu app.",
                    text_color="#00E676"
                )
        else:
            self.vcam.stop()
            self.btn_install_driver.pack_forget()
            self.vcam_desc.configure(
                text=f"Cámara Virtual DETENIDA ({self.vcam.device_name}).",
                text_color="#888888"
            )
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
            self.adb_manager.ensure_usb_vendor_ids()
            self.adb_manager.restart_server()
            time.sleep(0.5)
            serial = self.adb_manager.selected_serial
            self.adb_manager.setup_port_forward(8080, 8080, serial=serial)
        threading.Thread(target=_task, daemon=True).start()

    def _toggle_pair_box(self):
        self._pair_box_visible = not self._pair_box_visible
        if self._pair_box_visible:
            self.pair_frame.pack(fill="x", padx=12, pady=(2, 6), after=self.btn_toggle_pair)
            self.btn_toggle_pair.configure(text="🔼 Ocultar emparejamiento")
        else:
            self.pair_frame.pack_forget()
            self.btn_toggle_pair.configure(text="🔐 Emparejar con código (1ra vez)")

    def _pair_wireless_async(self):
        pair_addr = self.pair_addr_entry.get().strip()
        pair_code = self.pair_code_entry.get().strip()
        self.btn_pair_confirm.configure(state="disabled", text="⏳ Emparejando...")

        def _task():
            ok, msg = self.adb_manager.pair_wireless(pair_addr, pair_code)
            def _done():
                self.btn_pair_confirm.configure(state="normal", text="✓ Vincular Dispositivo")
                self.wireless_status_label.configure(
                    text=msg,
                    text_color="#00E676" if ok else "#FF5252",
                )
                if ok and ":" in pair_addr and not self.wireless_addr_entry.get().strip():
                    ip_only = pair_addr.split(":")[0]
                    self.wireless_addr_entry.insert(0, f"{ip_only}:")
            self.after(0, _done)

        threading.Thread(target=_task, daemon=True).start()

    def _connect_wireless_async(self):
        addr = self.wireless_addr_entry.get().strip()
        self.btn_wireless_connect.configure(state="disabled", text="⏳ Conectando...")

        def _task():
            ok, msg = self.adb_manager.connect_wireless(addr)
            if ok:
                self.settings["last_wireless_addr"] = addr
                self.settings["last_serial"] = addr
                self._save_settings()
                self.adb_manager.setup_port_forward(8080, 8080, serial=addr, check_state=False)
                devices = self.adb_manager.list_devices()
                self.after(0, self._update_devices_ui, devices)

            def _done():
                self.btn_wireless_connect.configure(state="normal", text="📡 Conectar Inalámbrico")
                self.wireless_status_label.configure(
                    text=msg,
                    text_color="#00E676" if ok else "#FF5252",
                )
            self.after(0, _done)

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
            self.status_badge.configure(text="Buscando USB / Wi-Fi...", fg_color="#333333")
            self.device_info_label.configure(
                text=(
                    "Desconectado.\n"
                    "💡 En Honor/Huawei: activa 'Transferencia de archivos (MTP)' y "
                    "'Permitir ADB en modo solo carga', o usa Depuración Inalámbrica:"
                ),
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
            tag = "Wi-Fi" if ":" in serial else serial[-4:]
            name = f"{model} ({tag})"
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
            threading.Thread(target=lambda: self.adb_manager.setup_port_forward(8080, 8080, serial=first_serial), daemon=True).start()

        self.device_menu.configure(values=display_names)
        if selected_name:
            self.device_menu.set(selected_name)

        active_dev = next((d for d in devices if d["serial"] == self.adb_manager.selected_serial), devices[0])
        is_wireless = ":" in active_dev["serial"]
        if active_dev["state"] == "device":
            badge_txt = "ADB Inalámbrico" if is_wireless else "USB Conectado"
            link_txt = f"Wi-Fi ({active_dev['serial']})" if is_wireless else "Túnel USB tcp:8080"
            self.status_badge.configure(text=badge_txt, fg_color="#007E33")
            self.device_info_label.configure(
                text=f"Modelo: {active_dev['model']}\nEstado: Listo ({link_txt})",
                text_color="#00E676"
            )
        elif active_dev["state"] == "unauthorized":
            self.status_badge.configure(text="Autorizar en Celular", fg_color="#FF8800")
            self.device_info_label.configure(
                text="Acepta el diálogo de 'Permitir depuración'\nen la pantalla de tu celular.",
                text_color="#FFBB33"
            )
        else:
            self.status_badge.configure(text="Dispositivo Offline", fg_color="#555555")
            self.device_info_label.configure(
                text=f"Estado: {active_dev['state']}\nReconecta el cable USB o vuelve a conectar por Wi-Fi.",
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
            elif result.status == FrameStatus.AUDIO_ONLY_MODE:
                self._is_in_standby = True
                processed = self.processor.generate_audio_only_frame(audio_active=self.audio_output.is_active)
            else:
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

        # Si está oculta en la bandeja del sistema, omitir el renderizado visual para ahorrar CPU
        if self._is_hidden_in_tray:
            self.after(250, self._ui_refresh_tick)
            return

        frame = self._latest_display_frame
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

    def _toggle_close_to_tray(self):
        val = bool(self.close_to_tray_switch.get())
        self.settings["close_to_tray"] = val
        self._save_settings()

    def _hide_to_tray(self):
        """Oculta la ventana de la barra de tareas y mantiene DroidLens en la bandeja del sistema."""
        if hasattr(self, "tray_manager") and self.tray_manager.is_running:
            self._is_hidden_in_tray = True
            self.withdraw()

    def _restore_from_tray_safe(self):
        self.after(0, self._restore_from_tray)

    def _restore_from_tray(self):
        self._is_hidden_in_tray = False
        self._last_rendered_id = -2
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _on_tray_mode_selected(self, mode: StreamMode):
        def _apply():
            label = STREAM_MODE_LABELS.get(mode, STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO])
            self.mode_menu.set(label)
            self._on_mode_menu_selected(label)

        self.after(0, _apply)

    def _on_window_unmap(self, event=None):
        """Si el usuario minimiza la ventana y el modo bandeja está activo, ocultarla de la barra de tareas."""
        if event is not None and event.widget is not self:
            return
        try:
            if (
                self.settings.get("close_to_tray", True)
                and hasattr(self, "tray_manager")
                and self.tray_manager.is_running
                and self.state() == "iconic"
            ):
                self.after(10, self._hide_to_tray)
        except Exception:
            pass

    def _on_close_button(self):
        """Intercepta el botón X: oculta en bandeja si está habilitado; de lo contrario cierra la app."""
        if (
            self.settings.get("close_to_tray", True)
            and hasattr(self, "tray_manager")
            and self.tray_manager.is_running
        ):
            self._hide_to_tray()
        else:
            self._quit_app()

    def _quit_app_safe(self):
        self.after(0, self._quit_app)

    def _quit_app(self):
        self.is_running = False
        if hasattr(self, "tray_manager"):
            self.tray_manager.stop()
        try:
            self.adb_manager.remove_port_forward(8080)
        except Exception:
            pass
        self.receiver.stop()
        self.audio_output.stop()
        self.vcam.stop()
        self.destroy()


if __name__ == "__main__":
    app = DroidLensApp()
    app.mainloop()

