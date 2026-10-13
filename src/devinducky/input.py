"""Turn the pad's hotkeys into tap / hold / press events.

The pad types a hotkey on key-down and another on key-up (see keys.py). The
listener decodes those, and HoldClassifier times the gap so a quick tap and a
long hold become different actions. The hold fires *while* the key is still
down (at hold_ms), so the LED can confirm before you let go.
"""

import queue
import threading
import time

from . import keys


class HoldClassifier:
    """Pure state machine; callers pass the clock in so it's testable."""

    def __init__(self, hold_ms):
        self.hold_s = hold_ms / 1000
        self.pressed = {}            # key -> down time; removed once hold fires

    def down(self, key, now):
        self.pressed[key] = now

    def up(self, key, now):
        """Returns "tap" if released before the hold fired, else None."""
        t0 = self.pressed.pop(key, None)
        if t0 is None:
            return None              # hold already fired, or we missed the down
        return "tap" if now - t0 < self.hold_s else "hold"

    def due(self, now):
        """Keys whose hold threshold has passed; each fires once."""
        fired = [k for k, t0 in self.pressed.items() if now - t0 >= self.hold_s]
        for k in fired:
            del self.pressed[k]
        return fired


_MOD_NAMES = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
}


def _key_name(k):
    return getattr(k, "name", None)  # pynput Key enum members have .name; chars don't


def decode(mods, fkey):
    """Held modifier names + an F-key name -> keys.Event, or None."""
    order = [m for m in ("ctrl", "alt", "shift", "cmd") if m in mods]
    return keys.EVENT_FOR.get(keys.Hotkey(tuple(order), fkey))


class PadInput:
    """Runs the pynput listener and emits (kind, key) on self.events.

    kind is "tap" or "hold" for slot keys, "press" for everything else.
    """

    def __init__(self, hold_ms, on_raw=None):
        self.events = queue.Queue()
        self.clf = HoldClassifier(hold_ms)
        self.mods = set()
        self.on_raw = on_raw          # optional debug hook: (Event, timestamp)
        self._lock = threading.Lock()

    def _on_press(self, k):
        name = _key_name(k)
        if name in _MOD_NAMES:
            self.mods.add(_MOD_NAMES[name])
        elif name in keys.FKEYS:
            ev = decode(self.mods, name)
            if ev:
                self._handle(ev)

    def _on_release(self, k):
        name = _key_name(k)
        if name in _MOD_NAMES:
            self.mods.discard(_MOD_NAMES[name])

    def _handle(self, ev):
        now = time.monotonic()
        if self.on_raw:
            self.on_raw(ev, now)
        with self._lock:
            if ev.kind == "down":
                self.clf.down(ev.key, now)
            elif ev.kind == "up":
                if self.clf.up(ev.key, now) == "tap":
                    self.events.put(("tap", ev.key))
            else:
                self.events.put(("press", ev.key))

    def _hold_loop(self):
        while True:
            time.sleep(0.03)
            with self._lock:
                fired = self.clf.due(time.monotonic())
            for k in fired:
                self.events.put(("hold", k))

    def start(self):
        from pynput import keyboard
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.daemon = True
        listener.start()
        threading.Thread(target=self._hold_loop, daemon=True).start()
        return listener
