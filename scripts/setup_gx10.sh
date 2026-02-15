#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Detour — GX10 / DGX Spark Setup Script
#
# Installs vLLM via pip and serves Nemotron NVFP4 directly. No Docker.
#
# Usage:
#   chmod +x scripts/setup_gx10.sh
#   ./scripts/setup_gx10.sh
#   MODEL=... PORT=... ./scripts/setup_gx10.sh   # override defaults
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────
MODEL="${MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4}"
PORT="${PORT:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM="${GPU_MEM:-0.90}"
VENV_DIR="${VENV_DIR:-$HOME/.venv-vllm}"

echo "═══════════════════════════════════════════════════════════════"
echo "  Detour — GX10 Nemotron Setup (bare-metal, no Docker)"
echo "  Model:       ${MODEL}"
echo "  Port:        ${PORT}"
echo "  Max Context: ${MAX_MODEL_LEN}"
echo "  Venv:        ${VENV_DIR}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 0: Kill any leftover Docker container ───────────────────────────
if command -v docker &>/dev/null; then
    docker rm -f detour-vllm 2>/dev/null && echo "[0] Stopped leftover Docker container" || true
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

# ── Ensure CUDA libraries are on LD_LIBRARY_PATH ─────────────────────────
# vLLM needs libcudart.so.12, libnvrtc.so etc. which are native C libs.
# We search dynamically since the path varies across distros / CUDA versions.
echo ""
echo "[*] Locating CUDA libraries..."
CUDA_FOUND=false

# Method 1: ldconfig cache (fastest)
if command -v ldconfig &>/dev/null; then
    CUDART_PATH=$(ldconfig -p 2>/dev/null | grep libcudart.so.12 | head -1 | awk '{print $NF}')
    if [[ -n "${CUDART_PATH:-}" ]]; then
        CUDA_LIB_DIR=$(dirname "${CUDART_PATH}")
        export LD_LIBRARY_PATH="${CUDA_LIB_DIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        echo "  Found via ldconfig: ${CUDA_LIB_DIR}"
        CUDA_FOUND=true
    fi
fi

# Method 2: search common paths
if ! $CUDA_FOUND; then
    for p in /usr/local/cuda/lib64 /usr/local/cuda-12/lib64 \
             /usr/lib/aarch64-linux-gnu /usr/lib/x86_64-linux-gnu \
             /usr/local/cuda/targets/sbsa-linux/lib \
             /usr/local/cuda/targets/aarch64-linux/lib; do
        if [[ -d "$p" ]] && ls "$p"/libcudart.so.12* &>/dev/null 2>&1; then
            export LD_LIBRARY_PATH="${p}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            echo "  Found in: ${p}"
            CUDA_FOUND=true
            break
        fi
    done
fi

# Method 3: brute-force find
if ! $CUDA_FOUND; then
    echo "  Searching filesystem for libcudart.so.12 (may take a moment)..."
    CUDART_PATH=$(find /usr -name 'libcudart.so.12*' -type f 2>/dev/null | head -1)
    if [[ -n "${CUDART_PATH:-}" ]]; then
        CUDA_LIB_DIR=$(dirname "${CUDART_PATH}")
        export LD_LIBRARY_PATH="${CUDA_LIB_DIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        echo "  Found via find: ${CUDA_LIB_DIR}"
        CUDA_FOUND=true
    fi
fi

# Also add nvidia stubs/lib dirs if they exist
for p in /usr/local/cuda/lib64/stubs /usr/lib/aarch64-linux-gnu/nvidia; do
    [[ -d "$p" ]] && export LD_LIBRARY_PATH="${p}:${LD_LIBRARY_PATH}"
done

if ! $CUDA_FOUND; then
    echo "  ⚠ Could not find libcudart.so.12 anywhere!"
    echo "  Try: sudo apt install nvidia-cuda-toolkit"
    echo "  Or:  export LD_LIBRARY_PATH=/path/to/cuda/lib64"
    exit 1
fi

echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"

# ── Step 3: Set up venv + install vLLM ───────────────────────────────────
echo ""
echo "[3/4] Preparing vLLM..."

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "  Creating venv at ${VENV_DIR} (with system-site-packages for CUDA)..."
    python3 -m venv --system-site-packages "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
echo "  Activated venv: ${VENV_DIR}"

if ! python3 -c "import vllm" 2>/dev/null; then
    echo "  Installing vLLM + flashinfer..."
    pip install --upgrade pip

    # flashinfer provides CUTLASS kernels needed for NVFP4 MoE layers
    pip install flashinfer -i https://flashinfer.ai/whl/cu124/torch2.6/ 2>/dev/null \
        || pip install flashinfer 2>/dev/null \
        || echo "  ⚠ flashinfer wheel not available for this platform — vLLM will use fallback kernels"

    pip install vllm
else
    VLLM_VER=$(python3 -c "import vllm; print(vllm.__version__)")
    echo "  vLLM ${VLLM_VER} already installed ✓"
fi

# ── Sanity check: can vllm actually import? ──────────────────────────────
echo ""
echo "  Verifying vLLM can load..."
if ! python3 -c "import vllm; print(f'  vLLM {vllm.__version__} OK ✓')" 2>&1; then
    echo "  ✗ vLLM failed to import. Check LD_LIBRARY_PATH and CUDA installation."
    echo "  LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-<unset>}"
    echo "  Run: find /usr -name 'libcudart.so.12*' 2>/dev/null"
    exit 1
fi

# ── Step 4: Start vLLM server ────────────────────────────────────────────
echo ""
echo "[4/4] Starting vLLM server..."
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

# ── Wait for server ──────────────────────────────────────────────────────
echo "  Waiting for server to be ready (first run downloads ~15GB model)..."
for i in $(seq 1 300); do
    # Fail fast if vllm process already died
    if ! kill -0 $VLLM_PID 2>/dev/null; then
        echo ""
        echo "  ✗ vLLM process exited unexpectedly."
        wait $VLLM_PID 2>/dev/null
        EXIT_CODE=$?
        echo "  Exit code: ${EXIT_CODE}"
        echo "  Check the error output above."
        exit 1
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
        echo "═══════════════════════════════════════════════════════════════"
        wait $VLLM_PID
        exit 0
    fi
    sleep 2
    printf "."
done

echo ""
echo "  ⚠ Server did not become ready within 10 minutes."
echo "  Common issues:"
echo "    - Model still downloading (first run is ~15GB)"
echo "    - OOM: try 'sudo sync && echo 3 > /proc/sys/vm/drop_caches' then retry"
echo "    - Reduce context: MAX_MODEL_LEN=4096 ./scripts/setup_gx10.sh"
wait $VLLM_PID 2>/dev/null
