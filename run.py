import uvicorn
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import atexit
from backend.ollama_loader import ensure_ollama_ready, unload_all_models_from_vram

# Register atexit to guarantee VRAM release on any termination
atexit.register(unload_all_models_from_vram)

if __name__ == "__main__":
    print("=" * 60)
    print("  AI Growth Commerce Agentic Store")
    print("  Powered by Ollama Local AI & Autonomous Agent Fleet")
    print("=" * 60)
    print("  - Web Storefront & Prompt Interface: http://127.0.0.1:8000")
    print("  - Admin Intelligence Center:         http://127.0.0.1:8000/frontend/admin/index.html")
    print("  - AgentsOffice Visual RPG Simulator: http://127.0.0.1:8000/office")
    print("  - API Documentation:                 http://127.0.0.1:8000/docs")
    print("=" * 60)

    
    try:
        # 1. Warm up and load Ollama model into GPU VRAM
        ensure_ollama_ready()

        # 2. Start Web Server
        # reload=False ensures backend does NOT restart on database/inventory JSON file writes
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
    except KeyboardInterrupt:
        print("\n[Server] Interrupted by user (CTRL+C).", flush=True)
    finally:
        # 3. Cleanly unload all models from GPU VRAM on server stop
        try:
            unload_all_models_from_vram()
        except BaseException:
            pass
