#!/usr/bin/env python3
"""Dictation daemon: keeps faster-whisper resident in RAM and transcribes over HTTP.

POST /transcribe  body = raw WAV bytes        -> {"text": "..."}
GET  /health                                  -> {"ok": true, "model": "..."}
"""
import json
import os
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from faster_whisper import WhisperModel

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".local", "share", "dictare")

MODEL_NAME = os.environ.get("DICTARE_MODEL", "large-v3-turbo")
LANGUAGE = os.environ.get("DICTARE_LANG", "ro")
BEAM_SIZE = int(os.environ.get("DICTARE_BEAM", "5"))
THREADS = int(os.environ.get("DICTARE_THREADS", str(max(4, (os.cpu_count() or 8) - 2))))
PORT = int(os.environ.get("DICTARE_PORT", "8910"))

VOCAB_PATH = os.path.join(BASE, "vocab.txt")
try:
    with open(VOCAB_PATH, encoding="utf-8") as fh:
        INITIAL_PROMPT = fh.read().strip()
except OSError:
    INITIAL_PROMPT = None


def log(msg):
    print(f"[dictare] {msg}", flush=True)


log(f"loading {MODEL_NAME} (int8, {THREADS} threads)…")
_t0 = time.time()
model = WhisperModel(
    MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=THREADS
)
log(f"model loaded in {time.time() - _t0:.1f}s")


def transcribe(wav_path):
    segments, info = model.transcribe(
        wav_path,
        language=LANGUAGE,
        beam_size=BEAM_SIZE,
        initial_prompt=INITIAL_PROMPT,
        # Each dictation is independent — never carry text across invocations,
        # otherwise the previous prompt bleeds into the next one.
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        temperature=[0.0, 0.2, 0.4],
    )
    text = "".join(s.text for s in segments).strip()
    return text, info


# Warm the kernels up so the first real dictation is not the slow one.
try:
    import wave

    _warm = os.path.join(tempfile.gettempdir(), "dictare-warmup.wav")
    with wave.open(_warm, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    _t0 = time.time()
    transcribe(_warm)
    os.unlink(_warm)
    log(f"warmup done in {time.time() - _t0:.1f}s")
except Exception as exc:  # warmup is best-effort
    log(f"warmup skipped: {exc}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "model": MODEL_NAME, "lang": LANGUAGE})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._send(400, {"error": "empty body"})
            return
        data = self.rfile.read(length)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            tmp.write(data)
            tmp.close()
            t0 = time.time()
            text, info = transcribe(tmp.name)
            elapsed = time.time() - t0
            log(f"{info.duration:.1f}s audio -> {elapsed:.1f}s ({len(text)} chars)")
            self._send(200, {"text": text, "audio": info.duration, "took": elapsed})
        except Exception as exc:
            log(f"error: {exc}")
            self._send(500, {"error": str(exc)})
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"listening on 127.0.0.1:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
