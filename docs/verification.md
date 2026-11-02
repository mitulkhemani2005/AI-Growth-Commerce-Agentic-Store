# Nova — verification, 2 November 2026

## Follow-up: Windows log writes and API documentation

Reproduced the reported missing `ProductImportRequest` schema failure and Windows atomic-replace failure in regression tests before applying fixes.

- Defined and imported the office product request models; restored the import/list storage methods and validated import/update behavior with disposable records.
- Added bounded retries for Windows access/sharing/lock violations during atomic replacement. Unique temporary filenames prevent collisions; permanent failures retain the previous disk snapshot and cache. No truncation fallback or permission changes are used.
- Startup validates all route schemas before reporting readiness.
- Regression tests exercise a real Windows file handle that prevents replacement until released, transient and persistent failures, and 100 concurrent log mutations.
- Full backend suite after these fixes: **113 passed, 1 external integration skipped**. Ruff and changed-file whitespace checks pass.
- Live checks: `/openapi.json`, `/docs`, `/api/health`, storefront and operations all return HTTP 200. All seven specialists and the buyer fleet completed fresh cycles with no current agent errors; the configured model remained 100% GPU-resident.

Background: [Python atomic replacement](https://docs.python.org/3/library/os.html#os.replace) and [Pydantic unresolved types](https://pydantic.dev/docs/validation/latest/errors/usage_errors/#class-not-fully-defined).

## Requested fixes

1. Replaced the neon frontend with a light storefront, product catalog, responsive navigation, and a separate operations workspace. The operations overview includes a live activity timeline and GPU/runtime panel.
2. Enabled the autonomous fleet and fixed the manual-run endpoint: it now schedules work on the application event loop. Activity is persisted with atomic JSON writes and refreshed in the UI every two seconds. Start, completion, failure, audit, and shopper events are visible; inter-agent messages can be included separately.
3. Aligned inference with the installed `qwen2.5:0.5b` model. One shared request lane serves customer chat, specialist agents, buyer reviews, review synthesis, and salary negotiation. Exact model identity and full GPU residency are verified before inference and checked again afterward. Unverified or partial CPU residency is rejected. No unrelated model is silently selected.
4. Verified real operation: autonomous audit logs increased, specialist cycle counters advanced, manual fleet requests completed, model inference completed on the GPU, and the browser completed a demo checkout and displayed its order. Category/budget searches are grounded in live inventory; the verified laptop query returned three matching laptops in about 0.2 seconds.
5. Separated frontend and backend hosting. The storefront and operations UI run on port **5173**. Backend port **8000** serves API responses; `/admin` on the backend returns 404. The bundled office UI is served by the frontend as well.

## Evidence

- `ollama ps`: `qwen2.5:0.5b`, **100% GPU**, context 4096, keep-alive Forever.
- Ollama `/api/ps`: **481,810,185 model bytes** and **481,810,185 VRAM bytes**.
- Live `/api/health`: AI ready, GPU-resident, and background fleet running.
- All seven specialist agents completed autonomous cycles. Manual runs showed queued, started, and completed activity in the browser.
- Browser checks: redesigned storefront, all 12 operations views, fleet run, product add, demo checkout, order history, and phone-sized storefront/operations layouts without page-level horizontal overflow.
- Full backend suite: **106 passed, 1 external integration skipped**. This includes regression coverage for 30 repeated scarcity cycles without compounding prices, and preserving higher owner-set prices.
- Fixed scarcity pricing to calculate from the immutable base cost instead of repeatedly multiplying the last selling price. Four already inflated catalog prices were repaired through the owner API, with their previous values saved in `scratch/pricing-before-repair.json`; stock, orders, and base prices were preserved.
- Frontend: **4 tests passed**, lint passed, production build passed, and production dependency audit reported **0 vulnerabilities**.
- Current machine-readable evidence: [runtime-verification.json](runtime-verification.json).

The tests use disposable data and do not reset the running store. Runtime flags and model settings in `.env` were intentionally updated to enable the requested GPU agents; existing credentials were preserved. No real payment capture was performed. The application remains a local, single-process demo; production boundaries are documented in [README.md](../README.md).

The existing development backend process was already applying the updated code through automatic reload. Automatic approval review rejected an optional restart/temporary-file-cleanup command without a specific reason, so that process was left running. The API and frontend were verified directly afterward.
