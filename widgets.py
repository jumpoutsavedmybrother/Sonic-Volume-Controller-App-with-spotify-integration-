"""Reusable UI pieces. Nothing here knows about the main window, so they can be reused or tested alone."""
import customtkinter as ctk
from PIL import Image, ImageDraw

import audio


class DragFlag:
    """Shared "is the user holding a slider?" flag, so refreshes don't fight the mouse."""
    def __init__(self):
        self.active = False


def track_drag(slider, flag):
    try:
        slider.bind("<ButtonPress-1>", lambda e: setattr(flag, "active", True), add="+")
        slider.bind("<ButtonRelease-1>", lambda e: setattr(flag, "active", False), add="+")
    except Exception:
        pass


def style_mute_button(btn, muted, idle_fg, theme):
    """Red when muted, otherwise the theme's idle look."""
    if muted:
        btn.configure(text="🔇 MUTED", fg_color="#D32F2F", hover_color="#9A0007", text_color="white")
    else:
        btn.configure(text="🔊 ON", fg_color=idle_fg, hover_color=theme["button_hover"], text_color=theme["text"])


def make_spotify_icon(color_hex, size=24):
    img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size * 4, size * 4], fill=color_hex)
    dark_bg = (18, 18, 18, 255) if color_hex != "#111827" else (255, 255, 255, 255)
    draw.arc([int(size * 0.7), int(size * 0.8), int(size * 3.3), int(size * 3.2)], start=200, end=340, fill=dark_bg, width=int(size * 0.35))
    draw.arc([int(size * 0.85), int(size * 1.4), int(size * 3.15), int(size * 3.6)], start=200, end=340, fill=dark_bg, width=int(size * 0.32))
    draw.arc([int(size * 1.0), int(size * 2.0), int(size * 3.0), int(size * 4.0)], start=200, end=340, fill=dark_bg, width=int(size * 0.28))
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=resized, dark_image=resized, size=(size, size))


class SessionRow:
    """One "other audio source": app name, mute button and volume slider."""

    def __init__(self, parent, proc, name, font_family, drag, on_mute_clicked, on_volume_moved, theme, track_default):
        self.proc = proc                  # e.g. "discord.exe": what the volume memory is keyed on
        self.vol = None
        self.muted = False
        self._drag = drag
        self._on_mute_clicked = on_mute_clicked      # called with this row
        self._on_volume_moved = on_volume_moved      # called with (row, value)
        self._theme = theme

        self.container = ctk.CTkFrame(parent, fg_color="transparent")
        self.container.pack(fill="x")

        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(2, 0), padx=2)
        self.label = ctk.CTkLabel(header, text=name, font=(font_family, 10, "bold"))
        self.label.pack(side="left")
        self.mute_btn = ctk.CTkButton(header, text="🔊 ON", width=55, height=18, corner_radius=6,
                                      font=(font_family, 8, "bold"), command=self._clicked_mute)
        self.mute_btn.pack(side="right")

        self.slider = ctk.CTkSlider(self.container, from_=0.0, to=1.0, height=12, command=self._slider_moved)
        self.slider.pack(fill="x", pady=(0, 4), padx=2)
        track_drag(self.slider, drag)

        self.style(theme, track_default)

    def _clicked_mute(self):
        if self.vol is not None:
            self._on_mute_clicked(self)

    def _slider_moved(self, value):
        audio.set_volume(self.vol, value)
        self._on_volume_moved(self, value)

    def style(self, theme, track_default):
        self._theme = theme
        self.label.configure(text_color=theme["text"])
        self.slider.configure(button_color=theme["accent"], button_hover_color=theme["hover"],
                              progress_color=theme["accent"], fg_color=theme.get("track", track_default))
        style_mute_button(self.mute_btn, self.muted, theme["button_hover"], theme)

    def update(self, session):
        """Sync with the live session. Returns False if the session has gone away."""
        try:
            vol = audio.volume_interface(session)
            level, muted = audio.read_volume(vol)
        except Exception:
            return False
        self.vol = vol
        if not self._drag.active and abs(self.slider.get() - level) > 0.005:
            self.slider.set(level)
        if muted != self.muted:
            self.muted = muted
            style_mute_button(self.mute_btn, muted, self._theme["button_hover"], self._theme)
        return True

    def destroy(self):
        self.container.destroy()
