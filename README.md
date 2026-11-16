# Sonic Volume Mixer (v2) 
A sleek, modular Windows volume mixer built with Python. Sonic provides a modern overlay for controlling your master volume, per-app audio sources (like Spotify, Chrome, etc.), and media playback, complete with live album artwork and global hotkeys.

## **Features**
Per-App Volume Control: Individually adjust or mute specific applications on the fly.

Media Controls & Artwork: Play, pause, skip tracks, and view current album art via native Windows Media integration.

Modern UI: A clean, CustomTkinter-based dark theme interface.

Global Hotkeys: Quickly summon or dismiss the overlay from anywhere (Default: Ctrl+Shift+K).

Due to standard network security policies and Windows Defender often flagging unverified, custom-built executable files, this project is distributed as source code. Compiling the application directly on your own machine takes only a minute and ensures it runs perfectly within your specific Windows environment without triggering security blocks or missing background dependencies.

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
## **Prerequisites**
-- Windows 10 or 11

Python 3.12 (Highly recommended. Brand-new releases like Python 3.14 may experience compatibility issues with the underlying winrt C++ projections).

## **Installation & Setup**
1. Download the Project
Click the green Code button at the top of this repository and select Download ZIP. Extract the folder to a permanent location on your PC.

2. Install Dependencies
Open a terminal (Command Prompt or PowerShell) inside the extracted folder and run the following command to install the required Python libraries:

DOS
pip install -r requirements.txt
3. Build the Executable
Simply double-click the build.bat file included in the folder. This script will automatically clean up any old build cache, package the application using PyInstaller, and generate a fresh, working executable tailored specifically to your machine.

4. Run Sonic
Once the black build window finishes and closes, open the newly generated dist folder, and then open the sonic folder inside it.

Double-click sonic.exe to launch the app. 
It wont show up in your taskbar until you press the hotkey to activate it, the base hotkey is Crtl+Shift+K 

## **Important**: Do not move sonic.exe out of this folder, as it requires the accompanying _internal directory to function. Instead, right-click sonic.exe and select Show more options > Send to > Desktop (create shortcut), or pin it to your taskbar for easy access.
