"""Self-contained UI panels. Each owns its widgets and its own refresh logic, so ui.py only has to
create them, style them and call refresh/update."""
import time

import customtkinter as ctk

import audio
from widgets import style_mute_button, track_drag


def format_time(seconds):
    """83 -> '1:23', 3725 -> '1:02:05'."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class ProgressBar:
    """Track position with elapsed/total time. Click or drag to seek (if the app allows it)."""

    SEEK_HOLD = 1.5   # after a seek, show the target for a moment: apps are slow to report the new position

    def __init__(self, parent, font_family, drag, on_seek):
        self._drag = drag
        self._on_seek = on_seek
        self._duration = 0.0
        self._can_seek = False
        self._enabled = None
        self._hold_pos = None
        self._hold_until = 0.0

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.left = ctk.CTkLabel(self.frame, text="0:00", width=38, font=(font_family, 9), anchor="w")
        self.left.pack(side="left")
        self.right = ctk.CTkLabel(self.frame, text="0:00", width=38, font=(font_family, 9), anchor="e")
        self.right.pack(side="right")
        # a slider with its knob hidden works as a seekable progress bar
        self.slider = ctk.CTkSlider(self.frame, from_=0.0, to=1.0, height=8, button_length=0)
        self.slider.pack(side="left", fill="x", expand=True, padx=4)
        self.slider.set(0.0)
        track_drag(self.slider, drag)
        try:
            self.slider.bind("<ButtonRelease-1>", self._released, add="+")
        except Exception:
            pass

    def widgets_for_background(self):
        """Widgets nested one level inside `frame` (CTk won't repaint these when the panel colour changes)."""
        return (self.left, self.right, self.slider)

    def style(self, theme, track_default):
        self.left.configure(text_color=theme["subtext"])
        self.right.configure(text_color=theme["subtext"])
        self.slider.configure(progress_color=theme["accent"], button_color=theme["accent"],
                              button_hover_color=theme["accent"], fg_color=theme.get("track", track_default))

    def _set_enabled(self, enabled):
        if enabled != self._enabled:
            self._enabled = enabled
            try: self.slider.configure(state="normal" if enabled else "disabled")
            except Exception: pass

    def _set_text(self, label, text):
        if label.cget("text") != text:
            label.configure(text=text)

    def update(self, state):
        """Called a couple of times a second with the latest media state."""
        duration = state.duration_s if state.present else 0.0
        self._duration = duration
        self._can_seek = bool(state.present and state.can_seek and duration > 0)
        self._set_enabled(self._can_seek)

        if duration <= 0:
            if not self._drag.active:
                self.slider.set(0.0)
            self._set_text(self.left, "0:00")
            self._set_text(self.right, "--:--" if state.present else "0:00")
            return

        now = time.monotonic()
        if self._drag.active:                       # the user is holding the bar: show where they'd land
            pos = self.slider.get() * duration
        elif self._hold_pos is not None and now < self._hold_until:
            pos = self._hold_pos
        else:
            self._hold_pos = None
            pos = state.position_s + ((now - state.stamp) if state.status == "playing" else 0.0)
            pos = min(max(pos, 0.0), duration)
        if not self._drag.active:
            self.slider.set(pos / duration)
        self._set_text(self.left, format_time(pos))
        self._set_text(self.right, format_time(duration))

    def _released(self, event=None):
        if not (self._can_seek and self._duration > 0):
            return
        target = self.slider.get() * self._duration
        self._hold_pos = target
        self._hold_until = time.monotonic() + self.SEEK_HOLD
        self._on_seek(target)


class MasterBox:
    """Master volume for the default output device, plus a picker to switch which device that is."""

    DEVICE_REFRESH_EVERY = 5   # refresh() calls between re-reading the device list

    def __init__(self, parent, font_family, drag):
        self._drag = drag
        self.muted = False
        self._ticks = 0
        self._label_to_id = {}
        self._labels = []
        self._current_id = None
        self._theme = None

        self.frame = ctk.CTkFrame(parent, corner_radius=12)

        self.header = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.header.pack(fill="x", padx=8, pady=(6, 0))
        self.title = ctk.CTkLabel(self.header, text="Master", font=(font_family, 11, "bold"), anchor="w")
        self.title.pack(side="left", padx=(2, 0))
        self.device_menu = ctk.CTkOptionMenu(self.header, values=["(no device)"], width=170, height=22,
                                             font=(font_family, 9), dropdown_font=(font_family, 9),
                                             dynamic_resizing=False, command=self._device_chosen)
        self.device_menu.pack(side="right")

        self.controls = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.controls.pack(fill="x", padx=8, pady=(2, 6))
        self.slider = ctk.CTkSlider(self.controls, from_=0.0, to=1.0, height=14, command=self._slider_moved)
        self.slider.pack(side="left", fill="x", expand=True, padx=(0, 6))
        track_drag(self.slider, drag)
        self.mute_btn = ctk.CTkButton(self.controls, text="🔊 ON", width=55, height=22, corner_radius=8,
                                      font=(font_family, 9, "bold"), command=self._toggle_mute)
        self.mute_btn.pack(side="right")

    def widgets_for_background(self):
        return (self.title, self.device_menu, self.slider, self.mute_btn)

    def style(self, theme, track_default):
        self._theme = theme
        self.title.configure(text_color=theme["accent"])
        self.slider.configure(button_color=theme["accent"], button_hover_color=theme["hover"],
                              progress_color=theme["accent"], fg_color=theme.get("track", track_default))
        self.device_menu.configure(fg_color=theme["button_bg"], button_color=theme["button_bg"],
                                   button_hover_color=theme["button_hover"], text_color=theme["text"],
                                   dropdown_fg_color=theme["button_bg"], dropdown_hover_color=theme["button_hover"],
                                   dropdown_text_color=theme["text"])
        style_mute_button(self.mute_btn, self.muted, theme["button_bg"], theme)

    # ---- actions ----
    def _slider_moved(self, value):
        audio.set_master_volume(value)

    def _toggle_mute(self):
        audio.toggle_master_mute()
        self.refresh()

    def _device_chosen(self, label):
        device_id = self._label_to_id.get(label)
        if device_id and device_id != self._current_id:
            audio.set_default_device(device_id)
        self.refresh(force_devices=True)

    # ---- sync with Windows ----
    def refresh(self, force_devices=False):
        info = audio.read_master()
        if info is None:
            self.title.configure(text="Master (no output device)")
            return
        self.title.configure(text="Master")
        self._current_id = info["id"]

        if not self._drag.active and abs(self.slider.get() - info["level"]) > 0.005:
            self.slider.set(info["level"])
        if info["muted"] != self.muted and self._theme is not None:
            self.muted = info["muted"]
            style_mute_button(self.mute_btn, self.muted, self._theme["button_bg"], self._theme)

        if force_devices or self._ticks % self.DEVICE_REFRESH_EVERY == 0:
            self._refresh_devices(info)
        self._ticks += 1
        current = next((label for label, did in self._label_to_id.items() if did == info["id"]), None)
        if current and self.device_menu.get() != current:
            self.device_menu.set(current)

    def _refresh_devices(self, info):
        devices = audio.list_output_devices()
        if not devices:                       # can't list them: show just the current one
            devices = [(info["id"], info["name"])]
        mapping, seen = {}, {}
        for device_id, name in devices:       # two identical names would collide in the menu, so number them
            seen[name] = seen.get(name, 0) + 1
            label = name if seen[name] == 1 else f"{name} ({seen[name]})"
            mapping[label] = device_id
        if list(mapping) != self._labels:
            self._labels = list(mapping)
            self.device_menu.configure(values=self._labels)
        self._label_to_id = mapping
