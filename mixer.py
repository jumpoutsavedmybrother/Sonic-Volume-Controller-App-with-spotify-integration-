import os
import sys
import customtkinter as ctk
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
from pynput import keyboard
import ctypes
import psutil
import urllib.request
import urllib.parse
import json
import io
import re
from PIL import Image, ImageDraw

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class CompactVolumeMixer(ctk.CTk):
    FONT_FAMILY = "Segoe UI"
    THEME_ORDER = ["green", "purple", "red", "grey", "black", "white"]

    THEMES = {
        "green": {
            "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
            "accent": "#1DB954", "hover": "#1AA34A", "text": "white", "subtext": "gray60",
            "button_bg": "#262626", "button_hover": "#3D3D3D"
        },
        "purple": {
            "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
            "accent": "#9333EA", "hover": "#7E22CE", "text": "white", "subtext": "gray60",
            "button_bg": "#262626", "button_hover": "#3D3D3D"
        },
        "red": {
            "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
            "accent": "#E50914", "hover": "#B80710", "text": "white", "subtext": "gray60",
            "button_bg": "#262626", "button_hover": "#3D3D3D"
        },
        "grey": {
            "mode": "dark", "bg_dark": "#121212", "panel_bg": "#1E1E1E", "scroll_bg": "#000000",
            "accent": "#9E9E9E", "hover": "#757575", "text": "white", "subtext": "gray60",
            "button_bg": "#2C2C2C", "button_hover": "#3D3D3D"
        },
        "black": {
            "mode": "dark", "bg_dark": "#050505", "panel_bg": "#0F0F0F", "scroll_bg": "#000000",
            "accent": "#FFFFFF", "hover": "#E5E5E5", "text": "white", "subtext": "gray60",
            "button_bg": "#222222", "button_hover": "#333333"
        },
        "white": {
            "mode": "light", "bg_dark": "#F3F4F6", "panel_bg": "#FFFFFF", "scroll_bg": "#FAFAFA",
            "accent": "#111827", "hover": "#374151", "text": "#111827", "subtext": "#6B7280",
            "button_bg": "#E5E7EB", "button_hover": "#D1D5DB"
        }
    }

    def __init__(self):
        super().__init__()

        self.title("App Volume Mixer")
        self.geometry("620x440")          
        self.attributes("-topmost", True)  
        self.overrideredirect(True)
        
        # Transparent background trick for rounded borders
        self.wm_attributes("-transparentcolor", "#000001")
        self.configure(fg_color="#000001")

        try:
            self.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass

        self.current_theme_idx = 0
        ctk.set_appearance_mode("dark")

        # State Variables
        self.withdraw()
        self.is_visible = False
        self.is_paused = False
        self.current_hotkey_str = "<ctrl>+<shift>+m"
        self.cached_track = None
        self.cached_image = None
        self.current_track_display = None
        self.temp_listener = None

        # Main Rounded Wrapper
        self.main_wrapper = ctk.CTkFrame(self, corner_radius=20)
        self.main_wrapper.pack(fill="both", expand=True, padx=2, pady=2)

        # Window Dragging
        self.main_wrapper.bind("<Button-1>", self.start_move)
        self.main_wrapper.bind("<B1-Motion>", self.do_move)

        self.main_wrapper.grid_columnconfigure(0, weight=1)
        self.main_wrapper.grid_columnconfigure(1, weight=1)
        self.main_wrapper.grid_rowconfigure(0, weight=1)

        # ================= LEFT PANEL =================
        self.left_panel = ctk.CTkFrame(self.main_wrapper, corner_radius=16)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)

        self.spotify_box = ctk.CTkFrame(self.left_panel, corner_radius=12)
        self.spotify_box.pack(fill="x", padx=8, pady=(8, 4))

        self.spot_title_label = ctk.CTkLabel(self.spotify_box, text="Spotify App", font=(self.FONT_FAMILY, 11, "bold"), anchor="w")
        self.spot_title_label.pack(fill="x", padx=10, pady=(6, 0))

        self.spot_controls_frame = ctk.CTkFrame(self.spotify_box, fg_color="transparent")
        self.spot_controls_frame.pack(fill="x", padx=8, pady=(2, 6))

        self.spot_slider = ctk.CTkSlider(self.spot_controls_frame, from_=0.0, to=1.0, height=14)
        self.spot_slider.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.spot_mute_btn = ctk.CTkButton(self.spot_controls_frame, text="🔊 ON", width=55, height=22, corner_radius=8, font=(self.FONT_FAMILY, 9, "bold"))
        self.spot_mute_btn.pack(side="right")

        self.other_label = ctk.CTkLabel(self.left_panel, text="Other Audio Sources", font=(self.FONT_FAMILY, 10, "bold"), anchor="w")
        self.other_label.pack(fill="x", padx=10, pady=(6, 2))

        self.scroll_frame = ctk.CTkScrollableFrame(self.left_panel, corner_radius=12)
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.close_btn = ctk.CTkButton(self.left_panel, text="Close Overlay", command=self.hide_window, height=26, corner_radius=10, font=(self.FONT_FAMILY, 10, "bold"))
        self.close_btn.pack(fill="x", padx=8, pady=(0, 8))

        # ================= RIGHT PANEL =================
        self.right_panel = ctk.CTkFrame(self.main_wrapper, corner_radius=16)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)

        self.right_header = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.right_header.pack(fill="x", padx=10, pady=(8, 0))

        self.spot_icon_label = ctk.CTkLabel(self.right_header, text="")
        self.spot_icon_label.pack(side="right")

        self.cover_label = ctk.CTkLabel(self.right_panel, text="🎵", font=(self.FONT_FAMILY, 80), corner_radius=14, width=210, height=210)
        self.cover_label.pack(padx=10, pady=(4, 6))

        self.song_label = ctk.CTkLabel(self.right_panel, text="Spotify: Inactive", font=(self.FONT_FAMILY, 11, "bold"), anchor="center", justify="center", wraplength=250)
        self.song_label.pack(fill="x", padx=10, pady=(0, 6))

        self.media_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.media_frame.pack(fill="x", padx=8, pady=(0, 6))

        btn_kwargs = {"height": 28, "width": 0, "font": (self.FONT_FAMILY, 11), "corner_radius": 8}
        self.prev_btn = ctk.CTkButton(self.media_frame, text="⏮", command=lambda: self.send_media_key(0xB1), **btn_kwargs)
        self.prev_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.play_btn = ctk.CTkButton(self.media_frame, text="⏯", command=self.toggle_play_pause, **btn_kwargs)
        self.play_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.next_btn = ctk.CTkButton(self.media_frame, text="⏭", command=lambda: self.send_media_key(0xB0), **btn_kwargs)
        self.next_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.spot_media_mute_btn = ctk.CTkButton(self.media_frame, text="🔊", command=self.toggle_spotify_playback_mute, **btn_kwargs)
        self.spot_media_mute_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.theme_btn = ctk.CTkButton(self.right_panel, text="🎨 Theme: Green", command=self.cycle_theme, height=26, corner_radius=8, font=(self.FONT_FAMILY, 10, "bold"))
        self.theme_btn.pack(fill="x", padx=8, pady=(0, 4))

        self.hotkey_btn = ctk.CTkButton(self.right_panel, text="Hotkey: Ctrl+Shift+M (Click to Remap)", command=self.listen_for_new_hotkey, height=24, corner_radius=8, font=(self.FONT_FAMILY, 9))
        self.hotkey_btn.pack(fill="x", padx=8, pady=(0, 8))

        self.init_hotkey_listener()
        self.apply_theme("green")

    def generate_spotify_icon(self, color_hex, size=24):
        img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([0, 0, size * 4, size * 4], fill=color_hex)
        dark_bg = (18, 18, 18, 255) if color_hex != "#111827" else (255, 255, 255, 255)
        draw.arc([int(size * 0.7), int(size * 0.8), int(size * 3.3), int(size * 3.2)], start=200, end=340, fill=dark_bg, width=int(size * 0.35))
        draw.arc([int(size * 0.85), int(size * 1.4), int(size * 3.15), int(size * 3.6)], start=200, end=340, fill=dark_bg, width=int(size * 0.32))
        draw.arc([int(size * 1.0), int(size * 2.0), int(size * 3.0), int(size * 4.0)], start=200, end=340, fill=dark_bg, width=int(size * 0.28))
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=resized, dark_image=resized, size=(size, size))

    def cycle_theme(self):
        self.current_theme_idx = (self.current_theme_idx + 1) % len(self.THEME_ORDER)
        self.apply_theme(self.THEME_ORDER[self.current_theme_idx])

    def apply_theme(self, theme_name):
        t = self.THEMES[theme_name]
        ctk.set_appearance_mode(t["mode"])
        
        self.main_wrapper.configure(fg_color=t["bg_dark"])
        self.left_panel.configure(fg_color=t["panel_bg"])
        self.right_panel.configure(fg_color=t["panel_bg"])
        self.spotify_box.configure(fg_color=t["bg_dark"])
        self.scroll_frame.configure(fg_color=t["scroll_bg"])

        self.spot_title_label.configure(text_color=t["accent"])
        self.other_label.configure(text_color=t["subtext"])
        self.song_label.configure(text_color=t["text"])
        self.spot_slider.configure(button_color=t["accent"], button_hover_color=t["hover"], progress_color=t["accent"])

        for btn in [self.close_btn, self.prev_btn, self.play_btn, self.next_btn, self.spot_media_mute_btn, self.theme_btn, self.hotkey_btn]:
            btn.configure(fg_color=t["button_bg"], hover_color=t["button_hover"], text_color=t["text"])

        self.theme_btn.configure(text=f"🎨 Theme: {theme_name.capitalize()}")
        self.spot_icon_label.configure(image=self.generate_spotify_icon(t["accent"]))
        self.populate_sliders()

    def start_move(self, event):
        if "slider" in str(event.widget).lower() or "button" in str(event.widget).lower():
            self._drag_active = False
            return
        self._drag_active = True
        self._drag_x = event.x
        self._drag_y = event.y

    def do_move(self, event):
        if getattr(self, '_drag_active', True):
            x = self.winfo_x() - self._drag_x + event.x
            y = self.winfo_y() - self._drag_y + event.y
            self.geometry(f"+{x}+{y}")

    def init_hotkey_listener(self):
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            try: self.hotkey_listener.stop()
            except Exception: pass
        try:
            self.hotkey_listener = keyboard.GlobalHotKeys({self.current_hotkey_str: lambda: self.after(0, self.toggle_visibility)})
            self.hotkey_listener.start()
        except Exception: pass

    def listen_for_new_hotkey(self):
        self.hotkey_btn.configure(text="Press in sequence (e.g. Ctrl then Shift then M)...")
        recorded_keys = []
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            try: self.hotkey_listener.stop()
            except Exception: pass

        def on_press(key):
            try:
                key_tag = None
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r): key_tag = '<ctrl>'
                elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r): key_tag = '<shift>'
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r): key_tag = '<alt>'
                else:
                    if hasattr(key, 'char') and key.char: key_tag = key.char.lower()
                    elif hasattr(key, 'name') and key.name: key_tag = key.name.lower()

                if key_tag and key_tag not in recorded_keys:
                    recorded_keys.append(key_tag)
                    if key_tag not in ['<ctrl>', '<shift>', '<alt>']:
                        new_hotkey = "+".join(recorded_keys)
                        self.current_hotkey_str = new_hotkey
                        display_str = new_hotkey.replace('<ctrl>', 'Ctrl').replace('<shift>', 'Shift').replace('<alt>', 'Alt').upper()
                        self.after(0, lambda: self.finish_hotkey_record(display_str))
                        return False
            except Exception: pass

        self.temp_listener = keyboard.Listener(on_press=on_press)
        self.temp_listener.start()

    def finish_hotkey_record(self, display_str):
        self.hotkey_btn.configure(text=f"Hotkey: {display_str} (Click to Remap)")
        self.init_hotkey_listener()

    def fetch_album_art(self, track_str):
        if track_str == self.cached_track and self.cached_image:
            return self.cached_image
        clean_query = re.sub(r'[\(\[\{].*?[\)\]\}]', '', track_str).strip() or track_str
        encoded_q = urllib.parse.quote(clean_query)
        for api_url in [f"https://api.deezer.com/search?q={encoded_q}&limit=3", f"https://itunes.apple.com/search?term={encoded_q}&entity=song&limit=3"]:
            try:
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                    img_url = None
                    if "deezer" in api_url and data.get('data'):
                        img_url = data['data'][0]['album'].get('cover_xl') or data['data'][0]['album'].get('cover_big')
                    elif "itunes" in api_url and data.get('resultCount', 0) > 0:
                        img_url = data['results'][0]['artworkUrl100'].replace("100x100bb", "600x600bb")

                    if img_url:
                        img_req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(img_req, timeout=2.0) as img_res:
                            pil_img = Image.open(io.BytesIO(img_res.read()))
                            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(210, 210))
                            self.cached_track = track_str
                            self.cached_image = ctk_img
                            return ctk_img
            except Exception: pass
        return None

    def send_media_key(self, key_code):
        ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key_code, 0, 2, 0)
        self.after(300, self.update_track_info)

    def toggle_play_pause(self):
        self.send_media_key(0xB3)
        self.is_paused = not self.is_paused
        t = self.THEMES[self.THEME_ORDER[self.current_theme_idx]]
        if self.is_paused:
            self.play_btn.configure(fg_color="#D32F2F", hover_color="#9A0007", text_color="white")
        else:
            self.play_btn.configure(fg_color=t["button_bg"], hover_color=t["button_hover"], text_color=t["text"])

    def toggle_spotify_playback_mute(self):
        sessions = AudioUtilities.GetAllSessions()
        target_apps = ["spotify.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]
        target_session = None
        for session in sessions:
            if session.Process:
                p_name = session.Process.name().lower()
                if p_name == "spotify.exe":
                    target_session = session; break
                elif p_name in target_apps and not target_session and self.current_track_display:
                    target_session = session

        if target_session:
            vol_interface = target_session._ctl.QueryInterface(ISimpleAudioVolume)
            vol_interface.SetMute(not vol_interface.GetMute(), None)
            self.populate_sliders()

    def get_spotify_track(self):
        user32 = ctypes.windll.user32
        found_title = None
        def enum_windows_callback(hwnd, extra):
            nonlocal found_title
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value.strip()
                    ignored = ["spotify", "spotify free", "spotify premium", "drag", "gdi+ window", "spotifywidgetprovider"]
                    if title.lower() not in ignored:
                        pid = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        try:
                            proc_name = psutil.Process(pid.value).name().lower()
                            if proc_name in ["spotify.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
                                if "spotify" in title.lower() or proc_name == "spotify.exe":
                                    clean = title.replace("Spotify - ", "").strip()
                                    for suffix in [" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox"]:
                                        clean = clean.split(suffix)[0]
                                    clean = clean.replace("•", "-").strip()
                                    if clean and clean.lower() not in ignored:
                                        found_title = clean
                        except Exception: pass
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return found_title

    def toggle_mute(self, vol_interface):
        vol_interface.SetMute(not vol_interface.GetMute(), None)
        self.populate_sliders()

    def update_track_info(self):
        track = self.get_spotify_track()
        if track != self.current_track_display:
            self.current_track_display = track
            if track:
                self.song_label.configure(text=track)
                art_image = self.fetch_album_art(track)
                if art_image: self.cover_label.configure(image=art_image, text="")
                else: self.cover_label.configure(image="", text="🎵")
            else:
                self.song_label.configure(text="Spotify: Inactive")
                self.cover_label.configure(image="", text="🎵")

    def start_polling(self):
        if self.is_visible:
            self.update_track_info()
            self.after(1000, self.start_polling)

    def populate_sliders(self):
        self.update_track_info()
        t = self.THEMES[self.THEME_ORDER[self.current_theme_idx]]

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        sessions = AudioUtilities.GetAllSessions()
        spotify_session = None
        other_sessions = []
        excluded_procs = ["spotifywidgetprovider.exe"]

        for session in sessions:
            if session.Process:
                p_name = session.Process.name().lower()
                if p_name in excluded_procs: continue
                if p_name == "spotify.exe": spotify_session = session
                elif p_name in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
                    if not spotify_session and self.current_track_display: spotify_session = session

        for session in sessions:
            if session.Process and session != spotify_session and session.Process.name().lower() not in excluded_procs:
                other_sessions.append(session)

        if spotify_session:
            v_interface = spotify_session._ctl.QueryInterface(ISimpleAudioVolume)
            self.spot_slider.configure(command=lambda val, i=v_interface: i.SetMasterVolume(float(val), None))
            self.spot_slider.set(v_interface.GetMasterVolume())
            
            is_muted = v_interface.GetMute()
            btn_text = "🔇 MUTED" if is_muted else "🔊 ON"
            btn_fg = "#D32F2F" if is_muted else t["button_bg"]
            btn_txt_col = "white" if is_muted else t["text"]

            self.spot_mute_btn.configure(text=btn_text, fg_color=btn_fg, hover_color="#9A0007" if is_muted else t["button_hover"], text_color=btn_txt_col, command=lambda i=v_interface: self.toggle_mute(i))
            self.spot_media_mute_btn.configure(text="🔇" if is_muted else "🔊", fg_color=btn_fg, hover_color="#9A0007" if is_muted else t["button_hover"], text_color=btn_txt_col, command=lambda i=v_interface: self.toggle_mute(i))
            
            app_title = "Spotify App" if spotify_session.Process.name().lower() == "spotify.exe" else f"Spotify Web ({spotify_session.Process.name().replace('.exe','').capitalize()})"
            self.spot_title_label.configure(text=app_title)
        else:
            self.spot_title_label.configure(text="Spotify / Web Player (Inactive)")

        for session in other_sessions:
            vol_interface = session._ctl.QueryInterface(ISimpleAudioVolume)
            app_name = session.Process.name().replace('.exe', '').capitalize()
            current_vol = vol_interface.GetMasterVolume()
            is_muted = vol_interface.GetMute()

            header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            header_frame.pack(fill="x", pady=(2, 0), padx=2)

            label = ctk.CTkLabel(header_frame, text=app_name, font=(self.FONT_FAMILY, 10, "bold"), text_color=t["text"])
            label.pack(side="left")

            mute_btn = ctk.CTkButton(header_frame, text="🔇 MUTED" if is_muted else "🔊 ON", width=55, height=18, corner_radius=6, font=(self.FONT_FAMILY, 8, "bold"), fg_color="#D32F2F" if is_muted else t["button_hover"], text_color="white" if is_muted else t["text"], command=lambda i=vol_interface: self.toggle_mute(i))
            mute_btn.pack(side="right")

            slider = ctk.CTkSlider(self.scroll_frame, from_=0.0, to=1.0, height=12, button_color=t["accent"], button_hover_color=t["hover"], progress_color=t["accent"], command=lambda val, i=vol_interface: i.SetMasterVolume(float(val), None))
            slider.set(current_vol)
            slider.pack(fill="x", pady=(0, 4), padx=2)

    def toggle_visibility(self):
        if self.is_visible: self.hide_window()
        else: self.show_window()

    def show_window(self):
        self.populate_sliders()
        if not hasattr(self, '_has_opened'):
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (620 // 2)
            y = (self.winfo_screenheight() // 2) - (440 // 2)
            self.geometry(f"+{x}+{y}")
            self._has_opened = True
        
        self.deiconify()
        self.is_visible = True
        self.start_polling()

    def hide_window(self):
        self.withdraw()
        self.is_visible = False

if __name__ == "__main__":
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    
    app = CompactVolumeMixer()
    app.mainloop()
