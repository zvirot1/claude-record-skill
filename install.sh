#!/usr/bin/env bash
# macOS / Linux installer: copies skills/* into ~/.claude/skills and installs Python deps.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
mkdir -p "$root"
for d in "$here"/skills/*/; do
  name="$(basename "$d")"
  rm -rf "$root/$name"
  cp -R "$d" "$root/$name"
  find "$root/$name" -name __pycache__ -type d -prune -exec rm -rf {} +
  echo "[install] $name -> $root/$name"
done
py="$(command -v python3 || command -v python || true)"
[ -n "$py" ] || { echo "[install] Python 3 not found (macOS: brew install python)"; exit 1; }
"$py" -m pip install --user --quiet mss pynput pillow 2>/dev/null \
  || "$py" -m pip install --user --quiet --break-system-packages mss pynput pillow
"$py" "$root/record-skill/scripts/save_skill.py" --list
echo
echo "[install] done. Tests:"
echo "  $py $root/record-skill/scripts/record.py --no-input --duration 5"
echo "  $py $root/record-skill/scripts/record.py --duration 30    # stop with Ctrl+Shift+Q"
echo "macOS: grant Screen Recording + Accessibility to your terminal app first."
