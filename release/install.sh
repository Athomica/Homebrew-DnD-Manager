#!/usr/bin/env bash
# DnD Manager v3 — installer script
# Run with:  bash install.sh
set -euo pipefail

REPO="athomica/homebrew-dnd-manager"
BRANCH="claude/optimistic-pascal-u4dyW"
BASE="https://raw.githubusercontent.com/$REPO/$BRANCH/release"

DEST="$HOME/DnDManager"

echo "============================================"
echo "  DnD Manager v3 — Installer"
echo "============================================"
echo ""
echo "Downloading part 1 of 2 (~57 MB) ..."
curl -L --progress-bar -o /tmp/_dndmgr.part1 "$BASE/DnDManager.part1"

echo "Downloading part 2 of 2 (~55 MB) ..."
curl -L --progress-bar -o /tmp/_dndmgr.part2 "$BASE/DnDManager.part2"

echo "Assembling ..."
cat /tmp/_dndmgr.part1 /tmp/_dndmgr.part2 > "$DEST"
chmod +x "$DEST"
rm -f /tmp/_dndmgr.part1 /tmp/_dndmgr.part2

echo ""
echo "Done!  Saved to: $DEST"
echo ""

# Optional: add to KDE application menu
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
echo "Added to KDE application menu."
echo ""
echo "Launching DnD Manager..."
"$DEST" &
