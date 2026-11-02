"""Run the Nova API. Start the frontend separately with npm run dev."""

import os
import uvicorn
from backend.config import BASE_DIR  # Load the root environment before reading listener settings.


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Nova's demo customer profiles are local-only. Bind HOST to localhost; public deployment requires customer authentication and transactional database storage.")
    print(f"Nova API:      http://{host}:{port}")
    print(f"API docs:      http://{host}:{port}/docs")
    print(f"Frontend:      {os.getenv('FRONTEND_URL', 'http://127.0.0.1:5173')} (npm run dev in frontend/)")
    uvicorn.run("backend.main:app", host=host, port=port, reload=False, workers=1)


if __name__ == "__main__":
    main()
