#!/usr/bin/env bash
# Start TTS relay service on Jetson.
# Usage: bash run_tts_relay.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -u "$SCRIPT_DIR/tts_relay_server.py"
