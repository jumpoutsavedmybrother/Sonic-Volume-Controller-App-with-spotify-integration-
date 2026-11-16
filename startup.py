"""Start with Windows, using the per-user "Run" registry key (no administrator rights needed)."""
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Sonic"


def launch_command():
    """The command Windows should run at sign-in: the .exe itself if packaged, otherwise pythonw + this script."""
    target = os.path.abspath(sys.argv[0])
    if getattr(sys, "frozen", False) or target.lower().endswith(".exe"):
        exe = target if target.lower().endswith(".exe") else sys.executable
        return f'"{exe}"'
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")   # pythonw = no console window
    return f'"{pythonw if os.path.exists(pythonw) else python}" "{target}"'


def is_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except Exception:
        return False


def set_enabled(enabled):
    """Returns True if the registry now matches what was asked for."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass   # already off
        return True
    except Exception as e:
        print(f"Could not change start-with-Windows: {e}")
        return False
