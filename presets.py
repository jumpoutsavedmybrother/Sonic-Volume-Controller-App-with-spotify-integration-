"""Volume presets: a few saved 'mixes' (each app's level and mute). Pure data, no UI or Windows calls."""

SLOTS = ("1", "2", "3", "4")


def _clean_apps(apps):
    """Keep only valid {"proc": {"level": 0..1, "muted": bool}} entries."""
    clean = {}
    if not isinstance(apps, dict):
        return clean
    for proc, entry in apps.items():
        if not (isinstance(proc, str) and proc and isinstance(entry, dict)):
            continue
        level = entry.get("level")
        if isinstance(level, bool) or not isinstance(level, (int, float)):
            continue
        clean[proc.lower()] = {"level": min(1.0, max(0.0, float(level))), "muted": bool(entry.get("muted", False))}
    return clean


class PresetStore:
    def __init__(self, data=None):
        self._slots = {}
        if isinstance(data, dict):
            for slot, entry in data.items():
                apps = _clean_apps(entry.get("apps") if isinstance(entry, dict) else None)
                if slot in SLOTS and apps:
                    self._slots[slot] = apps

    def has(self, slot):
        return slot in self._slots

    def get(self, slot):
        """{proc: {"level", "muted"}} for this slot, or None if it's empty."""
        apps = self._slots.get(slot)
        return {proc: dict(entry) for proc, entry in apps.items()} if apps else None

    def save(self, slot, apps):
        """Store a mix. Returns how many apps were saved (0 means nothing was stored)."""
        apps = _clean_apps(apps)
        if slot in SLOTS and apps:
            self._slots[slot] = apps
            return len(apps)
        return 0

    def clear(self, slot):
        self._slots.pop(slot, None)

    def to_dict(self):
        return {slot: {"apps": {proc: dict(e) for proc, e in apps.items()}} for slot, apps in self._slots.items()}
