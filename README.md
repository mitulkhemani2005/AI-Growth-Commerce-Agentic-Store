# Nava: Agentic AI Store

> **Autonomous Multi-Agent E-Commerce Platform with Dynamic Margin Intelligence, Agent-to-Agent Commerce Protocols (UAP / ACP / AP2), and Razorpay Rails.**

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)
![React](https://img.shields.io/badge/React-18-61DAFB.svg)
![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg)
![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black.svg)
![Payments](https://img.shields.io/badge/Razorpay-Test--Mode-blue.svg)
![Protocol](https://img.shields.io/badge/AP2-Agent%20Protocol-d4ff00.svg)

---

## ⚡ Overview

**Nava: Agentic AI Store** is an enterprise-grade autonomous commerce platform where traditional customer-facing shopping meets next-generation **Agent-to-Agent (A2A)** and **Agent-to-Consumer (A2C)** commerce.

Built with a high-impact, editorial design system, Nava runs a collaborative fleet of **7 24/7 autonomous specialist AI agents** orchestrated over an asynchronous message bus, alongside **5 AI consumer personas** that continuously browse, transact, and stress-test the store with cryptographic payment mandates.

---

## 🚀 Key Innovations & Features

### 1. Conversational In-App Checkout (Nava AI Copilot)
- **Zero-Friction In-Chat Purchases**: Customers can discover hardware, request spec comparisons, and complete checkouts directly in natural language without popup interruptions.
- **Agentic Payments Protocol (AP2)**: Uses pre-authorized cryptographic spending mandates (`mandate_ap2_...`) allowing Nava to execute tokenized settlements on Razorpay test-mode rails.

### 2. Machine-Readable Agent Catalog (`/.well-known/agent-catalog.json`)
- Standards-compliant catalog adhering to **NPCI Unified Agentic Protocol (UAP)** and **Agentic Commerce Protocol (ACP)** specifications.
- Exposes product schemas, live inventory, immutable base price floors, dynamic surge status, return policies, and supported settlement rails to external and autonomous AI shoppers.
- Manifest available at `/.well-known/ap2-manifest.json`.

### 3. Intelligent Upsell & Cross-Sell Agent
- Analyzes cart contents and browsing intent in real-time.
- Identifies optimal, high-margin complementary hardware pairings (e.g. Workstation Laptop $\rightarrow$ 100W GaN Fast Charger & Sleeve).
- Applies an automated 10% bundle saving while strictly verifying that prices never breach wholesale base cost floors.

### 4. Interactive Campaign Orchestrator
- Enables the store owner to create, activate, pause, or terminate promotional flash sales per product category (strictly at most 1 active campaign per category).
- Synchronizes campaign directives across the store, dynamically updates the storefront marquee announcement ticker, and drives targeted buyer engagement.

### 5. Dual-Tier Dynamic Pricing Engine
- **Base Price Floor (🔒 Store Owner Constraint)**: Immutable cost floor beneath which an item can never be sold.
- **Selling Price (📈 Dynamic AI Pricing)**: Autonomously modulated in real-time based on competitor demand signals, stock levels, and transaction velocity.

### 6. Explainable, Bounded & Gated Financial Actions
- **Explainable**: Every price shift, AP2 charge, wholesale restock, and refund includes an audited rationale and timestamp.
- **Bounded**: Hard spending limits (e.g., maximum ₹25,000 per AP2 transaction) prevent unauthorized capital leakage.
- **Gated**: Strict 24-hour pre-shipment refund policy gate prevents inventory discrepancies after logistics dispatch.

---

## 🏗️ System Architecture

```
                                  ┌─────────────────────────────┐
                                  │   Customer / AI Shoppers   │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           NAVA STOREFRONT (React 18 + Vite)                             │
│  - Editorial Minimalist Layout          - Live Cart Drawer & Cross-Sell Strips         │
│  - Floating Athletic Nava Copilot       - Dynamic Dual-Pricing Badges                   │
│  - Real-Time Order Dispatch Tracking    - Owner Command Studio                          │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                             FASTAPI BACKEND ENGINE (run.py)                             │
│                                                                                         │
│   /.well-known/agent-catalog.json       /api/cart/cross-sells       /api/campaigns      │
│   /.well-known/ap2-manifest.json        /api/chat/conversational-checkout               │
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         7 AUTONOMOUS SPECIALIST AGENTS                          │   │
│   │  [Price Manager]  [Inventory Velocity]  [Order Manager]   [Dispatcher Agent]    │   │
│   │  [Finance Auditor] [Review Synthesizer] [CEO Strategic Commander]              │   │
│   └────────────────────────────────────────┬────────────────────────────────────────┘   │
│                                            │                                            │
│                                            ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                    INTER-AGENT MESSAGE BUS & SHARED LEDGERS                     │   │
│   │  - agent_messages.json                  - inventory.json (Dual-Pricing)         │   │
│   │  - treasury.json (Audited Cash Flow)    - buyer_agents.json (5 AI Shoppers)     │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
  ┌─────────────────────────────┐                 ┌─────────────────────────────┐
  │      LOCAL OLLAMA LLM       │                 │   PAYMENT & AP2 GATEWAY     │
  │  - qwen2.5:7b / llama3.1    │                 │  - Razorpay Test-Mode APIs  │
  │  - Zero GPU Cloud Egress    │                 │  - AP2 Cryptographic Tokens │
  └─────────────────────────────┘                 └─────────────────────────────┘
```

---

## 🤖 The 7 Autonomous Specialist Agents

| Agent | Core Mandate | Execution Cycle |
|---|---|---|
| **Price Manager** | Modulates dynamic selling prices based on demand while strictly enforcing the Base Price Floor (`PRICE >= BASE_PRICE`). | Every 25s |
| **Inventory Manager** | Tracks warehouse stock velocity, flags low-stock SKUs, and executes wholesale restocks from the CEO Treasury. | Every 20s |
| **Order Manager** | Governs order lifecycle transitions (`Pending` $\rightarrow$ `Confirmed` $\rightarrow$ `Dispatched` $\rightarrow$ `Shipped` $\rightarrow$ `Delivered`) and executes 24-hour refund policies. | Every 20s |
| **Dispatcher Agent** | Generates authentic logistics tracking codes (Bluedart Express, Delhivery Prime) and schedules courier dispatches. | Every 15s |
| **Finance Manager** | Audits gross merchandise value (GMV), net margins, tax compliance (0% storewide), and payroll disbursal. | Every 30s |
| **Review & Feedback Agent** | Synthesizes verified customer reviews with sentiment analysis and auto-generates catalog descriptions. | Every 45s |
| **CEO Agent** | Directs multi-agent alignment, conducts interactive salary negotiations, and acts as the Store Owner command interface. | Every 30s |

---

## 🛍️ 5 Autonomous AI Shoppers Fleet

Nava features 5 synthetic consumer personas executing continuous purchase cycles with pre-allocated budgets:

1. **Alex Chen** — *Flagship Hunter*: Prioritizes premium 5G smartphones and titanium hardware.
2. **Sophia Miller** — *Bargain Hunter*: Focuses on dynamic AI discounts and flash sale campaigns.
3. **David Patel** — *Audiophile*: Dedicated to active noise cancelling studio acoustics.
4. **Elena Rostova** — *Luxury Tech Enthusiast*: Purchases top-tier workstations and premium accessories.
5. **Marcus Kim** — *Trendsetter*: Rapid buyer testing novel product drops and stress-testing refund policies.

---

## ⚙️ Quickstart Guide

### Prerequisites
- **Python**: 3.10 or higher
- **Node.js**: 18 or higher (with `npm`)
- **Ollama**: Installed locally with `qwen2.5:7b` or `llama3.1:8b`
  ```bash
  ollama pull qwen2.5:7b
  ```

### 1. Clone & Environment Configuration
```bash
git clone https://github.com/mitulkhemani2005/AI-Growth-Commerce-Agentic-Store.git
cd AI-Growth-Commerce-Agentic-Store

# Create and activate Python virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b
RAZORPAY_KEY_ID=rzp_test_placeholder
RAZORPAY_KEY_SECRET=placeholder_secret
INITIAL_BANK_BALANCE=500000.00
PORT=8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Launch the Server
```bash
python run.py
```

The application will be live at:
- **Customer Storefront**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Store Owner Command Studio**: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- **Agents Office RPG Simulator**: [http://127.0.0.1:8000/office](http://127.0.0.1:8000/office)
- **Interactive API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

*(Optional: For live frontend development with Hot Module Replacement, run `npm run dev` in the `frontend/` directory).*

---

## 📡 API Reference Overview

### Agent Protocols & Discovery
- `GET /.well-known/agent-catalog.json` — Machine-readable UAP / ACP product catalog.
- `GET /.well-known/ap2-manifest.json` — AP2 protocol manifest and spending bounds.
- `GET /api/cart/cross-sells?user_id=...` — Personalized accessory bundle recommendations.
- `POST /api/chat/conversational-checkout` — 1-click in-app conversational AP2 checkout.

### Promotional Campaigns
- `GET /api/campaigns/active` — Active flash sale campaign.
- `GET /api/admin/campaigns` — All promotional campaigns.
- `POST /api/admin/campaigns/launch` — Launch bounded promotional campaign.

### Financial Guardrails & Audit
- `GET /api/admin/audit-trail` — Chronological explainable money ledger with policy evaluations.
- `GET /api/admin/treasury` — Real-time bank balance, wholesale spend, sales deposits, and net profit ledger.

### Payments
- `GET /api/payment/config` — Public Razorpay Key ID.
- `POST /api/payment/create-order` — Initialize Razorpay order.
- `POST /api/payment/verify` — Verify HMAC SHA-256 signature.
- `POST /api/payment/agent-autopay` — Execute autonomous AP2 payment.

---

## 🛡️ Financial Guardrails & Failure Modes

1. **AP2 Mandate Budget Cap**: Single transactions cannot exceed the pre-approved safety cap (₹25,000). Excessive orders trigger a bounded rejection and request standard checkout.
2. **Base Price Floor Lock**: The Store Owner sets an immutable cost floor for every SKU. Dynamic price decreases are bounded: $\text{Price} \ge \text{Base Price}$.
3. **24-Hour Non-Shipped Policy**: Automated refunds are permitted only within 24 hours of creation and before carrier dispatch. Orders in transit require Store Owner override.

---

## 🧪 Testing & Verification

Run the full integration test suite:
```bash
python tests/test_nava_store.py
python tests/test_react_frontend.py
```

All tests execute end-to-end against live FastAPI routes without external mocks.

---

## 📄 License

MIT License. Designed and engineered for next-generation autonomous e-commerce.
