#!/usr/bin/env bash
# DnD Manager — installer script
#
# Downloads the two halves of the application binary from the repo, joins them,
# verifies the SHA-256 matches what was committed, makes it executable,
# registers a KDE menu entry, and launches it.
#
# Run with:
#   bash install.sh
#
# Override the branch (for testing a feature branch) with:
#   BRANCH=some/other-branch bash install.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO="Athomica/Homebrew-DnD-Manager"
BRANCH="${BRANCH:-claude/peaceful-heisenberg-ABLtK}"
BASE="https://raw.githubusercontent.com/$REPO/$BRANCH/release"

# Expected SHA-256 of the assembled binary. Updated every time the binary is
# rebuilt; if the parts on disk don't match, the installer aborts loudly
# instead of silently installing a stale build.
EXPECTED_SHA256="811b5db473a6dfc7dd5d374671e1a5162162302b21f0a231e9e8bc65c600de17"

DEST="$HOME/DnDManager"
TMP1="$(mktemp -t dndmgr.part1.XXXXXX)"
TMP2="$(mktemp -t dndmgr.part2.XXXXXX)"
TMP_OUT="$(mktemp -t dndmgr.bin.XXXXXX)"
trap 'rm -f "$TMP1" "$TMP2" "$TMP_OUT"' EXIT

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
say "  DnD Manager — Installer"
say "  branch: $BRANCH"
say "============================================"
say ""
require_cmd curl
require_cmd sha256sum

# Test that the repo is reachable
say "Checking repository access..."
HTTP_CODE=$(curl -L -s -o /dev/null -w '%{http_code}' "$BASE/install.sh" || echo "000")
if [ "$HTTP_CODE" = "404" ]; then
    die "Cannot reach $BASE/install.sh (HTTP 404).
The branch '$BRANCH' may not exist, or the repo may be private.
Override the branch with:  BRANCH=some/other-branch bash install.sh"
elif [ "$HTTP_CODE" != "200" ]; then
    die "Unexpected HTTP $HTTP_CODE while reaching $BASE/install.sh"
fi

# Cache-buster query string keeps GitHub's raw CDN from handing us a stale copy.
CB="?cb=$(date +%s)"

say "Downloading part 1 of 2 (~56 MB)..."
curl -L --fail --progress-bar -o "$TMP1" "$BASE/DnDManager.part1$CB"

say "Downloading part 2 of 2 (~56 MB)..."
curl -L --fail --progress-bar -o "$TMP2" "$BASE/DnDManager.part2$CB"

# Sanity check: both files should be binary (not the GitHub 404 HTML page)
if head -c 16 "$TMP1" | grep -aq 'html\|404\|<!DO'; then
    die "Downloaded part 1 looks like an HTML error page, not the binary."
fi
if head -c 16 "$TMP2" | grep -aq 'html\|404\|<!DO'; then
    die "Downloaded part 2 looks like an HTML error page, not the binary."
fi

say "Assembling the executable..."
cat "$TMP1" "$TMP2" > "$TMP_OUT"

say "Verifying SHA-256..."
ACTUAL_SHA256=$(sha256sum "$TMP_OUT" | awk '{print $1}')
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    die "Checksum mismatch!
  expected: $EXPECTED_SHA256
  got:      $ACTUAL_SHA256
The downloaded parts are stale or corrupted. Try again in a minute
(GitHub's raw CDN can cache for ~5 minutes after a push)."
fi
say "  OK ($ACTUAL_SHA256)"

mv "$TMP_OUT" "$DEST"
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
