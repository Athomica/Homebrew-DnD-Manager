#!/usr/bin/env bash
# DnD Manager installer.
#
# Default (no flags): pull the latest source, set up a venv, build the
# single-file binary, install a clickable .desktop entry into the KDE /
# GNOME app menu (where it can be pinned to the taskbar), then launch.
#
# Re-run any time to update — the script is idempotent and detects an
# existing checkout/venv/binary and refreshes them in place.
#
# Usage:
#   ./install.sh                      # full install: pull + build + desktop entry + run
#   ./install.sh --no-build           # skip binary; run from source via the venv
#   ./install.sh --no-desktop         # skip the .desktop entry
#   ./install.sh --no-run             # set up but don't launch
#   ./install.sh --branch <name>      # use a different branch
#   ./install.sh --dir <path>         # install to a non-default location
#   ./install.sh --uninstall          # remove the .desktop entry (leaves files)

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Athomica/Homebrew-DnD-Manager.git}"
BRANCH="${BRANCH:-claude/peaceful-heisenberg-ABLtK}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/dnd-manager}"
DO_BUILD=1
DO_DESKTOP=1
DO_RUN=1
DO_UNINSTALL=0

DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/dnd-manager.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
ICON_FILE="$ICON_DIR/dnd-manager.png"

while [ $# -gt 0 ]; do
    case "$1" in
        --branch)      BRANCH="$2"; shift 2 ;;
        --dir)         INSTALL_DIR="$2"; shift 2 ;;
        --no-build)    DO_BUILD=0; shift ;;
        --no-desktop)  DO_DESKTOP=0; shift ;;
        --no-run)      DO_RUN=0; shift ;;
        --uninstall)   DO_UNINSTALL=1; shift ;;
        -h|--help)     sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [ "$DO_UNINSTALL" = "1" ]; then
    rm -f "$DESKTOP_FILE" "$ICON_FILE"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    echo "==> Removed desktop entry. Files in $INSTALL_DIR untouched."
    exit 0
fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need git
need python3

echo "==> Repo: $REPO_URL"
echo "==> Branch: $BRANCH"
echo "==> Install dir: $INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Updating existing checkout"
    git -C "$INSTALL_DIR" fetch --depth=1 origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
    echo "==> Cloning fresh"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

VENV="$INSTALL_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "==> Creating venv"
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
echo "==> Installing PyQt6"
pip install --quiet pyqt6

BINARY="$INSTALL_DIR/dist/DnDManager"

if [ "$DO_BUILD" = "1" ]; then
    echo "==> Installing PyInstaller and building binary (this takes a minute)"
    pip install --quiet 'pyinstaller>=6.0'
    ( cd build && ./build.sh )
    if [ ! -x "$BINARY" ]; then
        echo "==> Build failed: no executable at $BINARY" >&2
        exit 1
    fi
    echo "==> Built: $BINARY"
fi

# Choose what the desktop entry / direct launch should run.
# Prefer the binary if it exists; otherwise fall back to running from
# source via the venv. Both paths are absolute so the desktop entry
# works regardless of $PATH.
if [ -x "$BINARY" ]; then
    LAUNCH_CMD="$BINARY"
else
    LAUNCH_CMD="$VENV/bin/python $INSTALL_DIR/src/main.py"
fi

if [ "$DO_DESKTOP" = "1" ]; then
    echo "==> Installing desktop entry at $DESKTOP_FILE"
    mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
    # The bundled fallback icon is a generic "applications-games"
    # symbolic icon — written only if no custom PNG ships with the
    # repo. Skipping the PNG is fine; Icon=applications-games in the
    # desktop entry resolves against the system theme.
    if [ -f "$INSTALL_DIR/build/icon.png" ]; then
        cp -f "$INSTALL_DIR/build/icon.png" "$ICON_FILE"
        ICON_VALUE="dnd-manager"
    else
        ICON_VALUE="applications-games"
    fi
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=DnD Manager
GenericName=Tabletop Campaign Tracker
Comment=Manage characters, encounters, and combat for a homebrew tabletop RPG
Exec=$LAUNCH_CMD
Icon=$ICON_VALUE
Terminal=false
Categories=Game;RolePlaying;
StartupNotify=true
StartupWMClass=DnDManager
EOF
    chmod +x "$DESKTOP_FILE"
    # Refresh the menu index so KDE / GNOME pick up the new entry
    # without a logout. Silent if the tool isn't installed.
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    echo "==> Look for 'DnD Manager' in your app launcher."
    echo "    Right-click the entry there to pin it to the taskbar."
fi

VERSION=$(grep -oP 'v3\.[0-9]+\.[0-9]+' src/ui/main_window.py | head -1)
echo "==> Installed version: $VERSION"

if [ "$DO_RUN" = "1" ]; then
    echo "==> Launching"
    exec $LAUNCH_CMD
fi
