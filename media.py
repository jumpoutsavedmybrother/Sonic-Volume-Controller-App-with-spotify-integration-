"""
media.py - reads and controls the Windows "now playing" session (SMTC) so Sonic no longer has to
scrape window titles, guess album covers online, or track pause state by hand.

All WinRT work happens on one background thread with its own asyncio loop. The UI thread never
touches WinRT: it calls get_state() for the latest snapshot and the command methods to control playback.
"""
import asyncio
import datetime
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Optional

# Substring of the app's AppUserModelID -> the process name pycaw reports for its audio session
_AUMID_HINTS = (
    ("spotify", "spotify.exe"),
    ("msedge", "msedge.exe"),
    ("chrome", "chrome.exe"),
    ("firefox", "firefox.exe"),
    ("308046b0af4a39cb", "firefox.exe"),   # Firefox's AUMID
    ("brave", "brave.exe"),
    ("operagx", "opera.exe"),        # Opera GX also runs as opera.exe; listed explicitly in case its ID has no "opera " in it
    ("opera gx", "opera.exe"),
    ("opera_gx", "opera.exe"),
    ("opera", "opera.exe"),
)


def aumid_to_process(aumid):
    """Best-effort map from a media app's AppUserModelID to its .exe name (None if unknown)."""
    a = (aumid or "").lower()
    for hint, proc in _AUMID_HINTS:
        if hint in a:
            return proc
    if a.endswith(".exe"):
        return a
    return None


def friendly_app_name(aumid, process):
    if process:
        return process.replace(".exe", "").capitalize()
    tail = (aumid or "").split("!")[-1].split(".")[-1]
    return tail or "Media app"


@dataclass(frozen=True)
class MediaState:
    present: bool = False          # is there a media session at all?
    title: str = ""
    artist: str = ""
    status: str = "none"           # "playing" | "paused" | "stopped" | "none"
    aumid: str = ""
    process: Optional[str] = None  # e.g. "spotify.exe", or None if we can't map the app
    app_name: str = ""
    is_spotify: bool = False
    thumb: Optional[bytes] = None  # encoded image bytes (JPEG/PNG) from Windows
    art_id: int = 0                # changes whenever `thumb` changes
    art_pending: bool = False      # Windows hasn't given us this track's art yet
    position_s: float = 0.0        # playback position in seconds, as of `stamp`
    duration_s: float = 0.0        # track length in seconds (0 = unknown / live)
    can_seek: bool = False         # does the app allow jumping to a position?
    stamp: float = 0.0             # time.monotonic() when this snapshot was taken
    error: Optional[str] = None


class MediaWatcher:
    POLL_SECONDS = 0.5
    ART_RETRIES = 5   # Spotify can update the title before the thumbnail, so re-read art a few times

    def __init__(self):
        self._lock = threading.Lock()
        self._state = MediaState()
        self._stop = threading.Event()
        self._thread = None
        self._loop = None
        # Everything below is touched only from the worker thread
        self._session = None
        self._PlaybackStatus = None
        self._DataReader = None
        self._track_key = None
        self._thumb = None
        self._thumb_hash = None
        self._prev_hash = None
        self._art_attempts = 0
        self._art_id = 0
        self._timeline_start = 0.0
        self._warned = set()

    # ---------------- public API (called from the UI thread) ----------------
    def start(self):
        self._thread = threading.Thread(target=self._thread_main, name="media-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def get_state(self):
        with self._lock:
            return self._state

    def toggle_play_pause(self):
        return self._submit("toggle")

    def next(self):
        return self._submit("next")

    def previous(self):
        return self._submit("previous")

    def seek(self, seconds):
        """Jump to this many seconds into the track."""
        return self._submit("seek", seconds)

    # ---------------- worker thread ----------------
    def _set_state(self, state):
        with self._lock:
            self._state = state

    def _submit(self, name, arg=None):
        """Queue a command on the worker loop. Returns False if there's nothing to control."""
        loop = self._loop
        if loop is None or self._session is None:
            return False
        asyncio.run_coroutine_threadsafe(self._do_command(name, arg), loop)
        return True

    def _thread_main(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self._set_state(MediaState(error=f"Media access failed: {e}"))

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        try:
            # Imported here, not at the top of the file: winrt sets up its COM apartment on first
            # import, and that needs to happen on this worker thread (the Tk thread is already
            # initialised by pycaw). If you ever see "RPC_E_CHANGED_MODE", look here first.
            import winrt.windows.foundation                      # noqa: F401
            import winrt.windows.foundation.collections          # noqa: F401  (lets us iterate get_sessions())
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
            )
            from winrt.windows.storage.streams import DataReader
        except ImportError as e:
            print(f"media: winrt import failed: {e!r}")   # full detail for the Thonny Shell / console
            missing = getattr(e, "name", None) or str(e)
            self._set_state(MediaState(error=f"Media info: can't import {missing} (see Shell, requirements.txt)"))
            return

        self._PlaybackStatus = PlaybackStatus
        self._DataReader = DataReader
        manager = await Manager.request_async()

        while not self._stop.is_set():
            try:
                self._set_state(await self._snapshot(manager))
            except Exception as e:
                print(f"media poll failed: {e}")   # keep the last good state and try again
            await asyncio.sleep(self.POLL_SECONDS)

    def _pick(self, sessions, manager):
        """Prefer Spotify (the playing one if there are several); otherwise whatever Windows says is current."""
        spotify = [s for s in sessions if "spotify" in (s.source_app_user_model_id or "").lower()]
        if spotify:
            for s in spotify:
                if s.get_playback_info().playback_status == self._PlaybackStatus.PLAYING:
                    return s
            return spotify[0]
        return manager.get_current_session()

    async def _snapshot(self, manager):
        sessions = list(manager.get_sessions())
        session = self._pick(sessions, manager)
        self._session = session
        if session is None:
            self._track_key = None
            return MediaState()

        aumid = session.source_app_user_model_id or ""
        process = aumid_to_process(aumid)
        if process is None and aumid not in self._warned:
            self._warned.add(aumid)
            print(f"media: don't know which process owns the media app {aumid!r} - add it to _AUMID_HINTS")
        info = session.get_playback_info()
        raw_status = info.playback_status
        if raw_status == self._PlaybackStatus.PLAYING:
            status = "playing"
        elif raw_status == self._PlaybackStatus.PAUSED:
            status = "paused"
        else:
            status = "stopped"

        props = await session.try_get_media_properties_async()
        title = props.title or ""
        artist = props.artist or ""

        key = (aumid, title, artist, props.album_title or "")
        if key != self._track_key:
            self._track_key = key
            self._prev_hash = self._thumb_hash
            self._thumb = None
            self._thumb_hash = None
            self._art_attempts = 0

        # Read the thumbnail on a new track, and keep re-reading briefly while it still matches the
        # previous track's art (Windows sometimes hasn't swapped it yet).
        stale_or_missing = self._thumb is None or self._thumb_hash == self._prev_hash
        if stale_or_missing and self._art_attempts < self.ART_RETRIES:
            self._art_attempts += 1
            data = await self._read_thumbnail(props)
            if data:
                h = hashlib.md5(data).hexdigest()
                if h != self._thumb_hash:
                    self._thumb, self._thumb_hash = data, h
                    self._art_id += 1

        position_s, duration_s = self._read_timeline(session, status)
        try:
            can_seek = bool(info.controls.is_playback_position_enabled)
        except Exception:
            can_seek = False

        return MediaState(
            present=True, title=title, artist=artist, status=status, aumid=aumid,
            process=process, app_name=friendly_app_name(aumid, process),
            is_spotify="spotify" in aumid.lower(),
            thumb=self._thumb, art_id=self._art_id,
            art_pending=self._thumb is None and self._art_attempts < self.ART_RETRIES,
            position_s=position_s, duration_s=duration_s, can_seek=can_seek, stamp=time.monotonic(),
        )

    def _read_timeline(self, session, status):
        """(position, duration) in seconds. Windows reports the position "as of" a timestamp and apps
        update it at their own pace, so while playing we add the time that has passed since then."""
        try:
            tl = session.get_timeline_properties()
            start = tl.start_time.total_seconds()
            duration = max(0.0, tl.end_time.total_seconds() - start)
            position = tl.position.total_seconds() - start
            self._timeline_start = start
            if status == "playing":
                updated = tl.last_updated_time
                if updated is not None:
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=datetime.timezone.utc)
                    elapsed = (datetime.datetime.now(datetime.timezone.utc) - updated).total_seconds()
                    if 0 <= elapsed < 6 * 3600:   # ignore a never-set timestamp (year 1601)
                        position += elapsed
            position = max(0.0, position)
            if duration > 0:
                position = min(position, duration)
            return position, duration
        except Exception:
            return 0.0, 0.0

    async def _read_thumbnail(self, props):
        try:
            ref = props.thumbnail
            if ref is None:
                return None
            stream = await ref.open_read_async()
            size = int(stream.size)
            if size <= 0:
                return None
            reader = self._DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception as e:
            print(f"thumbnail read failed: {e}")
            return None

    async def _do_command(self, name, arg=None):
        session = self._session
        if session is None:
            return
        try:
            if name == "seek":
                ticks = int((self._timeline_start + float(arg)) * 10_000_000)   # Windows wants 100-nanosecond ticks
                await session.try_change_playback_position_async(ticks)
            elif name == "toggle":
                await session.try_toggle_play_pause_async()
            elif name == "next":
                await session.try_skip_next_async()
            elif name == "previous":
                await session.try_skip_previous_async()
        except Exception as e:
            print(f"media command {name} failed: {e}")
