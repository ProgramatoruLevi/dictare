#!/usr/bin/env python3
"""Record 16 kHz mono WAV until SIGINT/SIGTERM, then close the file cleanly.

macOS has no pw-record equivalent, and pulling in ffmpeg or sox would mean a
Homebrew dependency. sounddevice ships PortAudio inside its wheel, so this stays
a pip-only install.
"""
import argparse
import queue
import signal
import wave

import sounddevice as sd

RATE = 16000

stopping = False


def _stop(_sig, _frame):
    global stopping
    stopping = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--rate", type=int, default=RATE)
    ap.add_argument("--device", default=None,
                    help="input device name or index (default: system default)")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    blocks = queue.Queue()

    def callback(indata, _frames, _time, _status):
        blocks.put(bytes(indata))

    device = args.device
    if device is not None and device.isdigit():
        device = int(device)

    with wave.open(args.path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(args.rate)
        with sd.RawInputStream(samplerate=args.rate, channels=1, dtype="int16",
                               device=device, callback=callback):
            while not stopping:
                try:
                    wav.writeframes(blocks.get(timeout=0.1))
                except queue.Empty:
                    pass
            while not blocks.empty():          # flush whatever is still buffered
                wav.writeframes(blocks.get())


if __name__ == "__main__":
    main()
