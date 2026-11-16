"""Remembers the volume/mute the user last chose for each app, keyed by process name (e.g. "discord.exe").
Pure data: no UI and no Windows calls, so it's easy to test."""


class VolumeMemory:
    def __init__(self, data=None):
        self._data = {}
        if isinstance(data, dict):
            for proc, entry in data.items():
                entry = self._clean(entry)
                if isinstance(proc, str) and proc and entry:
                    self._data[proc.lower()] = entry

    @staticmethod
    def _clean(entry):
        """Accept only {"level": 0..1, "muted": bool}; anything else in a hand-edited file is ignored."""
        if not isinstance(entry, dict):
            return None
        level = entry.get("level")
        muted = entry.get("muted", False)
        if isinstance(level, bool) or not isinstance(level, (int, float)):
            return None
        return {"level": min(1.0, max(0.0, float(level))), "muted": bool(muted)}

    def get(self, proc):
        """(level, muted) for this app, or None if the user never changed it."""
        entry = self._data.get((proc or "").lower())
        return (entry["level"], entry["muted"]) if entry else None

    def remember(self, proc, level=None, muted=None):
        """Record a change the user made. Only the fields given are updated."""
        if not proc:
            return
        entry = self._data.setdefault(proc.lower(), {"level": 1.0, "muted": False})
        if level is not None:
            entry["level"] = min(1.0, max(0.0, float(level)))
        if muted is not None:
            entry["muted"] = bool(muted)

    def forget(self, proc):
        self._data.pop((proc or "").lower(), None)

    def to_dict(self):
        return {proc: dict(entry) for proc, entry in self._data.items()}
