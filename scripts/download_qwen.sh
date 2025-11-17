#!/bin/bash
# Script to download Qwen3-4B-Instruct model
# Usage: ./download_qwen.sh [huggingface_token]

set -e

MODEL_DIR="/root/MithrilLog/models"
MODEL_FILE="Qwen3-4B-Instruct-Q4_K_M.gguf"
REPO_ID="Qwen/Qwen3-4B-Instruct-GGUF"

cd "$MODEL_DIR"

if [ -f "$MODEL_FILE" ]; then
    size=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo "0")
    if [ "$size" -gt 2000000000 ]; then
        echo "Model already exists ($(echo "scale=1; $size/1024/1024/1024" | bc) GB)"
        exit 0
    fi
fi

if [ -n "$1" ]; then
    echo "Using provided Hugging Face token..."
    export HF_TOKEN="$1"
    docker compose exec -T orchestrator python3 -c "
from huggingface_hub import hf_hub_download
import os
os.chdir('/app/models')
try:
    print('Downloading Qwen3-4B-Instruct Q4_K_M model...')
    model_path = hf_hub_download(
        repo_id='$REPO_ID',
        filename='$MODEL_FILE',
        local_dir='.',
        token=os.environ.get('HF_TOKEN')
    )
    size = os.path.getsize('$MODEL_FILE') / 1024 / 1024
    print(f'Success! File size: {size:.1f} MB')
except Exception as e:
    print(f'Error: {e}')
    exit(1)
"
else
    echo "No token provided. Please:"
    echo "1. Get a token from https://huggingface.co/settings/tokens"
    echo "2. Run: ./download_qwen.sh YOUR_TOKEN"
    echo "Or download manually and place in: $MODEL_DIR/$MODEL_FILE"
fi

