#!/usr/bin/env bash
# Install the dictation stack on macOS. Run from inside this folder:
#   bash install.sh
set -euo pipefail

BASE="$HOME/.local/share/dictare"
BIN="$HOME/.local/bin"
SRC="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"

echo "==> laying out $BASE"
mkdir -p "$BASE" "$BIN" "$AGENTS" "$BASE/transcripts"
cp "$SRC/whisperd.py" "$SRC/recorder.py" "$SRC/pttd_mac.py" "$BASE/"
[ -f "$BASE/vocab.txt" ] || cp "$SRC/vocab.txt" "$BASE/vocab.txt"
cp "$SRC/dictare" "$BIN/dictare"
chmod +x "$BIN/dictare"

echo "==> uv (isolated Python toolchain, no Homebrew needed)"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Python 3.12 + venv"
uv python install 3.12
uv venv --python 3.12 "$BASE/venv"

echo "==> dependencies (faster-whisper, sounddevice, pynput)"
uv pip install --python "$BASE/venv/bin/python" faster-whisper sounddevice pynput

echo "==> downloading large-v3-turbo (~1.6 GB, one time)"
"$BASE/venv/bin/python" - <<'PY'
from faster_whisper import WhisperModel
WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
print("model ready")
PY

echo "==> launchd agents"
for plist in com.levi.dictare com.levi.dictare-ptt; do
  sed "s|__HOME__|$HOME|g" "$SRC/$plist.plist" > "$AGENTS/$plist.plist"
  launchctl unload "$AGENTS/$plist.plist" 2>/dev/null || true
  launchctl load  "$AGENTS/$plist.plist"
done

cat <<EOF

DONE — but macOS will not let the hotkey work until you grant permissions.

Open System Settings > Privacy & Security and add the app that runs the agents
(usually /bin/bash, or Terminal if you launch by hand) to BOTH:

  * Input Monitoring   — so the Right Command key can be observed
  * Accessibility      — so Cmd+V can be injected after transcription

Also grant Microphone access the first time you record.

Then check it:   dictare selftest
And use it:      hold Right Command, speak, release.
EOF
