import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

# ── GPU-only loading enforcement ──────────────────────────────────────────────
# Set these BEFORE any Ollama daemon is spawned so every process inherits them.
# OLLAMA_NUM_GPU=-1   → offload every single layer to GPU; never spill to RAM
# OLLAMA_GPU_OVERHEAD=0 → remove the system-RAM safety buffer Ollama reserves
# OLLAMA_MAX_LOADED_MODELS=1 → only one model in memory at a time (no RAM overflow)
# The server, rather than individual requests, owns model residency.  Do not
# configure a made-up GPU layer count here: Ollama's scheduler will place a
# model entirely on the GPU only when it actually fits.  We verify that fact
# below and refuse to start the agents otherwise.
os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
os.environ.setdefault("OLLAMA_NUM_PARALLEL", "1")
os.environ.setdefault("OLLAMA_MAX_QUEUE", "32")
# ─────────────────────────────────────────────────────────────────────────────

def get_ollama_models_dir() -> Optional[str]:
    """Retrieves the configured OLLAMA_MODELS directory, checking process and Windows registry/user env."""
    if os.environ.get("OLLAMA_MODELS"):
        return os.environ.get("OLLAMA_MODELS")
    
    # Check Windows User and Machine environment variables
    try:
        import winreg
        for hkey, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
        ]:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "OLLAMA_MODELS")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
    except Exception:
        pass
    
    # Common custom locations
    candidates = [
        r"D:\Users\khema\.ollama\models",
        os.path.expanduser(r"~\.ollama\models")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_base_host() -> str:
    """Returns the base HTTP URL for Ollama (default http://127.0.0.1:11434)."""
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    # Strip /v1 if present for native Ollama API calls
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/")


def is_ollama_running(host: Optional[str] = None) -> bool:
    """Checks if the Ollama daemon is reachable."""
    host = host or get_base_host()
    try:
        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "AgenticStoreLoader/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_ollama_daemon() -> bool:
    """Attempts to start ollama serve in the background if not currently running."""
    if is_ollama_running():
        return True
    
    models_dir = get_ollama_models_dir()
    env = os.environ.copy()
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir
    # Force all model layers onto GPU — prevents Ollama from spilling into system RAM
    env["OLLAMA_NUM_GPU"] = "-1"
    env["OLLAMA_GPU_OVERHEAD"] = "0"
    env["OLLAMA_MAX_LOADED_MODELS"] = "1"

    print(f"[Ollama Loader] Ollama daemon not running. Attempting to start background server...", flush=True)
    if models_dir:
        print(f"[Ollama Loader] Using models directory: {models_dir}", flush=True)

    try:
        # Start detached background process
        creationflags = 0
        if os.name == "nt":
            # CREATE_NO_WINDOW or DETACHED_PROCESS
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

        subprocess.Popen(
            ["ollama", "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        
        # Wait up to 10 seconds for Ollama to start responding
        for _ in range(20):
            time.sleep(0.5)
            if is_ollama_running():
                print("[Ollama Loader] Ollama daemon started successfully.", flush=True)
                return True
    except Exception as e:
        print(f"[Ollama Loader Warning] Could not auto-launch 'ollama serve': {e}", flush=True)

    return is_ollama_running()


def get_available_models(host: Optional[str] = None) -> List[str]:
    """Returns a list of model tags available in the local Ollama instance."""
    host = host or get_base_host()
    try:
        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "AgenticStoreLoader/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def get_running_vram_models(host: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns currently loaded models and their VRAM residency from /api/ps."""
    host = host or get_base_host()
    try:
        req = urllib.request.Request(f"{host}/api/ps", headers={"User-Agent": "AgenticStoreLoader/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("models", [])
    except Exception:
        return []


def model_is_fully_gpu_resident(model_name: str, host: Optional[str] = None) -> bool:
    """Return true only when Ollama reports all model weights in VRAM."""
    normalized = model_name if ":" in model_name else f"{model_name}:latest"
    for running in get_running_vram_models(host):
        name = running.get("name") or running.get("model") or ""
        if name == normalized:
            size = int(running.get("size") or 0)
            return size > 0 and int(running.get("size_vram") or 0) >= size
    return False


def preload_model_in_vram(model_name: str, host: Optional[str] = None) -> bool:
    """
    Sends a warm-up/preload request to Ollama with keep_alive=-1 to load the model
    into GPU VRAM immediately and pin it permanently.
    """
    # Resolve host default here so the URL is never built with None
    host = host or get_base_host()
    ctx_len = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
    payload = {
        "model": model_name,
        "keep_alive": -1,  # Keeps model resident for the process lifetime
        "options": {
            "num_ctx": ctx_len
        },
        "stream": False,
    }
    try:
        print(f"[Ollama Loader] Preloading '{model_name}' into GPU VRAM (keep_alive: Forever)...", flush=True)
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "AgenticStoreLoader/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status == 200:
                # A request succeeding is not evidence of GPU-only inference.
                # Ollama reports the authoritative model/VRAM sizes via /api/ps.
                if model_is_fully_gpu_resident(model_name, host):
                    print(f"[Ollama] {model_name}: 100% GPU verified.", flush=True)
                    return True
                unload_model_from_vram(model_name, host)
                print(f"[Ollama] {model_name}: GPU residency could not be verified; CPU/RAM fallback blocked.", flush=True)
                return False
    except urllib.error.HTTPError as e:
        print(f"[Ollama Loader Warning] Preload request returned HTTP {e.code}: {e.reason}", flush=True)
    except Exception as e:
        print(f"[Ollama Loader Warning] Failed to preload '{model_name}': {e}", flush=True)
    return False


def ensure_ollama_ready(preferred_model: Optional[str] = None) -> bool:
    """
    Main entrypoint called during application startup:
    1. Ensures Ollama daemon is active.
    2. Identifies the primary model to use.
    3. Preloads the model into GPU VRAM with permanent keep-alive.
    """
    # 1. Ensure daemon is up
    if not is_ollama_running():
        if not start_ollama_daemon():
            print("\n" + "=" * 60, flush=True)
            print("  [WARNING] Ollama server is NOT running at http://127.0.0.1:11434", flush=True)
            print("  Please open a terminal and run:", flush=True)
            print("    ollama serve", flush=True)
            print("=" * 60 + "\n", flush=True)
            return False

    target = preferred_model or os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    normalized = target if ":" in target else f"{target}:latest"
    if normalized not in get_available_models() or "cloud" in normalized.lower():
        print(f"[Ollama] Configured local model '{normalized}' is not installed. No alternate model will be loaded.", flush=True)
        return False
    if model_is_fully_gpu_resident(normalized):
        return True
    return preload_model_in_vram(normalized)


def unload_model_from_vram(model_name: str, host: Optional[str] = None) -> bool:
    """
    Sends an unload request to Ollama with keep_alive=0 to immediately release GPU VRAM.
    """
    host = host or get_base_host()
    payload = {
        "model": model_name,
        "keep_alive": 0
    }
    try:
        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "AgenticStoreLoader/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except BaseException:
        return False


def unload_all_models_from_vram(host: Optional[str] = None) -> None:
    """
    Queries all currently loaded models in Ollama and frees all GPU VRAM.
    Fast and safe: only queries active VRAM models.
    """
    try:
        host = host or get_base_host()
        if not is_ollama_running(host):
            return

        running = get_running_vram_models(host)
        if not running:
            return

        for m in running:
            name = m.get("name") or m.get("model")
            if name:
                unload_model_from_vram(name, host)

        time.sleep(0.1)
        remaining = get_running_vram_models(host)
        if not remaining:
            print("[Ollama Loader] Model unloaded. GPU VRAM successfully released (0 MB in use).", flush=True)
        else:
            for rem in remaining:
                r_name = rem.get("name") or rem.get("model")
                if r_name:
                    unload_model_from_vram(r_name, host)
    except BaseException:
        pass


