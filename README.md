# Nova

Nova is a local agentic commerce application with a separate React frontend, FastAPI API, seven autonomous specialist agents, synthetic shoppers, and a GPU-backed Ollama model.

## Start the project

Use two terminals from the project directory. Python 3.10+ and Node 20.19+ or 22.13+ are required.

**Terminal 1 — backend**

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.lock
# Copy .env.example to .env only when .env does not already exist.
.\.venv\Scripts\python run.py
```

**Terminal 2 — frontend**

```powershell
cd frontend
npm ci
npm run dev
```

| Service | Address |
| --- | --- |
| Storefront | http://127.0.0.1:5173/ |
| Operations, live activity, agents | http://127.0.0.1:5173/admin |
| Optional agent office visualization | http://127.0.0.1:5173/office/ |
| Backend API | http://127.0.0.1:8000/ |
| API documentation | http://127.0.0.1:8000/docs |
| GPU and runtime health | http://127.0.0.1:8000/api/health |

The backend does **not** serve the React app or an admin HTML page. Vite owns the frontend and proxies `/api`, `/static`, and `/.well-known` to the API. For a separate production-style frontend preview, run `npm run build` followed by `npm run preview` in `frontend/`; its address is port 4173.

`python run.py` deliberately runs a single backend worker without automatic reload. JSON writes and the agent fleet must not restart the application. Frontend source changes still use Vite hot reload.

For backend development, `.\.venv\Scripts\python -m uvicorn backend.main:app --reload --reload-dir backend --reload-dir agents_office/app` also works. Keep only one backend instance running against a data directory. Use the explicit venv Python to avoid another Python installation's launcher.

On Windows, activity snapshots retain atomic replacement and briefly retry file-sharing conflicts (`WinError 5`, `32`, or `33`), such as a reader or scanner holding the previous snapshot. Persistent permission failures remain visible and preserve the previous file. Startup also generates the complete OpenAPI schema before starting agents, so an undefined request model cannot remain hidden until `/docs` is opened.

## GPU model and autonomous agents

The provided local configuration uses the installed **qwen2.5:0.5b** model. Install it with `ollama pull qwen2.5:0.5b` on another machine. Ollama must be running on port 11434.

```dotenv
OLLAMA_MODEL=qwen2.5:0.5b
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_NUM_CTX=4096
AI_ENABLED=true
BACKGROUND_AGENTS_ENABLED=true
BUYER_SIMULATION_ENABLED=true
PAYMENT_MODE=demo
FRONTEND_URL=http://127.0.0.1:5173
```

All inference paths share the configured `OLLAMA_MODEL` and one request lane. Startup and inference verify exact model identity and full GPU residency using Ollama's `/api/ps`. A missing model, unverified residency, or partial CPU offload blocks inference; another model is never silently substituted. The API stays available and exposes the reason if GPU readiness fails. Use **Load model on GPU** in Operations to retry readiness.

The Operations dashboard shows model name, VRAM bytes, processor placement, completed inference requests, agent states, and session cycle counts. The **Live activity** view refreshes every two seconds and includes start, completion, error, audit, and shopper events. Inter-agent messages can be included with the Messages checkbox. Activity is persisted atomically in `data/agent_logs.json`.

Ollama's `ollama ps` should show `100% GPU`. This indicates the model is wholly GPU-resident; the Python server and normal host-side runtime still use system memory. See [Ollama's GPU verification documentation](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu).

A larger model can be selected by installing it and changing `OLLAMA_MODEL`, then restarting the backend. It must fit fully in the available VRAM. The small default model is sufficient to run local inference but has limited reasoning quality; catalog discovery is therefore grounded in actual product categories and budget filters instead of trusting unrelated model recommendations.

## Shopping and management

- Storefront: category/search filters, sorting, stock availability, bag quantities, checkout, order history, and Nova Copilot.
- Operations: live activity, manual fleet/individual runs, schedules, products, stock, orders, treasury, salaries, shoppers, campaigns, refunds, reviews, and CEO chat.
- Price floors, stock limits, refund windows, and legal order transitions are validated in the backend.
- Checkout intents are bound to customer and cart, expire, and reject replay that would create a duplicate order. Treasury accounting is applied once.

Background agents change the store: they audit and adjust prices, restock within the treasury budget, dispatch/advance orders, review feedback, and coordinate through persisted messages. Synthetic shoppers create demo purchases and reviews. A low treasury balance can legitimately block restocking; the activity stream records those decisions.

## Payments and owner access

The default payment mode is **demo**. No real money is charged, and checkout identifies the simulation clearly. For interactive Razorpay checkout, configure `PAYMENT_MODE=razorpay` and server-side test credentials, then restart. Gateway failures never become simulated successful captures. Autonomous real-money mandates are not implemented; autonomous payments remain demo-only. No live payment capture was performed during verification.

Set `NOVA_ADMIN_TOKEN` in `.env` to require a bearer token for owner APIs. Enter it in the Operations access form. Never commit `.env` or expose secrets through `VITE_` variables. Existing credential values are preserved when updating runtime flags.

`NOVA_DATA_DIR` can redirect JSON storage to a separate directory. Seed `inventory.json` before using an empty directory. Back up `data/` before using Reset Store.

## Checks

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check backend tests
cd frontend
npm run lint
npm test
npm run build
npm audit --omit=dev
```

Tests use disposable store data and disable the real fleet, GPU calls, and gateway. An external test is skipped by default; `--run-external` explicitly enables creating an unpaid Razorpay test order with test credentials only. Use pytest rather than running historical verification scripts directly, since standalone scripts may modify their configured data directory.

The app is a local, single-process JSON application. Public deployment requires customer authentication/authorization, transactional storage with migrations, durable reservations and payment reconciliation, rate limiting, and operational monitoring. Per-file atomic writes are not multi-file database transactions. The commerce-protocol manifests, 0% tax policy, and logistics tracking are demonstrations rather than certification, tax compliance, or carrier integrations.
