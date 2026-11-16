"""The main overlay window: layout, theming and the polling loop. Everything else lives in other modules."""
import io
import time
import ctypes
import threading

import customtkinter as ctk
from PIL import Image

import audio
import startup
from artwork import WebArtLookup
from config import DEFAULT_HOTKEY, load_config, save_config, resource_path
from hotkeys import HotkeyManager, hotkey_is_valid
from media import MediaWatcher
from memory import VolumeMemory
from panels import MasterBox, ProgressBar
from themes import THEMES, THEME_ORDER, KEY_COLOR, GLASS_USE_NATIVE_BLUR
from tray import TrayIcon
from widgets import DragFlag, SessionRow, make_spotify_icon, style_mute_button, track_drag
from winfx import GlassEffect

FONT_FAMILY = "Segoe UI"
WINDOW_W, WINDOW_H = 620, 520

# Pressing on any of these must not move the window (dials, buttons, scrollbars, drop-downs)
_INTERACTIVE = tuple(c for c in (getattr(ctk, n, None) for n in ("CTkSlider", "CTkButton", "CTkScrollbar", "CTkOptionMenu")) if c)


class CompactVolumeMixer(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("App Volume Mixer")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.attributes("-topmost", True)
        self.overrideredirect(True)

        # Transparent background for rounded borders
        self.wm_attributes("-transparentcolor", KEY_COLOR)
        self.configure(fg_color=KEY_COLOR)

        try:
            self.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass

        # ---- load saved settings (the whole dict is kept, so settings we don't know about survive a save) ----
        self.settings = load_config()
        saved_theme = self.settings.get("theme")
        self.current_theme_idx = THEME_ORDER.index(saved_theme) if saved_theme in THEME_ORDER else 0
        saved_hotkey = self.settings.get("hotkey")
        hotkey = saved_hotkey if isinstance(saved_hotkey, str) and hotkey_is_valid(saved_hotkey) else DEFAULT_HOTKEY
        self.memory = VolumeMemory(self.settings.get("app_volumes"))
        ctk.set_appearance_mode("dark")

        #variables
        #self.withdraw()
        self.is_visible = False
        self.is_paused = False
        self.current_track_display = None
        self.track_source = None          # process name of the app that owns the media session
        self.media_present = False
        self.media_app_name = ""
        self.shown_art_id = None          # which Windows thumbnail is on screen
        self._fallback_for = None         # track we've already tried the web art fallback for
        self._error_shown = None
        self.rows = {}                    # session key -> SessionRow for the "other apps" list
        self.spot_vol = None              # ISimpleAudioVolume for the top slider
        self.spot_proc = ""               # process behind the top slider (for the volume memory)
        self.spot_muted = False
        self._restored = set()            # session keys whose remembered volume we've already applied
        self.drag = DragFlag()            # true while the user holds a slider
        self.glass = GlassEffect(self)
        self.glass_mode = None            # None | "blur" | "solid"
        self.glass_blur_ok = None if GLASS_USE_NATIVE_BLUR else False   # None = not tried yet
        self.slider_track_default = ctk.ThemeManager.theme.get("CTkSlider", {}).get("fg_color", ("#939BA2", "#4A4D50"))
        self._poll_job = None
        self._progress_job = None
        self._save_job = None
        self._ignore_state_until = 0.0    # after a play/pause click, trust our own toggle briefly

        self.web_art = WebArtLookup()
        self.watcher = MediaWatcher()
        self.watcher.start()
        self.hotkeys = HotkeyManager(self, hotkey, on_trigger=self.toggle_visibility,
                                     on_status=self._set_hotkey_text, on_changed=lambda h: self.save_settings())
        self.tray = TrayIcon(self, resource_path("app_icon.ico"), on_toggle=self.toggle_visibility, on_quit=self.quit_app,
                             autostart_get=startup.is_enabled, autostart_set=startup.set_enabled)

        #rounded Wrapper
        self.main_wrapper = ctk.CTkFrame(self, corner_radius=20)
        self.main_wrapper.pack(fill="both", expand=True, padx=2, pady=2)

        self.main_wrapper.grid_columnconfigure(0, weight=1)
        self.main_wrapper.grid_columnconfigure(1, weight=1)
        self.main_wrapper.grid_rowconfigure(0, weight=0)   # drag handle (glass theme only)
        self.main_wrapper.grid_rowconfigure(1, weight=1)

        # In the glass theme everything else is see-through, and see-through pixels are click-through,
        # so the window needs a solid area to grab. Shown only for that theme (see apply_theme).
        self.grip = ctk.CTkFrame(self.main_wrapper, height=14, corner_radius=7)

        # ================= LEFT PANEL =================
        self.left_panel = ctk.CTkFrame(self.main_wrapper, corner_radius=16)
        self.left_panel.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=8)

        self.master_box = MasterBox(self.left_panel, FONT_FAMILY, self.drag)
        self.master_box.frame.pack(fill="x", padx=8, pady=(8, 4))

        self.spotify_box = ctk.CTkFrame(self.left_panel, corner_radius=12)
        self.spotify_box.pack(fill="x", padx=8, pady=(0, 4))

        self.spot_title_label = ctk.CTkLabel(self.spotify_box, text="Spotify App", font=(FONT_FAMILY, 11, "bold"), anchor="w")
        self.spot_title_label.pack(fill="x", padx=10, pady=(6, 0))

        self.spot_controls_frame = ctk.CTkFrame(self.spotify_box, fg_color="transparent")
        self.spot_controls_frame.pack(fill="x", padx=8, pady=(2, 6))

        self.spot_slider = ctk.CTkSlider(self.spot_controls_frame, from_=0.0, to=1.0, height=14, command=self.set_spotify_volume)
        self.spot_slider.pack(side="left", fill="x", expand=True, padx=(0, 6))
        track_drag(self.spot_slider, self.drag)

        self.spot_mute_btn = ctk.CTkButton(self.spot_controls_frame, text="🔊 ON", width=55, height=22, corner_radius=8, font=(FONT_FAMILY, 9, "bold"), command=self.toggle_spotify_mute)
        self.spot_mute_btn.pack(side="right")

        self.other_label = ctk.CTkLabel(self.left_panel, text="Other Audio Sources", font=(FONT_FAMILY, 10, "bold"), anchor="w")
        self.other_label.pack(fill="x", padx=10, pady=(6, 2))

        self.scroll_frame = ctk.CTkScrollableFrame(self.left_panel, corner_radius=12)
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.bottom_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.bottom_row.pack(fill="x", padx=8, pady=(0, 8))

        self.close_btn = ctk.CTkButton(self.bottom_row, text="Close Overlay", command=self.hide_window, height=26, corner_radius=10, font=(FONT_FAMILY, 10, "bold"))
        self.close_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.quit_btn = ctk.CTkButton(self.bottom_row, text="Quit", width=56, command=self.quit_app, height=26, corner_radius=10, font=(FONT_FAMILY, 10, "bold"))
        self.quit_btn.pack(side="right")

        # ================= RIGHT PANEL =================
        self.right_panel = ctk.CTkFrame(self.main_wrapper, corner_radius=16)
        self.right_panel.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=8)

        self.right_header = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.right_header.pack(fill="x", padx=10, pady=(8, 0))

        self.spot_icon_label = ctk.CTkLabel(self.right_header, text="")
        self.spot_icon_label.pack(side="right")

        self.cover_label = ctk.CTkLabel(self.right_panel, text="🎵", font=(FONT_FAMILY, 80), corner_radius=14, width=210, height=210)
        self.cover_label.pack(padx=10, pady=(4, 6))

        self.song_label = ctk.CTkLabel(self.right_panel, text="Spotify: Inactive", font=(FONT_FAMILY, 11, "bold"), anchor="center", justify="center", wraplength=250)
        self.song_label.pack(fill="x", padx=10, pady=(0, 4))

        self.progress = ProgressBar(self.right_panel, FONT_FAMILY, self.drag, on_seek=self.seek_to)
        self.progress.frame.pack(fill="x", padx=12, pady=(0, 4))

        self.media_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.media_frame.pack(fill="x", padx=8, pady=(0, 6))

        btn_kwargs = {"height": 28, "width": 0, "font": (FONT_FAMILY, 11), "corner_radius": 8}
        self.prev_btn = ctk.CTkButton(self.media_frame, text="⏮", command=lambda: self.skip(self.watcher.previous, 0xB1), **btn_kwargs)
        self.prev_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.play_btn = ctk.CTkButton(self.media_frame, text="⏯", command=self.toggle_play_pause, **btn_kwargs)
        self.play_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.next_btn = ctk.CTkButton(self.media_frame, text="⏭", command=lambda: self.skip(self.watcher.next, 0xB0), **btn_kwargs)
        self.next_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.spot_media_mute_btn = ctk.CTkButton(self.media_frame, text="🔊", command=self.toggle_spotify_mute, **btn_kwargs)
        self.spot_media_mute_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.theme_btn = ctk.CTkButton(self.right_panel, text="🎨 Theme: Green", command=self.cycle_theme, height=26, corner_radius=8, font=(FONT_FAMILY, 10, "bold"))
        self.theme_btn.pack(fill="x", padx=8, pady=(0, 4))

        self.hotkey_btn = ctk.CTkButton(self.right_panel, text=self.hotkeys.label(), command=self.hotkeys.begin_recording, height=24, corner_radius=8, font=(FONT_FAMILY, 9))
        self.hotkey_btn.pack(fill="x", padx=8, pady=(0, 8))

        self._enable_window_drag()

        self.hotkeys.start()
        self.apply_theme(THEME_ORDER[self.current_theme_idx])
        self.tray.start()

    # ================= settings / theme =================
    @property
    def current_theme(self):
        return THEMES[THEME_ORDER[self.current_theme_idx]]

    @property
    def is_glass(self):
        return bool(self.current_theme.get("glass"))

    def save_settings(self):
        self.settings.update({"theme": THEME_ORDER[self.current_theme_idx], "hotkey": self.hotkeys.hotkey,
                              "app_volumes": self.memory.to_dict()})
        save_config(self.settings)

    def schedule_save(self):
        """Save shortly after the last change, so dragging a slider doesn't write the file on every pixel."""
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(600, self._flush_save)

    def _flush_save(self):
        self._save_job = None
        self.save_settings()

    def _set_hotkey_text(self, text):
        self.hotkey_btn.configure(text=text)

    def cycle_theme(self):
        self.current_theme_idx = (self.current_theme_idx + 1) % len(THEME_ORDER)
        self.apply_theme(THEME_ORDER[self.current_theme_idx])
        self.save_settings()

    def apply_theme(self, theme_name):
        t = THEMES[theme_name]
        glass = bool(t.get("glass"))
        blur = glass and self.glass_blur_ok is not False
        self.glass_mode = ("blur" if blur else "solid") if glass else None
        pal = dict(t)
        if glass and not blur:
            pal.update(t["fallback"])
        rim = t.get("rim")
        bw = 1 if glass else 0
        ctk.set_appearance_mode(t["mode"])

        # Slight whole-window translucency stands in for glass when real blur isn't available
        try: self.attributes("-alpha", 0.94 if self.glass_mode == "solid" else 1.0)
        except Exception: pass

        self.main_wrapper.configure(fg_color=pal["bg_dark"], border_width=1 if self.glass_mode == "solid" else 0,
                                    border_color=rim or pal["bg_dark"])
        for frame, color in ((self.left_panel, pal["panel_bg"]), (self.right_panel, pal["panel_bg"]),
                             (self.master_box.frame, pal["bg_dark"]), (self.spotify_box, pal["bg_dark"]),
                             (self.scroll_frame, pal["scroll_bg"])):
            try:
                frame.configure(fg_color=color, border_width=bw, border_color=rim or color)
            except Exception:
                frame.configure(fg_color=color)   # some frame types don't accept border options

        # CTk only repaints a frame's direct children; push the new background to widgets nested one level deeper
        for w in (self.spot_slider, self.spot_mute_btn, *self.master_box.widgets_for_background()):
            w.configure(bg_color=pal["bg_dark"])
        for w in (self.spot_icon_label, self.prev_btn, self.play_btn, self.next_btn, self.spot_media_mute_btn,
                  self.close_btn, self.quit_btn, *self.progress.widgets_for_background()):
            w.configure(bg_color=pal["panel_bg"])

        self.spot_title_label.configure(text_color=t["accent"])
        self.other_label.configure(text_color=t["subtext"])
        self.song_label.configure(text_color=t["text"])
        self.spot_slider.configure(button_color=t["accent"], button_hover_color=t["hover"], progress_color=t["accent"],
                                   fg_color=t.get("track", self.slider_track_default))
        self.master_box.style(t, self.slider_track_default)
        self.progress.style(t, self.slider_track_default)

        for btn in [self.close_btn, self.quit_btn, self.prev_btn, self.play_btn, self.next_btn, self.spot_media_mute_btn, self.theme_btn, self.hotkey_btn]:
            btn.configure(fg_color=t["button_bg"], hover_color=t["button_hover"], text_color=t["text"],
                          border_width=bw, border_color=rim or t["button_bg"])

        if glass:
            self.grip.configure(fg_color=t["button_bg"], border_width=1, border_color=rim)
            self.grip.grid(row=0, column=0, columnspan=2, sticky="ew", padx=90, pady=(6, 0))
        else:
            self.grip.grid_remove()

        self.theme_btn.configure(text=f"🎨 Theme: {theme_name.capitalize()}")
        self.spot_icon_label.configure(image=make_spotify_icon(t["accent"]))

        # Re-apply the red "toggled on" states on top of the new theme
        self.style_spotify_mute()
        self.refresh_play_button()

        # Rebuild the "other apps" rows so their backgrounds match the new theme
        for key in list(self.rows):
            self.remove_row(key)
        if self.is_visible:
            self.refresh_sessions()
            self.update_glass_effect()

    # ================= glass effect =================
    def _tint(self):
        t = self.current_theme
        return t.get("tint", (0, 0, 0)), t.get("tint_alpha", 0x70)

    def update_glass_effect(self):
        """Apply/clear the blur for the current theme. If Windows refuses it, restyle with solid colours
        (the see-through colours would otherwise leave an invisible window)."""
        if self.is_glass:
            if self.glass_blur_ok is False:
                return
            self.update_idletasks()
            if self.glass.apply(*self._tint()):
                self.glass_blur_ok = True
            else:
                self.glass_blur_ok = False
                self.apply_theme(THEME_ORDER[self.current_theme_idx])
        elif self.glass.used:
            self.glass.clear()

    # ================= window dragging =================
    def _enable_window_drag(self):
        """Drag the window from anywhere except sliders, buttons and scrollbars.
        bind_all covers every widget, including rows that are created later."""
        self.bind_all("<Button-1>", self.start_move, add="+")
        self.bind_all("<B1-Motion>", self.do_move, add="+")
        self.bind_all("<ButtonRelease-1>", self.end_move, add="+")

    @staticmethod
    def _is_interactive(widget):
        """True if the widget is (or sits inside) a slider, button, scrollbar or drop-down."""
        while widget is not None:
            if isinstance(widget, _INTERACTIVE):
                return True
            widget = getattr(widget, "master", None)
        return False

    def start_move(self, event):
        self._drag_active = not self._is_interactive(event.widget)
        if self._drag_active:
            # remember where inside the window we grabbed it (screen coordinates, so it can't drift)
            self._drag_off = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def do_move(self, event):
        if getattr(self, "_drag_active", False):
            self.glass.begin_drag(*self._tint())
            self.geometry(f"+{event.x_root - self._drag_off[0]}+{event.y_root - self._drag_off[1]}")

    def end_move(self, event=None):
        self._drag_active = False
        self.glass.end_drag(*self._tint())

    # ================= album art =================
    def show_thumbnail(self, data):
        """Windows hands us the cover as encoded image bytes; decoding ~600px is fast enough for the UI thread."""
        try:
            pil_img = Image.open(io.BytesIO(data))
            pil_img.load()
            img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(210, 210))
            self.cover_label.configure(image=img, text="")
        except Exception as e:
            print(f"Could not show thumbnail: {e}")

    def _load_art(self, track):
        try:
            pil_img = self.web_art.fetch(track)
        except Exception:
            pil_img = None
        try:
            self.after(0, lambda: self._show_art(track, pil_img))
        except Exception:
            pass   # window was closed while we were downloading

    def _show_art(self, track, pil_img):
        if track != self.current_track_display or self.shown_art_id is not None:
            return   # song changed, or a real Windows thumbnail arrived in the meantime
        if pil_img is not None:
            img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(210, 210))
            self.cover_label.configure(image=img, text="")

    # ================= media controls =================
    def send_media_key(self, key_code):
        """Fallback when the media session isn't available: press the system media key."""
        ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key_code, 0, 2, 0)
        self.after(300, self.update_track_info)

    def skip(self, command, fallback_key):
        if command():
            self.after(600, self.update_track_info)
        else:
            self.send_media_key(fallback_key)

    def seek_to(self, seconds):
        self.watcher.seek(seconds)

    def toggle_play_pause(self):
        if not self.watcher.toggle_play_pause():
            self.send_media_key(0xB3)
        self.is_paused = not self.is_paused
        # The session takes a moment to report the change; don't let a stale read undo this toggle
        self._ignore_state_until = time.monotonic() + 1.0
        self.refresh_play_button()

    def refresh_play_button(self):
        t = self.current_theme
        if self.is_paused:
            self.play_btn.configure(fg_color="#D32F2F", hover_color="#9A0007", text_color="white")
        else:
            self.play_btn.configure(fg_color=t["button_bg"], hover_color=t["button_hover"], text_color=t["text"])

    def update_track_info(self):
        state = self.watcher.get_state()

        if state.error:
            if self._error_shown != state.error:
                self._error_shown = state.error
                self.song_label.configure(text=state.error)
            return

        self.media_present = state.present
        self.track_source = state.process
        self.media_app_name = state.app_name

        if time.monotonic() >= self._ignore_state_until:
            self.is_paused = state.status == "paused"
            self.refresh_play_button()

        display = None
        if state.present:
            display = (f"{state.title} - {state.artist}" if state.artist else state.title) or None

        if display != self.current_track_display:
            self.current_track_display = display
            self.shown_art_id = None
            self._fallback_for = None
            self.cover_label.configure(image="", text="🎵")
            self.song_label.configure(text=display or "Spotify: Inactive")
        if display is None:
            return

        if state.thumb and state.art_id != self.shown_art_id:
            self.shown_art_id = state.art_id
            self.show_thumbnail(state.thumb)
        elif not state.thumb and not state.art_pending and self._fallback_for != display:
            self._fallback_for = display
            threading.Thread(target=self._load_art, args=(display,), daemon=True).start()

    # ================= remembered volumes =================
    def _restore(self, vol, proc):
        """Apply the volume/mute the user last chose for this app (if any)."""
        saved = self.memory.get(proc)
        if saved:
            level, muted = saved
            audio.set_volume(vol, level)
            audio.set_mute(vol, muted)

    def _remember_current(self, vol, proc):
        """After a mute click: store whatever the app's mute state now is."""
        try:
            _, muted = audio.read_volume(vol)
        except Exception:
            return
        self.memory.remember(proc, muted=muted)
        self.schedule_save()

    def row_volume_moved(self, row, value):
        self.memory.remember(row.proc, level=value)
        self.schedule_save()

    def row_mute_clicked(self, row):
        audio.toggle_mute(row.vol)
        self._remember_current(row.vol, row.proc)
        self.refresh_sessions()

    # ================= volume: top box (the app that owns the media session) =================
    def find_media_session(self, sessions):
        """The audio session of whichever app owns the media session shown on the right.
        With no media at all, default to Spotify. If we can't map the app to a process, show nothing."""
        wanted = self.track_source if self.media_present else "spotify.exe"
        return audio.find_session(sessions, wanted)

    def style_spotify_mute(self):
        t = self.current_theme
        style_mute_button(self.spot_mute_btn, self.spot_muted, t["button_bg"], t)
        if self.spot_muted:
            self.spot_media_mute_btn.configure(text="🔇", fg_color="#D32F2F", hover_color="#9A0007", text_color="white")
        else:
            self.spot_media_mute_btn.configure(text="🔊", fg_color=t["button_bg"], hover_color=t["button_hover"], text_color=t["text"])

    def set_spotify_volume(self, value):
        audio.set_volume(self.spot_vol, value)
        if self.spot_vol is not None:
            self.memory.remember(self.spot_proc, level=value)
            self.schedule_save()

    def toggle_spotify_mute(self):
        if self.spot_vol is not None:
            audio.toggle_mute(self.spot_vol)
            self._remember_current(self.spot_vol, self.spot_proc)
            self.refresh_sessions()

    def update_spotify_box(self, session):
        if session is None:
            self.spot_vol = None
            if self.media_present and self.media_app_name:
                self.spot_title_label.configure(text=f"{self.media_app_name} (no volume control)")
            else:
                self.spot_title_label.configure(text="Spotify / Media (Inactive)")
            return
        proc = audio.process_name(session)
        key = audio.session_key(session)
        try:
            vol = audio.volume_interface(session)
            if key not in self._restored:            # first time we see this session: apply the remembered volume
                self._restored.add(key)
                self._restore(vol, proc)
            level, muted = audio.read_volume(vol)
        except Exception:
            self.spot_vol = None
            return
        self.spot_vol = vol
        self.spot_proc = proc
        if not self.drag.active and abs(self.spot_slider.get() - level) > 0.005:
            self.spot_slider.set(level)
        if muted != self.spot_muted:
            self.spot_muted = muted
            self.style_spotify_mute()

        name = audio.pretty_name(proc)
        if proc == "spotify.exe":
            title = "Spotify App"
        elif proc in audio.BROWSERS:
            # Windows controls volume per process, not per tab, so this affects every tab in that browser
            title = f"{name} (all tabs)"
        else:
            title = name
        self.spot_title_label.configure(text=title)

    # ================= volume: "other apps" list =================
    def remove_row(self, key):
        row = self.rows.pop(key, None)
        if row:
            row.destroy()

    def refresh_sessions(self):
        """Update existing widgets in place; only add/remove rows when apps start or stop (no rebuild, no flicker)."""
        sessions = audio.list_sessions()
        if sessions is None:
            return

        media_session = self.find_media_session(sessions)
        media_key = audio.session_key(media_session) if media_session else None
        self.update_spotify_box(media_session)

        wanted = audio.other_sessions(sessions, exclude_key=media_key)
        for key in [k for k in self.rows if k not in wanted]:
            self.remove_row(key)
        for key, session in wanted.items():
            row = self.rows.get(key)
            if row is None:
                proc = audio.process_name(session)
                row = SessionRow(self.scroll_frame, proc, audio.pretty_name(proc), FONT_FAMILY, self.drag,
                                 self.row_mute_clicked, self.row_volume_moved,
                                 self.current_theme, self.slider_track_default)
                self.rows[key] = row
                if row.update(session) and key not in self._restored:   # first sight: apply the remembered volume
                    self._restored.add(key)
                    self._restore(row.vol, proc)
            if not row.update(session):
                self.remove_row(key)   # session died between listing and reading

    # ================= show / hide / polling =================
    def _cancel_jobs(self):
        for name in ("_poll_job", "_progress_job"):
            job = getattr(self, name)
            if job is not None:
                self.after_cancel(job)
                setattr(self, name, None)

    def start_polling(self):
        self._cancel_jobs()
        self.master_box.refresh(force_devices=True)
        self._poll_tick()
        self._progress_tick()

    def _poll_tick(self):
        if not self.is_visible:
            self._poll_job = None
            return
        self.update_track_info()
        self.refresh_sessions()
        self.master_box.refresh()
        self._poll_job = self.after(1000, self._poll_tick)

    def _progress_tick(self):
        if not self.is_visible:
            self._progress_job = None
            return
        self.progress.update(self.watcher.get_state())
        self._progress_job = self.after(500, self._progress_tick)

    def toggle_visibility(self):
        if self.is_visible: self.hide_window()
        else: self.show_window()

    def show_window(self):
        if not hasattr(self, '_has_opened'):
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (WINDOW_W // 2)
            y = (self.winfo_screenheight() // 2) - (WINDOW_H // 2)
            self.geometry(f"+{x}+{y}")
            self._has_opened = True

        self.deiconify()
        self.is_visible = True
        self.update_glass_effect()
        self.start_polling()

    def quit_app(self):
        """Save anything pending, stop the background threads and close the program."""
        self._cancel_jobs()
        if self._save_job is not None:
            self.after_cancel(self._save_job)
            self._save_job = None
        self.save_settings()
        self.tray.stop()
        self.hotkeys.stop()
        self.watcher.stop()
        if self.glass.used:
            self.glass.clear()
        self.destroy()

    def hide_window(self):
        self.withdraw()
        self.is_visible = False
        self._cancel_jobs()

