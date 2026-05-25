#!/usr/bin/env bash
# DnD Manager v3.1 — installer script
#
# This script downloads the two halves of the application binary from your
# GitHub repository, joins them, makes the result executable, registers a
# KDE menu entry, and launches the app.
#
# Run with:
#   bash install.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO="athomica/homebrew-dnd-manager"
BRANCH="claude/optimistic-pascal-u4dyW"
BASE="https://raw.githubusercontent.com/$REPO/$BRANCH/release"

DEST="$HOME/DnDManager"
TMP1="$(mktemp -t dndmgr.part1.XXXXXX)"
TMP2="$(mktemp -t dndmgr.part2.XXXXXX)"
trap 'rm -f "$TMP1" "$TMP2"' EXIT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
say() { printf '%s\n' "$1"; }
die() { printf '\n[ERROR] %s\n' "$1" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command '$1' not found in PATH."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
say "============================================"
say "  DnD Manager v3.1 — Installer"
say "============================================"
say ""
require_cmd curl

# Test that the repo is reachable
say "Checking repository access..."
HTTP_CODE=$(curl -L -s -o /dev/null -w '%{http_code}' "$BASE/install.sh" || echo "000")
if [ "$HTTP_CODE" = "404" ]; then
    die "Cannot reach $BASE/install.sh (HTTP 404).
The repository may be private. Make it public on GitHub:
  Settings → scroll to the bottom → 'Change repository visibility' → Public
Then re-run this script."
elif [ "$HTTP_CODE" != "200" ]; then
    die "Unexpected HTTP $HTTP_CODE while reaching the repository."
fi

say "Downloading part 1 of 2 (about 60 MB)..."
curl -L --fail --progress-bar -o "$TMP1" "$BASE/DnDManager.part1"

say "Downloading part 2 of 2 (about 52 MB)..."
curl -L --fail --progress-bar -o "$TMP2" "$BASE/DnDManager.part2"

# Sanity check: both files should be binary (not the GitHub 404 HTML page)
if head -c 4 "$TMP1" | grep -aq 'html\|404\|<!DO'; then
    die "Downloaded part 1 looks like an HTML error page, not the binary."
fi
if head -c 4 "$TMP2" | grep -aq 'html\|404\|<!DO'; then
    die "Downloaded part 2 looks like an HTML error page, not the binary."
fi

say "Assembling the executable..."
cat "$TMP1" "$TMP2" > "$DEST"
chmod +x "$DEST"
say "Saved to: $DEST"

# Register a KDE menu entry (.desktop file)
DESKTOP_FILE="$HOME/.local/share/applications/dnd-manager.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=DnD Manager
Comment=Tabletop campaign tracker
Exec=$DEST
Icon=applications-games
Type=Application
Categories=Game;
EOF
say "Added 'DnD Manager' to your KDE application menu."

say ""
say "Done!  Launching DnD Manager..."
say ""
say "From now on, you can either:"
say "  - Find 'DnD Manager' in your KDE start menu, or"
say "  - Run: $DEST"
say ""
say "If the Wayland window doesn't open, try forcing X11 mode:"
say "  QT_QPA_PLATFORM=xcb $DEST"
say ""

"$DEST" &
disown
