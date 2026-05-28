#!/usr/bin/env bash
# DnD Manager installer.
#
# Clones (or updates) the repo, checks out the requested branch,
# sets up a venv, installs PyQt6, and launches the app from source.
# Pass --build to also produce the single-file PyInstaller binary
# into ./dist/DnDManager.
#
# Usage:
#   ./install.sh                          # run from source, default branch
#   ./install.sh --branch <name>          # use a different branch
#   ./install.sh --build                  # build the single-file binary
#   ./install.sh --no-run                 # set up only, don't launch

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Athomica/Homebrew-DnD-Manager.git}"
BRANCH="${BRANCH:-claude/peaceful-heisenberg-ABLtK}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/dnd-manager}"
DO_BUILD=0
DO_RUN=1

while [ $# -gt 0 ]; do
    case "$1" in
        --branch)  BRANCH="$2"; shift 2 ;;
        --dir)     INSTALL_DIR="$2"; shift 2 ;;
        --build)   DO_BUILD=1; shift ;;
        --no-run)  DO_RUN=0; shift ;;
        -h|--help)
            sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need git
need python3

echo "==> Repo: $REPO_URL"
echo "==> Branch: $BRANCH"
echo "==> Install dir: $INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Updating existing checkout"
    git -C "$INSTALL_DIR" fetch --depth=1 origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
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

if [ "$DO_BUILD" = "1" ]; then
    echo "==> Installing PyInstaller and building binary"
    pip install --quiet 'pyinstaller>=6.0'
    ( cd build && ./build.sh )
    echo "==> Built: $INSTALL_DIR/dist/DnDManager"
fi

VERSION=$(grep -oP 'v3\.[0-9]+\.[0-9]+' src/ui/main_window.py | head -1)
echo "==> Installed version: $VERSION"

if [ "$DO_RUN" = "1" ]; then
    if [ "$DO_BUILD" = "1" ] && [ -x "$INSTALL_DIR/dist/DnDManager" ]; then
        echo "==> Launching binary"
        exec "$INSTALL_DIR/dist/DnDManager"
    else
        echo "==> Launching from source"
        cd "$INSTALL_DIR/src" && exec python main.py
    fi
fi
