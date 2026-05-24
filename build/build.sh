#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Step 1: check dependencies
./check_deps.sh

# Step 2: clean previous build
rm -rf ../build_output ../dist
mkdir -p ../build_output

# Step 3: run PyInstaller
echo "Building DnDManager..."
pyinstaller build.spec \
    --clean \
    --noconfirm \
    --distpath ../dist \
    --workpath ../build_output

# Step 4: sanity check the result
EXE="../dist/DnDManager"
if [ ! -x "$EXE" ]; then
    echo "FAIL: Build did not produce executable at $EXE"
    exit 1
fi

# Step 5: verify size
size=$(stat -c '%s' "$EXE")
if [ "$size" -lt 30000000 ]; then
    echo "WARNING: Executable seems small ($size bytes). Verify plugins were bundled."
else
    echo "OK: Executable size $size bytes"
fi

echo ""
echo "Build complete: $EXE"
echo "Test with:"
echo "  $EXE                       # default (auto-detect wayland/xcb)"
echo "  QT_QPA_PLATFORM=xcb $EXE   # force X11 mode"
echo "  QT_DEBUG_PLUGINS=1 $EXE    # debug plugin loading"
