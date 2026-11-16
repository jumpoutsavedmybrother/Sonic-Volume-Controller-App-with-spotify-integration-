"""Windows per-app volume (pycaw). No UI code in here: the rest of the app only calls these functions."""
import warnings

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

try:
    from pycaw.constants import DEVICE_STATE, EDataFlow
except Exception:   # an older pycaw without these: device listing is then switched off, everything else still works
    DEVICE_STATE = EDataFlow = None

BROWSERS = ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe")
EXCLUDED_PROCS = ("spotifywidgetprovider.exe",)


def list_sessions():
    """All audio sessions, or None if Windows couldn't be read (so callers can skip a refresh
    instead of treating it as "no apps")."""
    try:
        return AudioUtilities.GetAllSessions()
    except Exception as e:
        print(f"Could not read audio sessions: {e}")
        return None


def process_name(session):
    try:
        return session.Process.name().lower() if session.Process else ""
    except Exception:
        return ""


def pretty_name(proc):
    return proc.replace(".exe", "").capitalize()


def is_active(session):
    try:
        return session.State == 1   # AudioSessionStateActive
    except Exception:
        return False


def session_key(session):
    try:
        key = session.InstanceIdentifier
    except Exception:
        key = None
    return key or f"pid:{session.ProcessId}"


def volume_interface(session):
    return session._ctl.QueryInterface(ISimpleAudioVolume)


def read_volume(vol):
    """Returns (level 0..1, muted). Raises if the session has gone away."""
    return vol.GetMasterVolume(), bool(vol.GetMute())


def set_volume(vol, value):
    if vol is None:
        return
    try: vol.SetMasterVolume(float(value), None)
    except Exception: pass


def set_mute(vol, muted):
    if vol is None:
        return
    try: vol.SetMute(bool(muted), None)
    except Exception: pass


def toggle_mute(vol):
    if vol is None:
        return
    try: vol.SetMute(not vol.GetMute(), None)
    except Exception: pass


def find_session(sessions, wanted_process):
    """The session for a given .exe, preferring one that's actively playing. None if there isn't one."""
    if not wanted_process:
        return None
    matches = [s for s in sessions if process_name(s) == wanted_process]
    active = [s for s in matches if is_active(s)]
    return (active or matches or [None])[0]


def other_sessions(sessions, exclude_key=None):
    """{key: session} for every app except `exclude_key` (the one shown in the top box) and helper processes."""
    wanted = {}
    for s in sessions:
        name = process_name(s)
        if not name or name in EXCLUDED_PROCS:
            continue
        key = session_key(s)
        if key == exclude_key or key in wanted:
            continue
        wanted[key] = s
    return wanted


# ---------------------------------------------------------------- master volume + output devices
def _speakers():
    """The current default output device, or None."""
    try:
        return AudioUtilities.GetSpeakers()
    except Exception as e:
        print(f"Could not get the default output device: {e}")
        return None


def read_master():
    """{"level", "muted", "id", "name"} for the default output device, or None."""
    dev = _speakers()
    if dev is None:
        return None
    try:
        vol = dev.EndpointVolume
        return {"level": float(vol.GetMasterVolumeLevelScalar()), "muted": bool(vol.GetMute()),
                "id": dev.id, "name": dev.FriendlyName}
    except Exception:
        return None


def set_master_volume(value):
    dev = _speakers()
    if dev is None:
        return
    try: dev.EndpointVolume.SetMasterVolumeLevelScalar(float(value), None)
    except Exception: pass


def toggle_master_mute():
    dev = _speakers()
    if dev is None:
        return
    try:
        vol = dev.EndpointVolume
        vol.SetMute(not vol.GetMute(), None)
    except Exception: pass


def list_output_devices():
    """[(device_id, friendly_name)] for active output devices; [] if they can't be listed."""
    if DEVICE_STATE is None or EDataFlow is None:
        return []
    try:
        with warnings.catch_warnings():   # pycaw warns about devices it can't read; that's harmless here
            warnings.simplefilter("ignore", UserWarning)
            devices = AudioUtilities.GetAllDevices(data_flow=EDataFlow.eRender.value,
                                                   device_state=DEVICE_STATE.ACTIVE.value)
        return [(d.id, d.FriendlyName) for d in devices if d.FriendlyName]
    except Exception as e:
        print(f"Could not list output devices: {e}")
        return []


def set_default_device(device_id):
    """Make this the Windows default output. Returns True on success."""
    try:
        AudioUtilities.SetDefaultDevice(device_id)
        return True
    except Exception as e:
        print(f"Could not switch output device: {e}")
        return False
