"""One inference lane for the configured, fully GPU-resident local model."""

import os
import threading
import time

from openai import OpenAI
from backend.ollama_loader import model_is_fully_gpu_resident, ensure_ollama_ready, get_running_vram_models

_inference_lock = threading.Lock()
_stats_lock = threading.Lock()
_stats = {"requests": 0, "completed": 0, "failed": 0, "active": False, "last_duration_seconds": None, "last_error": None}


def configured_model():
    return os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


def gpu_status():
    selected = configured_model()
    models = get_running_vram_models()
    normalized = selected if ":" in selected else f"{selected}:latest"
    loaded = next((item for item in models if (item.get("name") or item.get("model")) == normalized), None)
    size = int((loaded or {}).get("size", 0))
    vram = int((loaded or {}).get("size_vram", 0))
    ready = size > 0 and vram >= size
    with _stats_lock:
        stats = dict(_stats)
    return {"model": selected, "loaded": loaded is not None, "gpu_resident": ready,
            "processor": "100% GPU" if ready else "Not GPU ready",
            "model_bytes": size, "vram_bytes": vram,
            "gpu_percent": min(100, round(vram / size * 100, 1)) if size else 0,
            "context_length": (loaded or {}).get("context_length"), "inference": stats}


def complete_chat(*, model, messages, tools=None, tool_choice=None, temperature=0.2, max_tokens=1000,
                  base_url=None, api_key="ollama"):
    if model != configured_model():
        raise RuntimeError(f"Agent model '{model}' differs from Nova's configured GPU model '{configured_model()}'.")
    # Queue outside the inference budget. Never load a second model for another agent.
    with _inference_lock:
        if not model_is_fully_gpu_resident(model) and not ensure_ollama_ready(model):
            raise RuntimeError(f"'{model}' is not fully GPU-resident. CPU/RAM inference is blocked.")
        started = time.monotonic()
        client = None
        with _stats_lock:
            _stats.update(active=True, requests=_stats["requests"] + 1)
        try:
            client = OpenAI(base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
                            api_key=api_key or "ollama", max_retries=0, timeout=45)
            arguments = {"model": model, "messages": messages, "temperature": temperature,
                         "max_tokens": min(max_tokens, 1800),
                         "extra_body": {"options": {"num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096"))}, "keep_alive": -1}}
            if tools:
                arguments.update(tools=tools, tool_choice=tool_choice or "auto")
            response = client.chat.completions.create(**arguments)
            if not model_is_fully_gpu_resident(model):
                raise RuntimeError("GPU residency was lost during inference; response rejected.")
            with _stats_lock:
                _stats.update(completed=_stats["completed"] + 1, last_error=None)
            return response
        except Exception as error:
            with _stats_lock:
                _stats.update(failed=_stats["failed"] + 1, last_error=str(error))
            raise
        finally:
            if client is not None:
                client.close()
            with _stats_lock:
                _stats.update(active=False, last_duration_seconds=round(time.monotonic() - started, 2))
