"""Windows-only window effects for the glass theme (blur-behind and rounded corners).

Everything here fails safely: on an unsupported system the helpers return False / do nothing,
and the UI falls back to solid colours."""
import ctypes
from ctypes import wintypes


class _AccentPolicy(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


ACCENT_DISABLED = 0
ACCENT_TRANSPARENTGRADIENT = 2   # plain translucent tint, no blur (cheap: used while dragging)
ACCENT_ACRYLIC = 4               # blurred backdrop + tint


def top_level_hwnd(widget):
    hwnd = widget.winfo_id()
    return ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd   # 2 = GA_ROOT


def set_window_accent(hwnd, state, rgb=(0, 0, 0), alpha=0x70):
    """Undocumented Win10/11 call (SetWindowCompositionAttribute). Returns True if Windows accepted it."""
    try:
        r, g, b = rgb
        accent = _AccentPolicy(state, 2, (alpha << 24) | (b << 16) | (g << 8) | r, 0)
        data = _WinCompAttrData(19, ctypes.addressof(accent), ctypes.sizeof(accent))   # 19 = WCA_ACCENT_POLICY
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(_WinCompAttrData)]
        fn.restype = wintypes.BOOL
        return bool(fn(hwnd, ctypes.byref(data)))
    except Exception:
        return False


def set_round_corners(hwnd, on):
    """Windows 11 only; silently does nothing elsewhere."""
    try:
        pref = ctypes.c_int(2 if on else 0)   # DWMWCP_ROUND / DWMWCP_DEFAULT
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


class GlassEffect:
    """Tracks the blur state of one window so the UI doesn't have to."""

    def __init__(self, window):
        self.window = window
        self.active = False     # blur is currently on
        self.used = False       # we've touched the window, so it must be cleaned up when the theme changes
        self.dragging = False   # blur temporarily swapped for a cheap tint while the window is dragged

    def apply(self, tint, alpha):
        """Turn the blur on. Returns True if Windows accepted it."""
        try:
            hwnd = top_level_hwnd(self.window)
        except Exception:
            return False
        ok = set_window_accent(hwnd, ACCENT_ACRYLIC, tint, alpha)
        set_round_corners(hwnd, True)
        self.active = ok
        self.used = True
        self.dragging = False
        return ok

    def clear(self):
        try:
            hwnd = top_level_hwnd(self.window)
            set_window_accent(hwnd, ACCENT_DISABLED)
            set_round_corners(hwnd, False)
        except Exception:
            pass
        self.active = False
        self.used = False
        self.dragging = False

    def begin_drag(self, tint, alpha):
        """Acrylic makes dragging laggy on some Windows builds, so use a plain tint while moving."""
        if self.active and not self.dragging:
            self.dragging = True
            set_window_accent(top_level_hwnd(self.window), ACCENT_TRANSPARENTGRADIENT, tint, alpha)

    def end_drag(self, tint, alpha):
        if self.dragging:
            self.dragging = False
            self.apply(tint, alpha)
