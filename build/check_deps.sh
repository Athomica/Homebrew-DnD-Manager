#!/usr/bin/env bash
set -euo pipefail

# v3.10.19: ldconfig lives in /usr/sbin (or /sbin) on most distros and
# isn't on the default PATH when this script is invoked through a
# curl-piped installer or a minimal shell. Augment PATH so the lookup
# below can actually find the libraries — previously a missing
# ldconfig produced empty output, which made every lib look "missing"
# and printed a confusing "install everything" message even when the
# libraries were present.
export PATH="/usr/sbin:/sbin:$PATH"

REQUIRED_LIBS=(
    "libwayland-client.so.0"
    "libxcb.so.1"
    "libxkbcommon.so.0"
    "libxcb-cursor.so.0"
)

# Standard library search paths to fall back to if ldconfig isn't
# available at all (some minimal containers strip glibc tools).
FALLBACK_LIBDIRS=(
    /usr/lib /usr/lib64 /lib /lib64
    /usr/lib/x86_64-linux-gnu
    /usr/lib/aarch64-linux-gnu
)

have_lib() {
    local lib="$1"
    if command -v ldconfig >/dev/null 2>&1; then
        if ldconfig -p 2>/dev/null | grep -q "$lib"; then
            return 0
        fi
    fi
    # Fallback: probe well-known library directories directly. This
    # catches systems where ldconfig is missing or its cache is stale.
    local d
    for d in "${FALLBACK_LIBDIRS[@]}"; do
        if [ -e "$d/$lib" ]; then
            return 0
        fi
    done
    return 1
}

MISSING=()
for lib in "${REQUIRED_LIBS[@]}"; do
    have_lib "$lib" || MISSING+=("$lib")
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
