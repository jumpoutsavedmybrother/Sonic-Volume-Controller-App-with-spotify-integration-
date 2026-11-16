"""Sonic - global volume mixer with Spotify/now-playing controls. Run this file."""
import ctypes

from ui import CompactVolumeMixer


def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass

    app = CompactVolumeMixer()
    app.mainloop()


if __name__ == "__main__":
    main()
