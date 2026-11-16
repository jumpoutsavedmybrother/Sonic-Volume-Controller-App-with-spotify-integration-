"""System tray icon (left-click = show/hide; menu: Start with Windows, Quit).

pystray runs its own event loop, so it lives on a background thread. Its callbacks must never touch Tk
directly: they hand the work to the Tk thread with root.after(0, ...). If pystray isn't installed the
program still works (hotkey + Quit button), it just has no tray icon."""
import threading

from PIL import Image


class TrayIcon:
    def __init__(self, root, icon_path, on_toggle, on_quit, autostart_get, autostart_set):
        self._root = root
        self._icon_path = icon_path
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._autostart_get = autostart_get
        self._autostart_set = autostart_set
        self._icon = None
        self.available = False

    def _later(self, fn):
        try:
            self._root.after(0, fn)
        except Exception:
            pass   # window already closed

    def _toggle_autostart(self, icon, item):
        self._autostart_set(not self._autostart_get())

    def _load_image(self):
        try:
            return Image.open(self._icon_path).convert("RGBA")
        except Exception:
            return Image.new("RGBA", (64, 64), (29, 185, 84, 255))   # plain green square if the .ico is missing

    def start(self):
        """Returns True if the tray icon is running."""
        try:
            import pystray
        except ImportError:
            print("pystray isn't installed, so there's no tray icon (pip install pystray)")
            return False
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", lambda icon, item: self._later(self._on_toggle), default=True),
            pystray.MenuItem("Start with Windows", self._toggle_autostart, checked=lambda item: self._autostart_get()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda icon, item: self._later(self._on_quit)),
        )
        self._icon = pystray.Icon("Sonic", self._load_image(), "Sonic", menu)
        # icon.run() on a thread is more reliable on Windows than run_detached()
        threading.Thread(target=self._icon.run, name="tray", daemon=True).start()
        self.available = True
        return True

    def stop(self):
        if self._icon is not None:
            try: self._icon.stop()
            except Exception: pass
            self._icon = None
        self.available = False
