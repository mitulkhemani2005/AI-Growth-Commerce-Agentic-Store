# 🛍️ AI Growth Commerce - Agentic Store
## Complete Project Architecture, Design & Engineering Explanation

---

## 📖 1. Executive Summary & Vision

**AI Growth Commerce Agentic Store** is a next-generation autonomous e-commerce enterprise built with state-of-the-art multi-agent AI architecture. Unlike traditional e-commerce platforms that rely on static databases and manual administrative tasks, this platform operates **24/7 autonomously** with a collaborative fleet of specialized AI agents running on locally installed Ollama LLM (`gemma4:e2b-it-qat`).

### Core Pillars
1. **Autonomous Multi-Agent Fleet**: 7 specialized agents communicating in a closed-loop message bus to audit inventory, dynamically optimize prices, fulfill orders, process refunds, and report to the CEO.
2. **Two-Tier Pricing Engine**: Store Owner sets immutable **Base Price Floor (`BASE_PRICE`)**, while the **Price Manager Agent** dynamically adjusts **Selling Price (`PRICE`)** based on demand, inventory velocity, and margins ($\text{PRICE} \ge \text{BASE\_PRICE}$).
3. **Indian Rupee (INR ₹) & 0% Tax Policy**: Standardized currency across the store with zero tax on all items.
4. **Customer AI Copilot (Nova)**: Natural language conversational assistant with function calling to discover products, manage carts, answer questions, and trigger instant Razorpay checkout.
5. **Agentic Payments Protocol (AP2)**: Secure, cryptographic autonomous tokenized checkout capability enabling AI agents to finalize transactions seamlessly.
6. **Strict 24-Hour Refund Governance**: Auto-approves refunds if an order is cancelled within 24 hours of creation and has not yet been marked as *Shipped* or *Delivered*.

---

## 🏗️ 2. High-Level System Architecture

```
+-------------------------------------------------------------------------------+
|                            👑 STORE OWNER & CUSTOMERS                          |
|         (Customer Storefront / Admin Command Studio / Chat Interfaces)         |
+-------------------------------------------------------------------------------+
                                    | HTTP / REST / JSON
                                    v
+-------------------------------------------------------------------------------+
|                          ⚡ FASTAPI APPLICATION BACKEND                         |
|                               (backend/main.py)                               |
+-------------------------------------------------------------------------------+
        |                     |                    |                   |
        v                     v                    v                   v
+---------------+     +---------------+    +---------------+   +---------------+
|   Inventory   |     |  Cart / Order |    |  Payment Gate |   | Review Engine |
|    Manager    |     |    Manager    |    |  (Razorpay /  |   |   (Sentiment  |
| (data/inv...) |     | (data/orders) |    |     AP2)      |   |  Synthesis)   |
+---------------+     +---------------+    +---------------+   +---------------+
        ^                     ^                    ^                   ^
        |                     |                    |                   |
+-------------------------------------------------------------------------------+
|                       🤖 24/7 AUTONOMOUS MULTI-AGENT FLEET                    |
|                        (backend/background_workers.py)                        |
|                                                                               |
|  [Price Mgr]   [Inventory Mgr]   [Order Mgr]   [Finance Mgr]   [Dispatcher]   |
| (gemma4:e2b)   (gemma4:e2b)      (gemma4:e2b)  (gemma4:e2b)    (gemma4:e2b)   |
|                                                                               |
|           [Review Mgr] (gemma4:e2b)     [CEO Agent] (gemma4:e2b)              |
+-------------------------------------------------------------------------------+
                                    ^
                                    | (JSON Message Bus)
                                    v
+-------------------------------------------------------------------------------+
|                   📡 PERSISTENT INTER-AGENT MESSAGE BUS                       |
|           (data/agent_messages.json & data/agent_logs.json)                   |
+-------------------------------------------------------------------------------+
```

---

## 🤖 3. The 7 Autonomous Specialist Agents

Each agent runs on an independent asynchronous schedule powered by local Ollama (`gemma4:e2b-it-qat`):

### 1. 🏷️ Price Manager Agent (`openai/gpt-oss-20b`)
- **Interval**: 25 seconds
- **Role**: Continuously monitors inventory stock levels, order volume velocity, and competitor price trends.
- **Rule Enforcement**:
  - Automatically calculates surges or discounts based on demand signals.
  - **Hard Constraint**: $\text{PRICE} \ge \text{BASE\_PRICE}$. Selling price will never drop below the immutable base price floor set by the Store Owner.
- **Closed-Loop Signals**: Emits `PRICE_CHANGES_REPORT` to the CEO and confirms updates to the Inventory Manager.

### 2. 📦 Inventory Manager Agent (`openai/gpt-oss-20b`)
- **Interval**: 20 seconds
- **Role**: Audits warehouse stock levels across all SKUs.
- **Rule Enforcement**:
  - Identifies low-stock items ($\le 5\text{ units}$) and issues restock requests to the CEO (`RESTOCK_ALERT`).
  - Identifies high-velocity items and broadcasts `HIGH_DEMAND_SIGNAL` to the Price Manager to capture margin growth.

### 3. 📋 Order Management Agent (`openai/gpt-oss-20b`)
- **Interval**: 20 seconds
- **Role**: Manages lifecycle progression of orders: `Pending` ➔ `Confirmed` ➔ `Dispatched` ➔ `Shipped` ➔ `Delivered`.
- **Rule Enforcement**:
  - Verifies stock deduction on confirmation.
  - Keeps chronological audit logs for all status updates.

### 4. 🚚 Dispatcher Agent (`openai/gpt-oss-20b`)
- **Interval**: 15 seconds
- **Role**: Logistics engine for order fulfillment.
- **Rule Enforcement**:
  - Scans for `Confirmed` orders.
  - Generates unique carrier tracking numbers (`TRK-XXXXX`).
  - Advances orders to `Dispatched` and notifies Order Management via `ORDERS_DISPATCHED`.

### 5. 💰 Finance Manager Agent (`openai/gpt-oss-20b`)
- **Interval**: 30 seconds
- **Role**: Financial integrity, revenue monitoring, and automated refund governance.
- **Rule Enforcement**:
  - Calculates Realized Revenue, GMV, and Refund Ratio.
  - **Strict 24-Hour Cancellation Rule**: Automatically approves refunds if order age $\le 24\text{ hours}$ and status $\notin [\text{"Shipped"}, \text{"Delivered"}]$.
  - Restocks items immediately upon refund and notifies CEO with `FINANCE_ALERT`.
  - Avoids repetitive alert spam by awaiting `CEO_FINANCE_ACKNOWLEDGE`.

### 6. ⭐ Review & Feedback Agent (`openai/gpt-oss-20b`)
- **Interval**: 45 seconds
- **Role**: Customer sentiment synthesis and catalog enrichment.
- **Rule Enforcement**:
  - Analyzes new customer ratings and textual feedback.
  - Computes Bayesian average ratings.
  - Synthesizes dynamic AI summaries and updates product descriptions in `inventory.json`.

### 7. 👔 CEO Agent (`qwen/qwen3.6-27b`)
- **Interval**: 30 seconds
- **Role**: Executive orchestrator of the entire company.
- **Rule Enforcement**:
  - Consumes messages from all subordinate agents.
  - Formulates strategic directives (`CEO_PRICE_DIRECTIVE`, `CEO_FINANCE_ACKNOWLEDGE`, `CEO_INVENTORY_ACKNOWLEDGE`).
  - Compiles comprehensive Executive Reports formatted in Markdown for the Store Owner.

---

## 💳 4. Payment Gateway & AP2 Protocol

### Razorpay Gateway Integration
- Native support for Razorpay standard and test checkout flows.
- Converts INR amounts to paise ($100 \text{ paise} = \text{₹}1.00$) for Razorpay API compatibility.
- Instant signature verification on `/api/payment/verify`.

### Agentic Payments Protocol (AP2)
- Allows customers to authorize one-time tokenization.
- Once authorized, AI Copilot Nova can autonomously place and pay for orders directly within the chat without requiring modal popups.

---

## 🗂️ 5. Repository Structure

```
AI_Growth_Commerce_Agentic_Store/
│
├── backend/
│   ├── admin_agents.py        # 7 Multi-agent implementations & closed-loop logic
│   ├── agent.py               # Customer Copilot Nova & natural language tools
│   ├── background_workers.py  # 24/7 async daemon worker threads & tickers
│   ├── cart_manager.py        # Shopping cart state & session operations
│   ├── inventory_manager.py   # Catalog CRUD & stock atomic locks
│   ├── order_manager.py       # Order lifecycle & 24h refund logic
│   ├── payment_manager.py     # Razorpay Gateway & AP2 token validation
│   ├── review_manager.py      # Customer sentiment analysis & catalog summary
│   └── main.py                # FastAPI REST API endpoints & lifecycle
│
├── data/
│   ├── inventory.json         # Products, SKU specs, Base/Selling prices, stock
│   ├── orders.json            # Order history, tracking numbers, refund audit
│   ├── reviews.json           # Customer ratings & reviews
│   ├── agent_logs.json        # 24/7 chronological decision audit trail
│   └── agent_messages.json    # Inter-agent message bus communication log
│
├── frontend/
│   ├── index.html             # Customer Storefront (Catalog, Cart, Copilot)
│   ├── css/styles.css         # Modern dark-mode neon glassmorphism CSS
│   ├── js/app.js              # Storefront state, Lucide icons, Razorpay SDK
│   └── admin/
│       ├── index.html         # Store Owner Command Center (7 Tabs)
│       ├── css/admin.css      # Admin executive dark-mode UI stylesheet
│       └── js/admin.js        # Admin telemetry, live message feeds, pricing table
│
├── static/images/             # High-resolution vector product assets (SVG)
├── .env                       # Dedicated Groq keys & model configurations
├── requirements.txt           # Python dependency specifications
├── run.py                     # Entry point server launcher
├── test_admin_system.py       # Full system test suite
└── test_human_multiagent.py   # End-to-end multi-agent verification script
```

---

## 🚀 6. How to Run and Test

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Verify `.env` has your dedicated Groq API keys and Razorpay credentials.

### 3. Start the Server
```bash
python run.py
```
- **Customer Storefront**: `http://localhost:8000/`
- **Owner Command Center**: `http://localhost:8000/admin`
- **Interactive API Docs**: `http://localhost:8000/docs`

### 4. Run Test Suite
```bash
python test_human_multiagent.py
python test_admin_system.py
```
