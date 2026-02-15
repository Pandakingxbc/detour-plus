"""
LLM configuration for the Detour agent system.

Supports three modes:
  1. LOCAL  — Nemotron on the GX10 via vLLM (primary, for NVIDIA prize)
  2. NIM    — NVIDIA API Catalog / NIM endpoint (fallback)
  3. OPENAI — OpenAI-compatible endpoint (dev/testing)

The GX10 (Grace Blackwell, 128GB unified memory) can run:
  - nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 (~60GB, recommended by NVIDIA)
  - nvidia/Nemotron-3-Nano-4B (tiny, ultra-fast for routing)

vLLM serve command for GX10:
  vllm serve nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 \\
      --trust-remote-code \\
      --max-model-len 32768 \\
      --gpu-memory-utilization 0.92 \\
      --dtype auto \\
      --enable-auto-tool-choice \\
      --tool-call-parser hermes \\
      --port 8001
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """Configuration for the LLM backend."""
    # Endpoint
    base_url: str = "http://localhost:8001/v1"
    api_key: str = "not-needed"
    model: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"

    # Generation parameters
    temperature: float = 0.3          # low for deterministic tool-calling
    max_tokens: int = 4096
    top_p: float = 0.95

    # Agent parameters
    max_iterations: int = 15          # max tool-call loops per agent
    recursion_limit: int = 50         # LangGraph recursion limit

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build config from environment variables."""
        return cls(
            base_url=os.getenv("NEMOTRON_BASE_URL", "http://localhost:8001/v1"),
            api_key=os.getenv("NEMOTRON_API_KEY", "not-needed"),
            model=os.getenv("NEMOTRON_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"),
            temperature=float(os.getenv("NEMOTRON_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("NEMOTRON_MAX_TOKENS", "4096")),
        )

    def to_llm_kwargs(self) -> dict:
        """Return kwargs for ChatOpenAI constructor."""
        return {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


# Quick presets
LOCAL_GX10 = LLMConfig(
    base_url="http://localhost:8001/v1",
    model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
)

NVIDIA_NIM = LLMConfig(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY", ""),
    model="nvidia/nvidia-nemotron-3-nano-30b-a3b-bf16",
)

# For development/testing when no GPU is available
OPENAI_FALLBACK = LLMConfig(
    base_url="https://api.openai.com/v1",
    api_key=os.getenv("OPENAI_API_KEY", ""),
    model="gpt-4o-mini",
)
