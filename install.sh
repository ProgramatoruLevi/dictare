#!/usr/bin/env bash
# Bootstrap installer — safe to pipe from curl:
#   curl -LsSf https://raw.githubusercontent.com/ProgramatoruLevi/dictare/main/install.sh | bash
#
# Detects the OS, fetches the repo, and hands off to the platform installer.
# Set DICTARE_DRY_RUN=1 to fetch and report without installing anything.
set -euo pipefail

REPO="${DICTARE_REPO:-ProgramatoruLevi/dictare}"
REF="${DICTARE_REF:-main}"

case "$(uname -s)" in
  Linux)  PLATFORM=linux ;;
  Darwin) PLATFORM=macos ;;
  *) echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac
echo "==> platform: $PLATFORM"

# When piped from curl there is no repo on disk, so always fetch a fresh copy.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "==> fetching $REPO@$REF"
curl -LsSf "https://codeload.github.com/$REPO/tar.gz/$REF" | tar xzf - -C "$WORK"
ROOT="$(find "$WORK" -maxdepth 1 -type d -name 'dictare-*' | head -1)"
[ -d "$ROOT/$PLATFORM" ] || { echo "missing $PLATFORM/ in the fetched repo" >&2; exit 1; }

if [ "${DICTARE_DRY_RUN:-0}" = "1" ]; then
  echo "==> dry run — would execute $PLATFORM/install.sh"
  ls -1 "$ROOT/$PLATFORM"
  exit 0
fi

exec bash "$ROOT/$PLATFORM/install.sh"
