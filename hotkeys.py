"""Global hotkey: parsing/validation helpers and a manager that listens and lets the user remap it."""
from pynput import keyboard

MODIFIER_TAGS = ("<ctrl>", "<shift>", "<alt>")


def hotkey_is_valid(hotkey_str):
    """Must parse in pynput's syntax AND include a modifier, so typing a plain letter can't toggle the overlay."""
    try:
        keyboard.HotKey.parse(hotkey_str)
    except Exception:
        return False
    return any(tag in hotkey_str for tag in MODIFIER_TAGS)


def format_hotkey(hotkey_str):
    parts = []
    for p in hotkey_str.split("+"):
        p = p.strip("<>")
        parts.append(p.capitalize() if len(p) > 1 else p.upper())
    return "+".join(parts)


def key_to_tag(key):
    """Convert a pynput key event into the tag pynput's GlobalHotKeys expects."""
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return "<ctrl>"
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        return "<shift>"
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, getattr(keyboard.Key, "alt_gr", None)):
        return "<alt>"
    # Letters/digits: use the virtual-key code. With Ctrl held, key.char can come through as a control character.
    vk = getattr(key, "vk", None)
    if vk is not None:
        if 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:
            return chr(vk)
    # Named keys (F5, space, ...) need angle brackets: "<f5>", not "f5"
    name = getattr(key, "name", None)
    if name:
        return f"<{name.lower()}>"
    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()
    return None


class HotkeyManager:
    """Owns the global hotkey and the "press a new combo" recorder.

    The UI supplies three callbacks, all invoked on the Tk thread:
      on_trigger()        the hotkey was pressed
      on_status(text)     show this text on the hotkey button
      on_changed(hotkey)  the user picked a new valid hotkey (so the UI can save it)
    """

    def __init__(self, root, hotkey, on_trigger, on_status, on_changed):
        self.root = root
        self.hotkey = hotkey
        self._on_trigger = on_trigger
        self._on_status = on_status
        self._on_changed = on_changed
        self._listener = None
        self._recorder = None

    def label(self):
        return f"Hotkey: {format_hotkey(self.hotkey)} (Click to Remap)"

    def start(self):
        self.stop()
        try:
            self._listener = keyboard.GlobalHotKeys({self.hotkey: lambda: self.root.after(0, self._on_trigger)})
            self._listener.start()
        except Exception as e:
            print(f"Hotkey error: {e}")
            self._on_status("Hotkey failed - click to remap")

    def stop(self):
        if self._listener:
            try: self._listener.stop()
            except Exception: pass
            self._listener = None

    def begin_recording(self):
        if self._recorder and self._recorder.running:
            return
        self._on_status("Hold Ctrl/Shift/Alt, press a key (Esc cancels)")
        self.stop()   # so the old hotkey doesn't fire while recording
        recorded = []

        def on_press(key):
            if key == keyboard.Key.esc:
                self.root.after(0, self._cancel)
                return False
            tag = key_to_tag(key)
            if not tag or tag in recorded:
                return
            recorded.append(tag)
            if tag in MODIFIER_TAGS:
                return
            mods = [k for k in recorded if k in MODIFIER_TAGS]
            if not mods:
                recorded.clear()
                self.root.after(0, lambda: self._on_status("Hold Ctrl, Shift or Alt first"))
                return
            hotkey = "+".join(mods + [tag])
            self.root.after(0, lambda: self._finish(hotkey))
            return False

        self._recorder = keyboard.Listener(on_press=on_press)
        self._recorder.start()

    def _finish(self, hotkey):
        if hotkey_is_valid(hotkey):
            self.hotkey = hotkey
            self._on_changed(hotkey)
            self._on_status(self.label())
        else:
            self._on_status("That key can't be used")
            self.root.after(1500, lambda: self._on_status(self.label()))
        self.start()

    def _cancel(self):
        self._on_status(self.label())
        self.start()
