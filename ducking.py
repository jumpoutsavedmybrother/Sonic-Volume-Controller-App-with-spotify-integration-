"""Auto-ducking: lower the music while a call/chat app is making sound, then bring it back.

Two parts:
  DuckController  the timing "brain": from the trigger apps' loudness it works out a gain factor
                  (1.0 = normal, `amount` = fully ducked), with an attack delay so short pings are ignored,
                  a release delay so it doesn't pump between words, and smooth fades.
  Ducker          applies that factor to the target apps' volumes and remembers each app's real volume,
                  so it can put it back exactly. The real volumes are reported through `on_change` so the UI can
                  save them: if the program ever crashes mid-duck, the next start restores them."""
import time

import audio

DEFAULT_TRIGGERS = ("discord.exe", "discordptb.exe", "discordcanary.exe", "teams.exe", "ms-teams.exe",
                    "zoom.exe", "skype.exe", "slack.exe")


class DuckController:
    def __init__(self, amount=0.3, threshold=0.02, attack_s=0.25, release_s=1.5, fade_down_s=0.3, fade_up_s=1.0):
        self.amount = min(1.0, max(0.0, float(amount)))
        self.threshold = float(threshold)
        self.attack_s, self.release_s = attack_s, release_s
        self.fade_down_s, self.fade_up_s = fade_down_s, fade_up_s
        self.reset()

    def reset(self):
        self.factor = 1.0
        self.triggered = False
        self._loud_since = None
        self._last_loud = None
        self._last_now = None

    @property
    def ducked(self):
        return self.factor < 0.999

    def update(self, peak, now):
        """Feed the loudest trigger app's peak (0..1) at time `now` (seconds). Returns the gain factor."""
        if peak > self.threshold:
            self._last_loud = now
            if self._loud_since is None:
                self._loud_since = now
            if not self.triggered and now - self._loud_since >= self.attack_s:
                self.triggered = True
        else:
            self._loud_since = None
            if self.triggered and self._last_loud is not None and now - self._last_loud >= self.release_s:
                self.triggered = False

        dt = 0.0 if self._last_now is None else min(max(now - self._last_now, 0.0), 0.5)
        self._last_now = now
        target = self.amount if self.triggered else 1.0
        span = 1.0 - self.amount
        if self.factor > target:
            step = span if self.fade_down_s <= 0 else span / self.fade_down_s * dt
            self.factor = max(target, self.factor - step)
        elif self.factor < target:
            step = span if self.fade_up_s <= 0 else span / self.fade_up_s * dt
            self.factor = min(target, self.factor + step)
        return self.factor


class Ducker:
    def __init__(self, triggers=DEFAULT_TRIGGERS, extra_targets=(), amount=0.3, threshold=0.02, on_change=None):
        self.enabled = False
        self.triggers = {t.lower() for t in triggers}
        self.extra_targets = {t.lower() for t in extra_targets}      # always ducked, besides the app playing media
        self.controller = DuckController(amount, threshold)
        self.pending = {}                                            # volumes left over from a crashed run
        self._on_change = on_change                                  # called with {process: real volume} when it changes
        self._originals = {}                                         # session key -> {"proc", "level"}
        self._applied = {}                                           # session key -> level we last set
        self._reported = {}

    @property
    def active(self):
        """Enabled, or still holding some app's volume down (so the fast loop must keep running to restore it)."""
        return self.enabled or bool(self._originals)

    @property
    def busy(self):
        """active, or waiting to restore volumes left over from a crashed run."""
        return self.active or bool(self.pending)

    # ---- volumes the user sets while ducked ----
    @property
    def factor(self):
        return self.controller.factor

    def unduck(self, proc, value):
        """A volume the user sees right now -> the 'real' volume it stands for (value / factor while ducked)."""
        if self.controller.ducked and any(e["proc"] == proc for e in self._originals.values()):
            return min(1.0, value / max(self.controller.factor, 0.05))
        return value

    def set_real_level(self, proc, level):
        """The user chose a new real volume for this app (e.g. a preset). Returns the volume to apply right now."""
        ducked = [k for k, e in self._originals.items() if e["proc"] == proc]
        if not ducked or not self.controller.ducked:
            return level
        for key in ducked:
            self._originals[key]["level"] = level
            self._applied[key] = level * self.controller.factor
        return level * self.controller.factor

    # ---- main loop ----
    def tick(self, sessions, media_proc, now=None):
        now = time.monotonic() if now is None else now
        self.restore_pending(sessions)
        if not self.enabled:
            if self._originals:
                self.release(sessions)
            return

        loudest = 0.0
        for s in sessions:
            if audio.process_name(s) in self.triggers:
                loudest = max(loudest, audio.peak(s))
        factor = self.controller.update(loudest, now)

        live, targets = {}, {}
        for s in sessions:
            proc = audio.process_name(s)
            if not proc:
                continue
            key = audio.session_key(s)
            live[key] = s
            if proc not in self.triggers and (proc == media_proc or proc in self.extra_targets):
                targets[key] = (proc, s)

        for key in [k for k in self._originals if k not in targets]:      # no longer a target (or gone)
            if key in live:                                               # still running: put its volume back first
                self._set(live[key], self._originals[key]["level"])
            self._forget(key)
        for key, (proc, s) in targets.items():
            self._apply(key, proc, s, factor)
        self._report()

    def _apply(self, key, proc, session, factor):
        try:
            vol = audio.volume_interface(session)
            level, _ = audio.read_volume(vol)
        except Exception:
            return
        entry = self._originals.get(key)
        if entry is None:
            if factor >= 0.999:
                return
            entry = self._originals[key] = {"proc": proc, "level": level}
            self._applied[key] = level
        elif abs(level - self._applied.get(key, level)) > 0.03:
            # changed by the user (or the app) while ducked: treat that as the new normal volume
            entry["level"] = min(1.0, level / max(factor, 0.05))
        if factor >= 0.999:
            audio.set_volume(vol, entry["level"])
            self._forget(key)
            return
        new_level = entry["level"] * factor
        if abs(new_level - level) > 0.002:
            audio.set_volume(vol, new_level)
        self._applied[key] = new_level

    def _set(self, session, level):
        try:
            audio.set_volume(audio.volume_interface(session), level)
        except Exception:
            pass

    def _forget(self, key):
        self._originals.pop(key, None)
        self._applied.pop(key, None)

    def release(self, sessions):
        """Put every ducked app back to its real volume (used when ducking is switched off or on quit)."""
        live = {audio.session_key(s): s for s in sessions}
        for key, entry in list(self._originals.items()):
            if key in live:
                self._set(live[key], entry["level"])
            self._forget(key)
        self.controller.reset()
        self._report()

    # ---- crash recovery ----
    def persistable(self):
        """{process: real volume} for everything currently ducked, plus anything still waiting to be restored."""
        out = dict(self.pending)
        for entry in self._originals.values():
            out[entry["proc"]] = entry["level"]
        return out

    def load_pending(self, mapping):
        """Volumes saved by a previous run that may have crashed mid-duck (validated: process -> 0..1)."""
        self.pending = {p.lower(): min(1.0, max(0.0, float(v))) for p, v in (mapping or {}).items()
                        if isinstance(p, str) and isinstance(v, (int, float)) and not isinstance(v, bool)}
        self._reported = dict(self.pending)

    def restore_pending(self, sessions):
        if not self.pending:
            return
        running = set()
        for s in sessions:
            proc = audio.process_name(s)
            if proc in self.pending:
                self._set(s, self.pending[proc])
                running.add(proc)
        if running:
            self.pending = {p: v for p, v in self.pending.items() if p not in running}
            self._report()

    def _report(self):
        current = self.persistable()
        if current != self._reported:
            self._reported = current
            if self._on_change:
                self._on_change(current)
