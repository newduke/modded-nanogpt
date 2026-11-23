#!/usr/bin/env bash
# One-time setup on a RunPod pod with a network volume at /workspace.
# Safe to rerun: skips anything already done.
#   bash speedrun/bootstrap.sh            # full FineWeb10B (103 shards, ~21 GB)
#   bash speedrun/bootstrap.sh 10         # fewer shards (enough for recent records)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
DATA_DIR=${DATA_DIR:-/workspace/fineweb10B}
CHUNKS=${1:-103}

if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | sort | uniq -c
  nvidia-smi | grep -o "CUDA Version: [0-9.]*" || true
else
  echo "No GPU visible (fine for a data-prep pod)."
fi

command -v tmux >/dev/null || (apt-get update -qq && apt-get install -y -qq tmux) || true
python3 -m pip install -q --upgrade huggingface-hub

git -C "$REPO" remote get-url upstream >/dev/null 2>&1 \
  || git -C "$REPO" remote add upstream https://github.com/KellerJordan/modded-nanogpt.git

# Point the repo's download script at the shared data dir, then fetch shards.
mkdir -p "$DATA_DIR"
if [[ ! -L "$REPO/data/fineweb10B" ]]; then
  rm -rf "$REPO/data/fineweb10B"
  ln -s "$DATA_DIR" "$REPO/data/fineweb10B"
fi
echo "Downloading FineWeb10B val + $CHUNKS train shards to $DATA_DIR ..."
python3 "$REPO/data/cached_fineweb10B.py" "$CHUNKS"
du -sh "$DATA_DIR"
echo "Done. Next: python3 speedrun/speedrun.py list"
