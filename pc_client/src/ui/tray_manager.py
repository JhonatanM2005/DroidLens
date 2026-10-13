"""
Gestor de Bandeja del Sistema (System Tray) para DroidLens en Windows.
Permite ocultar la ventana principal de la barra de tareas, prevenir cierres
accidentales con el botón 'X', conmutar modos de transmisión desde el menú
contextual y cerrar completamente la aplicación cuando el usuario lo solicite.
"""

from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None

try:
    from core.protocol import StreamMode, STREAM_MODE_LABELS
except ImportError:
    from ..core.protocol import StreamMode, STREAM_MODE_LABELS


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """Genera un icono RGBA moderno en memoria para la bandeja del sistema."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo circular azul oscuro con borde celeste
    pad = max(2, size // 16)
    draw.ellipse(
        [pad, pad, size - pad, size - pad],
        fill=(18, 32, 56, 255),
        outline=(30, 144, 255, 255),
        width=max(2, size // 16),
    )

    # Lente central de cámara
    inner_pad = size // 4
    draw.ellipse(
        [inner_pad, inner_pad, size - inner_pad, size - inner_pad],
        fill=(30, 144, 255, 255),
        outline=(255, 255, 255, 255),
        width=max(2, size // 24),
    )

    # Punto indicador activo (verde esmeralda)
    dot_r = max(4, size // 8)
    dot_x = size - pad - dot_r * 2
    dot_y = pad + dot_r // 2
    draw.ellipse(
        [dot_x, dot_y, dot_x + dot_r * 2, dot_y + dot_r * 2],
        fill=(0, 230, 118, 255),
    )
    return img


class TrayManager:
    """Administra el icono de notificación en segundo plano (System Tray)."""

    def __init__(
        self,
        on_restore: Callable[[], None],
        on_select_mode: Callable[[StreamMode], None],
        on_quit: Callable[[], None],
        get_current_mode: Optional[Callable[[], StreamMode]] = None,
        icon_factory: Optional[Callable] = None,
    ):
        self._on_restore = on_restore
        self._on_select_mode = on_select_mode
        self._on_quit = on_quit
        self._get_current_mode = get_current_mode or (lambda: StreamMode.AUDIO_VIDEO)
        self._icon_factory = icon_factory
        self._icon = None
        self.is_running = False

    def _build_menu(self):
        if pystray is None:
            return None

        def _make_mode_action(mode: StreamMode):
            def _action(icon, item):
                self.trigger_select_mode(mode)
            return _action

        def _make_mode_checked(mode: StreamMode):
            def _checked(item):
                return self._get_current_mode() == mode
            return _checked

        return pystray.Menu(
            pystray.MenuItem(
                "Abrir DroidLens",
                lambda icon, item: self.trigger_restore(),
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                STREAM_MODE_LABELS[StreamMode.AUDIO_VIDEO],
                _make_mode_action(StreamMode.AUDIO_VIDEO),
                checked=_make_mode_checked(StreamMode.AUDIO_VIDEO),
                radio=True,
            ),
            pystray.MenuItem(
                STREAM_MODE_LABELS[StreamMode.VIDEO_ONLY],
                _make_mode_action(StreamMode.VIDEO_ONLY),
                checked=_make_mode_checked(StreamMode.VIDEO_ONLY),
                radio=True,
            ),
            pystray.MenuItem(
                STREAM_MODE_LABELS[StreamMode.AUDIO_ONLY],
                _make_mode_action(StreamMode.AUDIO_ONLY),
                checked=_make_mode_checked(StreamMode.AUDIO_ONLY),
                radio=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Salir de DroidLens",
                lambda icon, item: self.trigger_quit(),
            ),
        )

    def start(self) -> bool:
        """Inicia el icono en la bandeja del sistema en modo desacoplado."""
        if self.is_running:
            return True

        image = create_tray_icon_image(64)
        factory = self._icon_factory or (pystray.Icon if pystray is not None else None)
        if factory is None:
            return False

        try:
            menu = self._build_menu()
            self._icon = factory("DroidLens", image, "DroidLens — En segundo plano", menu)
            if hasattr(self._icon, "run_detached"):
                self._icon.run_detached()
            self.is_running = True
            return True
        except Exception:
            self._icon = None
            self.is_running = False
            return False

    def update_menu(self):
        """Refresca el estado visual del menú contextual de la bandeja."""
        if self._icon and hasattr(self._icon, "update_menu"):
            try:
                self._icon.update_menu()
            except Exception:
                pass

    def trigger_restore(self):
        if self._on_restore:
            self._on_restore()

    def trigger_select_mode(self, mode: StreamMode):
        if self._on_select_mode:
            self._on_select_mode(mode)
        self.update_menu()

    def trigger_quit(self):
        if self._on_quit:
            self._on_quit()

    def stop(self):
        """Detiene y elimina el icono de la bandeja del sistema."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        self.is_running = False
