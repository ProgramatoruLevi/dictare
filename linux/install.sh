#!/usr/bin/env bash
# Install the dictation stack on Linux (Wayland/GNOME, PipeWire).
set -euo pipefail

BASE="$HOME/.local/share/dictare"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "==> laying out $BASE"
mkdir -p "$BASE/transcripts" "$BIN" "$UNITS"
cp "$SRC/whisperd.py" "$SRC/pttd.py" "$BASE/"
[ -f "$BASE/vocab.txt" ] || cp "$SRC/vocab.txt" "$BASE/vocab.txt"
install -m 755 "$SRC/dictare" "$BIN/dictare"
cp "$SRC/dictare.service" "$SRC/dictare-ptt.service" "$UNITS/"

echo "==> system packages (needs sudo)"
# wl-clipboard owns the Wayland selection; ydotool injects the paste keystroke.
sudo apt-get update -qq
sudo apt-get install -y wl-clipboard ydotool jq

echo "==> /dev/uinput access for ydotool"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/60-uinput-dictare.rules >/dev/null
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG input "$USER"

echo "==> uv + isolated Python 3.12"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv venv --python 3.12 "$BASE/venv"

echo "==> faster-whisper"
uv pip install --python "$BASE/venv/bin/python" faster-whisper

echo "==> downloading large-v3-turbo (~1.6 GB, one time)"
"$BASE/venv/bin/python" - <<'PY'
from faster_whisper import WhisperModel
WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
print("model ready")
PY

echo "==> services"
systemctl --user daemon-reload
systemctl --user enable --now dictare.service
systemctl --user enable dictare-ptt.service
systemctl --user enable --now ydotool.service 2>/dev/null || true

cat <<'EOF'

DONE — one thing left: log out and back in.

The 'input' group only applies to a fresh session, and both the push-to-talk
daemon (reads /dev/input) and ydotoold (writes /dev/uinput) need it.

After logging back in:
  dictare selftest       # checks every component, then tests the paste
  hold Right Ctrl, speak, release
EOF
