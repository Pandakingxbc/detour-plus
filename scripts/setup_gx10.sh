#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Detour — GX10 / DGX Spark Setup Script
#
# Runs NVIDIA Nemotron on the GX10 (Grace Blackwell, 128GB unified mem)
# for the Detour agentic collision avoidance system.
#
# Usage:
#   chmod +x scripts/setup_gx10.sh
#   ./scripts/setup_gx10.sh                    # bare-metal (pip) — default
#   ./scripts/setup_gx10.sh --docker           # NGC container mode
#   MODEL=... PORT=... ./scripts/setup_gx10.sh # override model/port
#
# Bare-metal mode (default):
#   Installs vLLM via pip and runs vllm serve directly.
#   Works with any driver version (no container compat issues).
#
# Docker mode (--docker):
#   Uses NGC vLLM container. Requires driver >= 590.48 for 26.01 tag.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Parse args ───────────────────────────────────────────────────────────
USE_DOCKER=false
for arg in "$@"; do
    case $arg in
        --docker) USE_DOCKER=true ;;
    esac
done

# ── Configuration ────────────────────────────────────────────────────────
# NOTE: NVFP4 variant has a bug in vLLM <=0.13.0 (NGC 26.01):
#   "Non-gated activations are only supported by the flashinfer CUTLASS backend"
#   The Nemotron-H shared-expert MoE layers crash during profile_run().
#   Use BF16 instead — at ~60GB it fits in 128GB unified memory with 4K context.
MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
PORT="${PORT:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEM="${GPU_MEM:-0.85}"
NGC_IMAGE="nvcr.io/nvidia/vllm:26.01-py3"
CONTAINER_NAME="detour-vllm"
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"

MODE_LABEL="bare-metal (pip)"
if $USE_DOCKER; then MODE_LABEL="NGC Docker container"; fi

echo "═══════════════════════════════════════════════════════════════"
echo "  Detour — GX10 Nemotron Setup"
echo "  Mode:      ${MODE_LABEL}"
echo "  Model:     ${MODEL}"
echo "  Port:      ${PORT}"
echo "  Max Context: ${MAX_MODEL_LEN}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Check GPU ────────────────────────────────────────────────────
echo ""
echo "[1/4] Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "  ⚠ nvidia-smi not found. Are NVIDIA drivers installed?"
    exit 1
fi

# ── Step 2: Clear memory cache (DGX Spark OOM workaround) ────────────────
echo ""
echo "[2/4] Clearing memory cache (DGX Spark OOM prevention)..."
if [[ $EUID -eq 0 ]]; then
    sync && echo 3 > /proc/sys/vm/drop_caches
    echo "  Cache cleared ✓"
else
    sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null \
        && echo "  Cache cleared ✓" \
        || echo "  ⚠ Could not clear cache (not root). May hit OOM on large models."
fi

# ── Step 3: Install / prepare vLLM ───────────────────────────────────────
echo ""
echo "[3/4] Preparing vLLM..."

if $USE_DOCKER; then
    # ── Docker mode ──────────────────────────────────────────────────────
    echo "  Pulling NGC container: ${NGC_IMAGE}"
    docker pull "${NGC_IMAGE}"

    # Stop existing container
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    echo ""
    echo "[4/4] Starting vLLM in NGC container..."
    docker run --gpus all \
        -d \
        --ipc=host \
        --ulimit memlock=-1 \
        --ulimit stack=67108864 \
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
            --enforce-eager \
            --enable-auto-tool-choice \
            --tool-call-parser hermes \
            --enable-chunked-prefill

    echo "  Container started: ${CONTAINER_NAME}"
    echo "  Logs: docker logs -f ${CONTAINER_NAME}"
else
    # ── Bare-metal mode ──────────────────────────────────────────────────
    VENV_DIR="${VENV_DIR:-$HOME/.venv-vllm}"

    if [[ ! -d "${VENV_DIR}" ]]; then
        echo "  Creating venv at ${VENV_DIR} (with system-site-packages for CUDA)..."
        python3 -m venv --system-site-packages "${VENV_DIR}"
    fi

    # Activate venv for this session
    source "${VENV_DIR}/bin/activate"
    echo "  Using venv: ${VENV_DIR}"

    if ! python3 -c "import vllm" 2>/dev/null; then
        echo "  Installing vLLM via pip (in venv)..."
        pip install --upgrade pip
        pip install vllm
    else
        VLLM_VER=$(python3 -c "import vllm; print(vllm.__version__)")
        echo "  vLLM ${VLLM_VER} already installed ✓"
    fi

    echo ""
    echo "[4/4] Starting vLLM server (bare-metal)..."
    echo ""
    echo "  vllm serve ${MODEL} \\"
    echo "      --trust-remote-code \\"
    echo "      --max-model-len ${MAX_MODEL_LEN} \\"
    echo "      --gpu-memory-utilization ${GPU_MEM} \\"
    echo "      --dtype auto \\"
    echo "      --enforce-eager \\"
    echo "      --enable-auto-tool-choice \\"
    echo "      --tool-call-parser hermes \\"
    echo "      --enable-chunked-prefill \\"
    echo "      --port ${PORT}"
    echo ""

    vllm serve "${MODEL}" \
        --trust-remote-code \
        --max-model-len "${MAX_MODEL_LEN}" \
        --gpu-memory-utilization "${GPU_MEM}" \
        --dtype auto \
        --enforce-eager \
        --enable-auto-tool-choice \
        --tool-call-parser hermes \
        --enable-chunked-prefill \
        --port "${PORT}" &

    VLLM_PID=$!
    echo "  vLLM PID: ${VLLM_PID}"
fi

# ── Wait for server ──────────────────────────────────────────────────────
echo "  Waiting for server to be ready (first run downloads ~15GB model)..."
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
        if $USE_DOCKER; then
            echo ""
            echo "  Stop:  docker stop ${CONTAINER_NAME}"
            echo "  Logs:  docker logs -f ${CONTAINER_NAME}"
        fi
        echo "═══════════════════════════════════════════════════════════════"
        if ! $USE_DOCKER; then wait $VLLM_PID; fi
        exit 0
    fi
    sleep 2
    printf "."
done

echo ""
echo "  ⚠ Server did not become ready within 10 minutes."
if $USE_DOCKER; then
    echo "  Check container logs: docker logs ${CONTAINER_NAME}"
fi
echo "  Common issues:"
echo "    - Model still downloading (first run is ~15GB)"
echo "    - OOM: try 'sudo sync && echo 3 > /proc/sys/vm/drop_caches' then retry"
echo "    - Reduce context: MAX_MODEL_LEN=4096 ./scripts/setup_gx10.sh"
if ! $USE_DOCKER; then wait $VLLM_PID 2>/dev/null; fi
