import uvicorn
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("  AI Growth Commerce Agentic Store")
    print("  Powered by Groq / MiniMax LLM & Autonomous Tools")
    print("=" * 60)
    print("  - Web Storefront & Prompt Interface: http://127.0.0.1:8000")
    print("  - API Documentation: http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
