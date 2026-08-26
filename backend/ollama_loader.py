import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

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


def preload_model_in_vram(model_name: str, host: Optional[str] = None) -> bool:
    """
    Sends a warm-up/preload request to Ollama with keep_alive=-1 to load the model
    into GPU VRAM immediately and pin it permanently.
    """
    host = host or get_base_host()
    payload = {
        "model": model_name,
        "keep_alive": -1  # Keeps model indefinitely resident in GPU VRAM
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
                # Verify VRAM status
                running = get_running_vram_models(host)
                matched = next((m for m in running if model_name in m.get("name", "")), None)
                if matched:
                    vram_mb = round(matched.get("size_vram", 0) / (1024 * 1024), 1)
                    total_mb = round(matched.get("size", 0) / (1024 * 1024), 1)
                    pct = round((matched.get("size_vram", 0) / max(matched.get("size", 1), 1)) * 100)
                    print(
                        f"[Ollama Loader] Model '{model_name}' loaded in GPU VRAM: {vram_mb} MB / {total_mb} MB ({pct}% offloaded, Context: {matched.get('context_length', 4096)} tokens)",
                        flush=True
                    )
                else:
                    print(f"[Ollama Loader] Model '{model_name}' preload confirmed.", flush=True)
                return True
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

    # 2. Identify candidate model
    available = get_available_models()
    if not available:
        print("[Ollama Loader Warning] Ollama is running but no models were found in local catalog.", flush=True)
        return False

    target = preferred_model or os.environ.get("ADMIN_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))
    
    # Preference matching: first try exact match, then tag match
    preference_order = [target, "qwen2.5:7b", "llama3.1:8b", "llama3:8b", "qwen2.5:14b", "gemma4:e2b-it-qat"]
    chosen_model = None
    
    # 1. Exact match pass
    for cand in preference_order:
        if cand in available:
            chosen_model = cand
            break
            
    # 2. Family match fallback pass if no exact match found
    if not chosen_model:
        for cand in preference_order:
            family = cand.split(":")[0]
            matched = next((a for a in available if a.startswith(family + ":")), None)
            if matched:
                chosen_model = matched
                break

    chosen_model = chosen_model or (available[0] if available else target)
    
    # 3. Check if already loaded in VRAM
    running = get_running_vram_models()
    already_loaded = next((m for m in running if chosen_model in m.get("name", "")), None)
    if already_loaded:
        vram_mb = round(already_loaded.get("size_vram", 0) / (1024 * 1024), 1)
        total_mb = round(already_loaded.get("size", 0) / (1024 * 1024), 1)
        print(f"[Ollama Loader] Model '{chosen_model}' already active in GPU VRAM ({vram_mb} MB / {total_mb} MB).", flush=True)
        return True

    # 4. Preload model into GPU VRAM
    return preload_model_in_vram(chosen_model)


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


