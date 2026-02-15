#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Detour — GX10 / DGX Spark Setup Script
#
# Runs NVIDIA Nemotron on the GX10 (Grace Blackwell, 128GB unified mem)
# using the NGC vLLM Docker container for optimized inference.
#
# Usage:
#   chmod +x scripts/setup_gx10.sh
#   ./scripts/setup_gx10.sh [--model MODEL] [--port PORT]
#
# This script:
#   1. Checks GPU and Docker/NVIDIA Container Toolkit
#   2. Pulls the NGC vLLM container (if needed)
#   3. Clears memory cache (DGX Spark OOM workaround)
#   4. Starts vLLM with tool-calling support inside the container
#   5. Verifies the endpoint is working
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────
MODEL="${1:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
PORT="${2:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
GPU_MEM="${GPU_MEM:-0.92}"
NGC_IMAGE="nvcr.io/nvidia/vllm:26.01-py3"
CONTAINER_NAME="detour-vllm"
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"

echo "═══════════════════════════════════════════════════════════════"
echo "  Detour — GX10 Nemotron Setup (NGC Container)"
echo "  Model:     ${MODEL}"
echo "  Port:      ${PORT}"
echo "  Container: ${NGC_IMAGE}"
echo "  Max Context: ${MAX_MODEL_LEN}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Check GPU ────────────────────────────────────────────────────
echo ""
echo "[1/5] Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "  ⚠ nvidia-smi not found. Are NVIDIA drivers installed?"
    echo "  On GX10/DGX Spark: drivers should be preinstalled."
    exit 1
fi

# ── Step 2: Check Docker + NVIDIA Container Toolkit ──────────────────────
echo ""
echo "[2/5] Checking Docker..."
if ! command -v docker &>/dev/null; then
    echo "  ⚠ Docker not found. Install Docker Engine first:"
    echo "    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    exit 1
fi
docker --version
echo "  Checking NVIDIA Container Toolkit..."
if ! docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi &>/dev/null 2>&1; then
    echo "  ⚠ NVIDIA Container Toolkit not working. Install:"
    echo "    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    exit 1
fi
echo "  NVIDIA Container Toolkit ✓"

# ── Step 3: Pull NGC vLLM container ──────────────────────────────────────
echo ""
echo "[3/5] Pulling NGC vLLM container..."
echo "  Image: ${NGC_IMAGE} (~5.85 GB compressed)"
docker pull "${NGC_IMAGE}"

# ── Step 4: Clear memory cache (DGX Spark OOM workaround) ────────────────
echo ""
echo "[4/5] Clearing memory cache (DGX Spark OOM prevention)..."
if [[ $EUID -eq 0 ]]; then
    sync && echo 3 > /proc/sys/vm/drop_caches
    echo "  Cache cleared ✓"
else
    echo "  Attempting with sudo..."
    sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null && echo "  Cache cleared ✓" || echo "  ⚠ Could not clear cache (not root). Run with sudo if you hit OOM."
fi

# ── Step 5: Start vLLM in NGC container ──────────────────────────────────
echo ""
echo "[5/5] Starting vLLM server in NGC container..."
echo ""
echo "  docker run --gpus all \\"
echo "    -p ${PORT}:8000 \\"
echo "    -v ${HF_CACHE}:/root/.cache/huggingface \\"
echo "    --name ${CONTAINER_NAME} \\"
echo "    ${NGC_IMAGE} \\"
echo "    python3 -m vllm.entrypoints.openai.api_server \\"
echo "      --model ${MODEL} \\"
echo "      --trust-remote-code \\"
echo "      --max-model-len ${MAX_MODEL_LEN} \\"
echo "      --gpu-memory-utilization ${GPU_MEM} \\"
echo "      --dtype auto \\"
echo "      --enable-auto-tool-choice \\"
echo "      --tool-call-parser hermes"
echo ""

# Stop any existing container with same name
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

# Start the container
docker run --gpus all \
    -d \
    -p "${PORT}:8000" \
    -v "${HF_CACHE}:/root/.cache/huggingface" \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    "${NGC_IMAGE}" \
    python3 -m vllm.entrypoints.openai.api_server \
        --model "${MODEL}" \
        --trust-remote-code \
        --max-model-len "${MAX_MODEL_LEN}" \
        --gpu-memory-utilization "${GPU_MEM}" \
        --dtype auto \
        --enable-auto-tool-choice \
        --tool-call-parser hermes

echo "  Container started: ${CONTAINER_NAME}"
echo "  Logs: docker logs -f ${CONTAINER_NAME}"

# Wait for server to be ready
echo "  Waiting for server to be ready (first run downloads ~60GB model)..."
for i in $(seq 1 300); do
    if curl -s "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  ✓ vLLM is ready!"
        echo "  Endpoint: http://localhost:${PORT}/v1"
        echo ""
        echo "  Test with:"
        echo "    curl http://localhost:${PORT}/v1/chat/completions \\"
        echo "      -H 'Content-Type: application/json' \\"
        echo "      -d '{\"model\": \"${MODEL}\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}'"
        echo ""
        echo "  Set in .env:"
        echo "    NEMOTRON_BASE_URL=http://localhost:${PORT}/v1"
        echo ""
        echo "  Stop:  docker stop ${CONTAINER_NAME}"
        echo "  Logs:  docker logs -f ${CONTAINER_NAME}"
        echo "═══════════════════════════════════════════════════════════════"
        exit 0
    fi
    sleep 2
    printf "."
done

echo ""
echo "  ⚠ Server did not become ready within 10 minutes."
echo "  Check container logs: docker logs ${CONTAINER_NAME}"
echo "  Common issues:"
echo "    - Model still downloading (first run is ~60GB)"
echo "    - OOM: try 'sudo sync && echo 3 > /proc/sys/vm/drop_caches' then retry"
echo "    - Reduce --max-model-len or --gpu-memory-utilization"
