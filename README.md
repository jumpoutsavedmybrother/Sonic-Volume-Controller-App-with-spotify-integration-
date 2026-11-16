# Sonic v2

Global volume mixer with now-playing controls.

## Run it
1. Install Python 3.11+ (3.9+ may work), then in this folder:
   `python -m pip install -r requirements.txt`
2. `python sonic.py`
3. Nothing appears at first. Press **Ctrl+Shift+M** (or use the tray icon) to show the overlay.

## Make an .exe
Double-click `build.bat` (needs Python on your PATH). The app ends up in `dist\Sonic.exe`.
`build.bat debug` keeps a console window so you can see errors.

## Files
| File | Job |
|---|---|
| sonic.py | entry point: run this |
| ui.py | main window, theming, polling |
| panels.py | progress bar, master volume + output device |
| widgets.py | reusable widgets (per-app rows, mute buttons, icon) |
| audio.py | all Windows volume code (pycaw) |
| media.py | Windows now-playing (title, cover, position, seek) |
| hotkeys.py | global hotkey + remapping |
| tray.py | system tray icon |
| startup.py | start with Windows |
| memory.py | remembered per-app volumes |
| themes.py | colour themes (incl. glass) |
| winfx.py | glass blur / rounded corners |
| artwork.py | web album-art fallback |
| config.py | settings file (%APPDATA%\Sonic\config.json) |
| app_icon.ico | the icon |
