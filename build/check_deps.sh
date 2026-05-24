#!/usr/bin/env bash
set -euo pipefail

REQUIRED_LIBS=(
    "libwayland-client.so.0"
    "libxcb.so.1"
    "libxkbcommon.so.0"
    "libxcb-cursor.so.0"
)

MISSING=()
for lib in "${REQUIRED_LIBS[@]}"; do
    if ! ldconfig -p | grep -q "$lib"; then
        MISSING+=("$lib")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "FAIL: Missing system libraries:"
    printf '  %s\n' "${MISSING[@]}"
    echo ""
    echo "On Arch / CachyOS:"
    echo "  sudo pacman -S wayland libxcb libxkbcommon xcb-util-cursor"
    echo ""
    echo "On Ubuntu / Debian:"
    echo "  sudo apt install libwayland-client0 libxcb1 libxkbcommon0 libxcb-cursor0"
    exit 1
fi

# Verify PyInstaller version
PYI_VER=$(pyinstaller --version 2>/dev/null || echo "0")
PYI_MAJOR=$(echo "$PYI_VER" | cut -d. -f1)
if [ "$PYI_MAJOR" -lt 6 ]; then
    echo "FAIL: PyInstaller $PYI_VER is too old. Need 6.0 or newer."
    echo "  pip install --upgrade pyinstaller"
    exit 1
fi

echo "OK: All dependencies present, PyInstaller $PYI_VER"
