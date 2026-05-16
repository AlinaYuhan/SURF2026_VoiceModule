#!/usr/bin/env bash
# Launch voice_pipeline_node in WSL2 with all required env vars.
# Usage: bash run_node.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source /opt/ros/jazzy/setup.bash

export VOICE_ASR_MODEL=$HOME/.cache/modelscope/hub/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
export HF_HUB_OFFLINE=1
export ROS_DOMAIN_ID=42
export PYTHONPATH="$SCRIPT_DIR:/opt/ros/jazzy/lib/python3.12/site-packages"
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><AllowMulticast>false</AllowMulticast></General><Discovery><Peers><Peer address="192.168.123.164"/></Peers></Discovery></Domain></CycloneDDS>'
export VOICE_AUDIO_SOURCE=robot

cd "$SCRIPT_DIR"
python ros_nodes/voice_pipeline_node.py
