#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Detour — GX10 / DGX Spark Setup Script
#
# Serves NVIDIA Nemotron via vLLM on the GX10 (GB10, aarch64).
# Default mode uses the NGC Docker container (CUDA Forward Compat).
#
# Usage:
#   chmod +x scripts/setup_gx10.sh
#   ./scripts/setup_gx10.sh                    # Docker (default)
#   ./scripts/setup_gx10.sh --bare-metal       # pip venv mode
#   MODEL=... PORT=... ./scripts/setup_gx10.sh # override defaults
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Parse args ───────────────────────────────────────────────────────────
USE_DOCKER=true
for arg in "$@"; do
    case $arg in
        --bare-metal) USE_DOCKER=false ;;
    esac
done

# ── Configuration ────────────────────────────────────────────────────────
MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4}"
PORT="${PORT:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM="${GPU_MEM:-0.90}"
NGC_IMAGE="${NGC_IMAGE:-nvcr.io/nvidia/vllm:26.01-py3}"
CONTAINER_NAME="detour-vllm"
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"
VENV_DIR="${VENV_DIR:-$HOME/.venv-vllm}"

MODE_LABEL="Docker (NGC container)"
if ! $USE_DOCKER; then MODE_LABEL="bare-metal (pip)"; fi

echo "═══════════════════════════════════════════════════════════════"
echo "  Detour — GX10 Nemotron Setup"
echo "  Mode:        ${MODE_LABEL}"
echo "  Model:       ${MODEL}"
echo "  Port:        ${PORT}"
echo "  Max Context: ${MAX_MODEL_LEN}"
if $USE_DOCKER; then
echo "  Image:       ${NGC_IMAGE}"
else
echo "  Venv:        ${VENV_DIR}"
fi
echo "═══════════════════════════════════════════════════════════════"

# ── Step 0: Stop any leftover container ──────────────────────────────────
if command -v docker &>/dev/null; then
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null && echo "[0] Stopped leftover container" || true
fi

# ── Step 1: Check GPU ────────────────────────────────────────────────────
echo ""
echo "[1/4] Checking GPU..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "  ⚠ nvidia-smi not found. Are NVIDIA drivers installed?"
    exit 1
fi

# ── Step 2: Clear memory cache ───────────────────────────────────────────
echo ""
echo "[2/4] Clearing memory cache..."
if [[ $EUID -eq 0 ]]; then
    sync && echo 3 > /proc/sys/vm/drop_caches
    echo "  Cache cleared ✓"
else
    sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null \
        && echo "  Cache cleared ✓" \
        || echo "  ⚠ Could not clear cache (not root)."
fi

# ── Step 3 & 4: Prepare and launch vLLM ─────────────────────────────────
if $USE_DOCKER; then
    # ── Docker mode ──────────────────────────────────────────────────────
    echo ""
    echo "[3/4] Pulling NGC container (skips if cached)..."
    docker pull "${NGC_IMAGE}"

    echo ""
    echo "[4/4] Starting vLLM in Docker container..."
    echo ""
    echo "  docker run --gpus all ${NGC_IMAGE}"
    echo "    model: ${MODEL}"
    echo "    port:  ${PORT}"
    echo "    cache: ${HF_CACHE}"
    echo ""

    mkdir -p "${HF_CACHE}"

    docker run --gpus all \
        -d \
        --ipc=host \
        --ulimit memlock=-1 \
        --ulimit stack=67108864 \
        -p "${PORT}:8000" \
        -v "${HF_CACHE}:/root/.cache/huggingface" \
        -e HF_HOME=/root/.cache/huggingface \
        -e VLLM_USE_FLASHINFER_MOE_FP4=1 \
        -e VLLM_FLASHINFER_MOE_BACKEND=throughput \
        --name "${CONTAINER_NAME}" \
        --restart on-failure:3 \
        "${NGC_IMAGE}" \
        python3 -m vllm.entrypoints.openai.api_server \
            --model "${MODEL}" \
            --trust-remote-code \
            --max-model-len "${MAX_MODEL_LEN}" \
            --gpu-memory-utilization "${GPU_MEM}" \
            --dtype auto \
            --kv-cache-dtype fp8 \
            --enable-auto-tool-choice \
            --tool-call-parser qwen3_coder \
            --enable-chunked-prefill \
            --port 8000

    echo "  Container started: ${CONTAINER_NAME}"
    echo "  Logs: docker logs -f ${CONTAINER_NAME}"
else
    # ── Bare-metal mode ──────────────────────────────────────────────────
    echo ""
    echo "[3/4] Preparing vLLM (bare-metal)..."

    if [[ ! -d "${VENV_DIR}" ]]; then
        echo "  Creating venv at ${VENV_DIR} (with system-site-packages for CUDA)..."
        python3 -m venv --system-site-packages "${VENV_DIR}"
    fi

    source "${VENV_DIR}/bin/activate"
    echo "  Activated venv: ${VENV_DIR}"

    if ! python3 -c "import vllm" 2>/dev/null; then
        echo "  Installing vLLM + flashinfer..."
        pip install --upgrade pip
        pip install flashinfer -i https://flashinfer.ai/whl/cu124/torch2.6/ 2>/dev/null \
            || pip install flashinfer 2>/dev/null \
            || echo "  ⚠ flashinfer not available for this platform — vLLM will use fallback kernels"
        pip install vllm
    else
        VLLM_VER=$(python3 -c "import vllm; print(vllm.__version__)")
        echo "  vLLM ${VLLM_VER} already installed ✓"
    fi

    # Find CUDA libraries for bare-metal
    echo ""
    echo "[*] Locating CUDA libraries..."
    CUDA_FOUND=false
    SITE_PKGS=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "")

    TORCH_LIB=$(python3 -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))" 2>/dev/null || echo "")
    if [[ -n "${TORCH_LIB}" ]] && [[ -d "${TORCH_LIB}" ]] && ls "${TORCH_LIB}"/libcudart.so* &>/dev/null 2>&1; then
        export LD_LIBRARY_PATH="${TORCH_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        echo "  Found in torch: ${TORCH_LIB}"
        CUDA_FOUND=true
    fi

    if ! $CUDA_FOUND; then
        for candidate in \
            "${SITE_PKGS}/nvidia/cuda_runtime/lib" \
            "${VENV_DIR}/lib/python3.12/site-packages/nvidia/cuda_runtime/lib"; do
            if [[ -d "$candidate" ]] && ls "$candidate"/libcudart.so.12* &>/dev/null 2>&1; then
                export LD_LIBRARY_PATH="${candidate}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
                echo "  Found in nvidia-cuda-runtime: ${candidate}"
                CUDA_FOUND=true
                break
            fi
        done
    fi

    if ! $CUDA_FOUND && command -v ldconfig &>/dev/null; then
        CUDART_PATH=$(ldconfig -p 2>/dev/null | grep libcudart.so.12 | head -1 | awk '{print $NF}')
        if [[ -n "${CUDART_PATH:-}" ]]; then
            CUDA_LIB_DIR=$(dirname "${CUDART_PATH}")
            export LD_LIBRARY_PATH="${CUDA_LIB_DIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            echo "  Found via ldconfig: ${CUDA_LIB_DIR}"
            CUDA_FOUND=true
        fi
    fi

    if ! $CUDA_FOUND; then
        for p in /usr/local/cuda/lib64 /usr/local/cuda-12/lib64 \
                 /usr/lib/aarch64-linux-gnu /usr/lib/x86_64-linux-gnu \
                 /usr/local/cuda/targets/sbsa-linux/lib \
                 /usr/local/cuda/targets/aarch64-linux/lib; do
            if [[ -d "$p" ]] && ls "$p"/libcudart.so* &>/dev/null 2>&1; then
                export LD_LIBRARY_PATH="${p}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
                echo "  Found in: ${p}"
                CUDA_FOUND=true
                break
            fi
        done
    fi

    if [[ -n "${SITE_PKGS:-}" ]] && [[ -d "${SITE_PKGS}/nvidia" ]]; then
        for nvlib in "${SITE_PKGS}"/nvidia/*/lib; do
            [[ -d "$nvlib" ]] && export LD_LIBRARY_PATH="${nvlib}:${LD_LIBRARY_PATH}"
        done
        echo "  Added nvidia pip lib dirs"
    fi

    if ! $CUDA_FOUND; then
        echo "  ⚠ Could not find libcudart — try Docker mode instead (default)"
        exit 1
    fi

    echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"

    echo ""
    echo "  Verifying vLLM can load..."
    if ! python3 -c "import vllm; print(f'  vLLM {vllm.__version__} OK ✓')" 2>&1; then
        echo "  ✗ vLLM failed to import. Try Docker mode instead (default)."
        exit 1
    fi

    echo ""
    echo "[4/4] Starting vLLM server (bare-metal)..."
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
echo "  Waiting for server to be ready (loading model shards into GPU, ~2-3 min)..."
echo "  Note: first run downloads ~15GB model to ${HF_CACHE} (cached for future runs)"
for i in $(seq 1 300); do
    # Fail fast: check if container/process is still alive
    if $USE_DOCKER; then
        if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo ""
            echo "  ✗ Container exited unexpectedly."
            echo "  Logs:"
            docker logs --tail 30 "${CONTAINER_NAME}" 2>&1 || true
            exit 1
        fi
    else
        if ! kill -0 $VLLM_PID 2>/dev/null; then
            echo ""
            echo "  ✗ vLLM process exited unexpectedly."
            wait $VLLM_PID 2>/dev/null
            EXIT_CODE=$?
            echo "  Exit code: ${EXIT_CODE}"
            exit 1
        fi
    fi

    if curl -s "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  ✓ vLLM is ready!"
        echo "  Endpoint: http://localhost:${PORT}/v1"
        echo ""
        echo "  Test:"
        echo "    curl http://localhost:${PORT}/v1/chat/completions \\"
        echo "      -H 'Content-Type: application/json' \\"
        echo "      -d '{\"model\": \"${MODEL}\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}'"
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
echo "    - Model shards still loading into GPU (~2-3 min per restart)"
echo "    - OOM: try 'sudo sync && echo 3 > /proc/sys/vm/drop_caches' then retry"
echo "    - Reduce context: MAX_MODEL_LEN=4096 ./scripts/setup_gx10.sh"
if ! $USE_DOCKER; then wait $VLLM_PID 2>/dev/null; fi
