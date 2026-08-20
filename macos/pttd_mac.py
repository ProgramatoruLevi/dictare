#!/usr/bin/env python3
"""Push-to-talk for macOS: hold Right Command (or Right Ctrl) to record.

macOS has no evdev. pynput taps the same Quartz event stream the system uses,
which is why macOS demands Input Monitoring / Accessibility permission for
whatever app launches this — see README.md.

The state machine lives in PushToTalk, deliberately free of pynput, so it can be
tested without a keyboard or a Mac.
"""
import argparse
import os
import subprocess
import sys
import threading
import time

DICTARE = os.path.expanduser("~/.local/bin/dictare")

# Modifiers never abort a gesture — brushing Shift mid-hold must not throw the
# recording away. Only real keys mean "this was a shortcut, not a dictation".
MODIFIER_NAMES = {
    "shift", "shift_r", "shift_l", "ctrl", "ctrl_r", "ctrl_l",
    "alt", "alt_r", "alt_l", "alt_gr", "cmd", "cmd_r", "cmd_l", "caps_lock",
}


def is_modifier(key):
    return getattr(key, "name", None) in MODIFIER_NAMES


def log(msg):
    print(f"[pttd] {msg}", flush=True)


class PushToTalk:
    """Hold the trigger alone past `hold_ms` to record; release to transcribe.

    Any other key going down mid-gesture abandons it, so ordinary shortcuts that
    use the trigger as a modifier never fire a recording.
    """

    def __init__(self, hold_ms, on_start, on_stop, on_cancel, clock=time.monotonic):
        self.hold = hold_ms / 1000.0
        self.on_start, self.on_stop, self.on_cancel = on_start, on_stop, on_cancel
        self.clock = clock
        self.pending_since = None
        self.recording = False
        self._lock = threading.Lock()

    def trigger_down(self):
        with self._lock:
            if self.pending_since is None and not self.recording:
                self.pending_since = self.clock()

    def trigger_up(self):
        with self._lock:
            self.pending_since = None
            if self.recording:
                self.recording = False
                fire = self.on_stop
            else:
                return
        fire()

    def other_key_down(self):
        with self._lock:
            if self.pending_since is None and not self.recording:
                return
            self.pending_since = None
            was_recording, self.recording = self.recording, False
        if was_recording:
            self.on_cancel()

    def tick(self):
        """Call periodically; promotes a long-enough hold into a recording."""
        with self._lock:
            if self.pending_since is None:
                return
            if self.clock() - self.pending_since < self.hold:
                return
            self.pending_since = None
            self.recording = True
        self.on_start()


def fire(action):
    try:
        subprocess.Popen([DICTARE, action],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log(f"cannot run dictare {action}: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="cmd_r",
                    choices=["cmd_r", "ctrl_r", "alt_r", "f13", "f14", "f15"],
                    help="trigger key (default: Right Command)")
    ap.add_argument("--hold-ms", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        from pynput import keyboard
    except ImportError:
        log("pynput is missing — run install.sh first")
        return 1

    trigger = getattr(keyboard.Key, args.key, None)
    if trigger is None:
        log(f"unknown key {args.key}")
        return 1

    act = (lambda a: log(f"-> {a}")) if args.dry_run else fire
    ptt = PushToTalk(args.hold_ms,
                     lambda: act("start"), lambda: act("stop"), lambda: act("cancel"))

    def on_press(key):
        if key == trigger:
            ptt.trigger_down()
        elif not is_modifier(key):
            ptt.other_key_down()

    def on_release(key):
        if key == trigger:
            ptt.trigger_up()

    def ticker():
        while True:
            ptt.tick()
            time.sleep(0.025)

    threading.Thread(target=ticker, daemon=True).start()
    log(f"watching {args.key} (hold {args.hold_ms}ms)")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
