#!/usr/bin/env python3
"""Push-to-talk daemon: hold a key to record, release to transcribe.

Reads evdev passively (never grabs, so the key keeps working normally) and
drives `dictare start` / `dictare stop`.

A bare hold is the trigger. If any other key goes down while the trigger is
held, the gesture is abandoned — otherwise Right Ctrl + C would fire a
recording on every copy.
"""
import argparse
import glob
import os
import re
import selectors
import struct
import subprocess
import sys
import time

# struct input_event on 64-bit Linux: two longs (timeval), u16, u16, s32
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

EV_KEY = 0x01
KEY_RIGHTCTRL = 97

# Modifiers never abort a gesture. Catching Shift here was a real bug: holding
# the trigger and brushing Shift silently threw away a finished recording.
MODIFIERS = {
    29, 97,    # ctrl
    42, 54,    # shift
    56, 100,   # alt
    125, 126,  # meta
    58, 464,   # capslock, fn
}

DICTARE = os.path.expanduser("~/.local/bin/dictare")


def log(msg):
    print(f"[pttd] {msg}", flush=True)


# ydotool's own uinput device echoes every key we synthesize; watching it would
# let a paste abort the next gesture, and a synthetic trigger start a recording.
EXCLUDE_NAMES = ("ydotoold virtual device",)


def autodetect(keycode):
    """Every evdev node whose kernel key bitmap advertises the trigger key."""
    found = []
    blocks = open("/proc/bus/input/devices").read().split("\n\n")
    for block in blocks:
        m_key = re.search(r"B: KEY=([0-9a-f ]+)", block)
        m_hnd = re.search(r"H: Handlers=(.*)", block)
        m_name = re.search(r'N: Name="(.*)"', block)
        if not (m_key and m_hnd):
            continue
        if m_name and m_name.group(1) in EXCLUDE_NAMES:
            continue
        bits = set()
        for i, word in enumerate(reversed(m_key.group(1).split())):
            value = int(word, 16)
            for j in range(64):
                if value >> j & 1:
                    bits.add(i * 64 + j)
        if keycode not in bits:
            continue
        for handler in m_hnd.group(1).split():
            if handler.startswith("event"):
                found.append(f"/dev/input/{handler}")
    return found


AS_USER = None  # set by --as-user: (uid, home, runtime_dir, wayland, dbus)


def fire(action):
    if AS_USER:
        uid, home, runtime, wayland, dbus = AS_USER
        cmd = ["setpriv", f"--reuid={uid}", f"--regid={uid}", "--init-groups",
               "env", f"HOME={home}", f"XDG_RUNTIME_DIR={runtime}",
               f"WAYLAND_DISPLAY={wayland}", f"DBUS_SESSION_BUS_ADDRESS={dbus}",
               f"{home}/.local/bin/dictare", action]
    else:
        cmd = [DICTARE, action]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log(f"cannot run dictare {action}: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", action="append", default=[],
                    help="evdev node to watch (repeatable); default: autodetect")
    ap.add_argument("--key", type=int, default=KEY_RIGHTCTRL)
    ap.add_argument("--hold-ms", type=int, default=250,
                    help="how long the key must be held alone before recording")
    ap.add_argument("--dry-run", action="store_true",
                    help="log transitions instead of calling dictare")
    # Escape hatch for running the daemon as root before the user's 'input'
    # group membership has taken effect (it only applies to a fresh login).
    ap.add_argument("--as-user", metavar="UID:HOME:RUNTIME:WAYLAND:DBUS",
                    help="drop to this user when invoking dictare")
    args = ap.parse_args()

    if args.as_user:
        global AS_USER
        AS_USER = tuple(args.as_user.split(":", 4))
        log(f"will invoke dictare as uid {AS_USER[0]}")

    devices = args.device or autodetect(args.key)
    if not devices:
        log(f"no input device exposes keycode {args.key}")
        return 1

    sel = selectors.DefaultSelector()
    opened = []
    for path in devices:
        try:
            fd = open(path, "rb", buffering=0)
        except PermissionError:
            log(f"permission denied: {path} — are you in the 'input' group? "
                f"(a fresh login is required after usermod)")
            continue
        except OSError as exc:
            log(f"skip {path}: {exc}")
            continue
        sel.register(fd, selectors.EVENT_READ)
        opened.append(path)
    if not opened:
        return 1
    log(f"watching keycode {args.key} on: {', '.join(opened)}")

    act = (lambda a: log(f"-> {a}")) if args.dry_run else fire
    pending_since = None   # trigger is down, not yet long enough
    recording = False

    while True:
        timeout = None
        if pending_since is not None:
            timeout = max(0.0, args.hold_ms / 1000 - (time.monotonic() - pending_since))
        events = sel.select(timeout)

        if not events and pending_since is not None:
            pending_since, recording = None, True
            act("start")
            continue

        for key, _ in events:
            data = key.fileobj.read(EVENT_SIZE)
            if not data or len(data) < EVENT_SIZE:
                continue
            _, _, etype, code, value = struct.unpack(EVENT_FMT, data)
            if etype != EV_KEY:
                continue

            if code == args.key:
                if value == 1:                      # trigger pressed
                    pending_since = time.monotonic()
                elif value == 0:                    # trigger released
                    pending_since = None
                    if recording:
                        recording = False
                        act("stop")
            elif (value == 1 and code not in MODIFIERS
                  and (pending_since is not None or recording)):
                # A real key went down mid-gesture: this was a shortcut.
                pending_since = None
                if recording:
                    recording = False
                    act("cancel")


if __name__ == "__main__":
    sys.exit(main())
