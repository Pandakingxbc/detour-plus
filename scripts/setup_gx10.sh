#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Detour — GX10 / DGX Spark Setup Script
#
# Sets up NVIDIA Nemotron on the GX10 (Grace Blackwell, 128GB unified mem)
# for the Detour agentic collision avoidance system.
#
# Usage:
#   chmod +x scripts/setup_gx10.sh
#   ./scripts/setup_gx10.sh [--model MODEL] [--port PORT]
#
# This script:
#   1. Installs vLLM (if needed)
#   2. Downloads the Nemotron model
#   3. Starts vLLM with tool-calling support
#   4. Verifies the endpoint is working
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────
MODEL="${1:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
PORT="${2:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
GPU_MEM="${GPU_MEM:-0.92}"

echo "═══════════════════════════════════════════════════════════════"
echo "  Detour — GX10 Nemotron Setup"
echo "  Model:  ${MODEL}"
echo "  Port:   ${PORT}"
echo "  Max Context: ${MAX_MODEL_LEN}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Check GPU ────────────────────────────────────────────────────
echo ""
echo "[1/4] Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "  ⚠ nvidia-smi not found. Are NVIDIA drivers installed?"
    echo "  On GX10: drivers should be preinstalled."
fi

# ── Step 2: Install vLLM ─────────────────────────────────────────────────
echo ""
echo "[2/4] Checking vLLM installation..."
if ! python3 -c "import vllm" 2>/dev/null; then
    echo "  Installing vLLM..."
    pip install vllm --upgrade
else
    VLLM_VER=$(python3 -c "import vllm; print(vllm.__version__)")
    echo "  vLLM ${VLLM_VER} already installed ✓"
fi

# ── Step 3: Download model (if not cached) ────────────────────────────────
echo ""
echo "[3/4] Preparing model ${MODEL}..."
echo "  (This will download on first run — ~60GB for Nano-30B BF16)"
echo "  Model will be cached in ~/.cache/huggingface/"

# Check if we need to login to HuggingFace
if ! python3 -c "from huggingface_hub import HfApi; HfApi().whoami()" 2>/dev/null; then
    echo ""
    echo "  ⚠ You may need to accept the model license and login:"
    echo "    pip install huggingface-hub"
    echo "    huggingface-cli login"
    echo ""
fi

# ── Step 4: Start vLLM ───────────────────────────────────────────────────
echo ""
echo "[4/4] Starting vLLM server..."
echo ""
echo "  Command:"
echo "    vllm serve ${MODEL} \\"
echo "        --trust-remote-code \\"
echo "        --max-model-len ${MAX_MODEL_LEN} \\"
echo "        --gpu-memory-utilization ${GPU_MEM} \\"
echo "        --dtype auto \\"
echo "        --enable-auto-tool-choice \\"
echo "        --tool-call-parser hermes \\"
echo "        --port ${PORT}"
echo ""

# Start vLLM in the background
vllm serve "${MODEL}" \
    --trust-remote-code \
    --max-model-len "${MAX_MODEL_LEN}" \
    --gpu-memory-utilization "${GPU_MEM}" \
    --dtype auto \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --port "${PORT}" &

VLLM_PID=$!
echo "  vLLM PID: ${VLLM_PID}"

# Wait for server to be ready
echo "  Waiting for server to be ready..."
for i in $(seq 1 120); do
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
        echo "═══════════════════════════════════════════════════════════════"
        wait $VLLM_PID
        exit 0
    fi
    sleep 2
    printf "."
done

echo ""
echo "  ⚠ Server did not become ready within 4 minutes."
echo "  Check logs above for errors."
echo "  Common issues:"
echo "    - Model not downloaded yet (large download)"
echo "    - Not enough GPU memory (try smaller model or reduce --max-model-len)"
echo "    - Missing --trust-remote-code"
wait $VLLM_PID
