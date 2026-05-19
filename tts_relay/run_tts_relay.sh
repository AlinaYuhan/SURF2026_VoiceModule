#!/usr/bin/env bash
# Start TTS relay service on Jetson.
# Usage: bash run_tts_relay.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UNITREE_DDC="/home/unitree/unitree_sdk2-main/thirdparty/lib/aarch64"
CYCLONE_WS="/home/unitree/cyclonedds_ws/install/cyclonedds/lib"

# Pick whichever libddsc exports the symbol the pip _clayer.so needs.
LIBDDSC_PATH=""
for candidate in "$UNITREE_DDC" "$CYCLONE_WS"; do
    if nm -D "$candidate/libddsc.so" 2>/dev/null | grep -q "ddsi_sertype_v0"; then
        LIBDDSC_PATH="$candidate"
        echo "[relay] 使用 libddsc: $LIBDDSC_PATH"
        break
    fi
done

if [ -z "$LIBDDSC_PATH" ]; then
    echo "[relay] 警告: 两个候选 libddsc.so 都没有 ddsi_sertype_v0，直接尝试运行..."
else
    export LD_LIBRARY_PATH="$LIBDDSC_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

python3 -u "$SCRIPT_DIR/tts_relay_server.py"
