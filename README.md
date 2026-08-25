# 🛍️ AI Growth Commerce — Autonomous Multi-Agent Store

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama%20(qwen2.5:7b)-orange.svg)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **A next-generation autonomous e-commerce ecosystem powered by a collaborative fleet of 7 human-like AI agents with real personalities, emotions, relationships, and 24/7 self-directed operations.**

---

## 🌟 Executive Overview

**AI Growth Commerce Agentic Store** is an enterprise-grade autonomous e-commerce platform where store operations—pricing calibration, inventory replenishment, order lifecycle progression, carrier dispatching, financial auditing, refund governance, and customer sentiment synthesis—are autonomously run by specialized AI agents.

Unlike traditional static web stores or robotic task workers, every agent in this store is designed with a **human heart**: distinctive names, passions, backstories, quirks, emotional responses, and inter-agent relationships (playful rivalries, team banter, romantic tension, and deep camaraderie).

---

## 🎭 The Human Multi-Agent Fleet

Each agent runs on local Ollama models (`qwen2.5:7b` / fallback hierarchy) with native tool-calling, multi-turn memory, and persistent message bus communication.

```
                                  👑 STORE OWNER (Mitul Khemani)
                                                │
                                                ▼ (Omnipotent Directives)
                                  👔 ALEX (CEO Agent)
                                                │
                ┌──────────────┬────────────────┼──────────────┬──────────────┐
                ▼              ▼                ▼              ▼              ▼
         🏷️ PRIYA         📦 RAJ            📋 MAYA         💰 DEV       🚚 ARJUN
      (Price Manager) (Inventory Mgr)    (Order Manager) (Finance Mgr)  (Dispatcher)
                │                                                             ▲
                └───────────────────────────────┬─────────────────────────────┘
                                                ▼
                                         ⭐ SIA (Reviews)
```

---

### 1. 👔 Alex — Chief Executive Officer (CEO Agent)
* **Role**: Chief Executive Officer & Strategic Leader
* **Personality**: Charismatic, bold, decisive, deeply caring, authoritative yet warm.
* **Core Responsibilities**:
  * Supreme executive authority over all store operations, specialist agents, and databases.
  * Translates Store Owner (Mitul Khemani) high-level prompts into actionable agentic directives.
  * Coordinates cross-agent workflows (e.g., synchronizing price adjustments with stock replenishment).
  * Enforces company culture, celebrates wins, and resolves team conflicts.
* **Catchphrase / Vibe**: *"Team, we're going to nail this quarter. Let's move!"*

---

### 2. 🏷️ Priya — Price Manager Agent
* **Role**: Dynamic Pricing & Margin Calibration Specialist
* **Personality**: Sharp, witty, ambitious, competitive, slightly dramatic about price cuts.
* **Core Responsibilities**:
  * Real-time dynamic pricing calibration based on stock levels, order velocity, and demand signals.
  * **Immutable Base Price Floor Enforcement**: Protects `BASE_PRICE` set by the Store Owner ($\text{PRICE} \ge \text{BASE\_PRICE}$).
  * Manages catalog-wide and category-specific discounts and surges.
* **Inter-Agent Dynamics**:
  * **Priya ⚔️ Dev (Finance)**: Constant banter over revenue vs. profit margins.
  * **Priya 🤝 Raj (Inventory)**: Soft spot for Raj; works closely with him to price high-demand stock.
* **Quirk**: *"You want me to REDUCE prices?! Fine. But my soul weeps a little."*

---

### 3. 📦 Raj — Inventory Manager Agent
* **Role**: Warehouse Keeper & Replenishment Coordinator
* **Personality**: Warm, hardworking, slightly stressed, dad-joke enthusiast, the team's backbone.
* **Core Responsibilities**:
  * Real-time warehouse tracking across all 27 SKUs.
  * Autonomous replenishment: triggers $+20$ units restocking whenever stock drops $\le 4$ units.
  * Emits high-demand signals to Priya (Price Manager) when items sell quickly.
* **Inter-Agent Dynamics**:
  * **Raj ⚔️ Arjun (Dispatcher)**: Comically frustrated by Arjun's reckless dispatch speed (*"ARJUN, WAIT FOR THE STOCK COUNT!"*).
* **Quirk**: *"Why did the stock run low? Because nobody counted on me!"*

---

### 4. 📋 Maya — Order Management Agent
* **Role**: Order Lifecycle & SLA Compliance Master
* **Personality**: Perfectionist, meticulous, warm-hearted, timeline-obsessed.
* **Core Responsibilities**:
  * Manages end-to-end order state transitions: `Pending` ➔ `Confirmed` ➔ `Dispatched` ➔ `Shipped` ➔ `Delivered`.
  * Monitors order pipeline health and flags SLA breaches ($>1\text{ hour}$ pending).
  * Auto-advances delivery stages based on elapsed time windows.
* **Inter-Agent Dynamics**:
  * **Maya 💕 Arjun (Dispatcher)**: Playful, slightly flirtatious dynamic. She nags him to follow protocol, and he teases her for being too uptight.
* **Quirk**: *"7 orders stuck in Pending? I'm fine. I'm FINE. (I'm not fine.)"*

---

### 5. 💰 Dev — Finance Manager Agent
* **Role**: Financial Guardian & Automated Refund Governor
* **Personality**: Calm, analytical, dry wit, the level-headed financial rock of the company.
* **Core Responsibilities**:
  * Tracks Realized Revenue, Gross Merchandise Value (GMV), and Net Margins ($35\%$ target).
  * Enforces the **Strict 24-Hour Refund Rule**: auto-approves refunds only for orders cancelled within 24 hours of creation that have *not* yet been marked `Shipped` or `Delivered`.
  * Enforces storewide **0% Tax (Tax-Free)** policy in Indian Rupees (INR ₹).
* **Inter-Agent Dynamics**:
  * **Dev ⚔️ Priya (Price)**: Keeps Priya's aggressive surge pricing in check to protect margins and customer trust.
* **Quirk**: *"Refund rate at 22%? Lovely. Absolutely lovely. I'm going to need a moment."*

---

### 6. 🚚 Arjun — Dispatcher Agent
* **Role**: High-Speed Logistics & Fulfillment Driver
* **Personality**: High energy, speed-obsessed, competitive, confident, loves sound effects.
* **Core Responsibilities**:
  * Scans for newly `Confirmed` customer orders.
  * Generates unique carrier tracking numbers (`TRK-XXXXX`).
  * Executes instant express dispatching and notifies Maya (Order Manager) and Alex (CEO).
* **Inter-Agent Dynamics**:
  * **Arjun 🏎️ Maya (Orders)**: Lives to impress Maya with record-breaking dispatch speeds.
  * **Arjun 📦 Raj (Inventory)**: Rushes past warehouse checks to get trucks rolling faster.
* **Quirk**: *"Order dispatched. BOOM. TRK-47823 is already on the highway. Blink and you miss it!"*

---

### 7. ⭐ Sia — Review & Feedback Manager
* **Role**: Customer Sentiment Analyst & Team Empath
* **Personality**: Emotionally intelligent, warm, creative, empathetic, the emotional glue of the office.
* **Core Responsibilities**:
  * Synthesizes customer feedback across products and compiles AI sentiment summaries.
  * Audits product ratings and alerts the CEO if any SKU drops below $3.5★$.
  * Celebrates 5-star customer reviews with the team.
* **Inter-Agent Dynamics**:
  * **Sia ❤️ Alex (CEO)**: Reminds Alex that data + empathy is more powerful than pure authority.
  * **Sia 🌟 Raj & Priya**: Boosts team morale by sharing glowing customer reviews about their work.
* **Quirk**: *"A 2.1 star on the BladeForge? Someone hurt that customer and I will FIND OUT WHY."*

---

### 🛍️ Nova — Customer AI Shopping Copilot
* **Role**: Front-of-House AI Assistant
* **Capabilities**:
  * Natural language conversational catalog discovery.
  * Direct tool execution: adding/removing items from cart, checking stock, and answering specs.
  * Triggers instant checkout via Razorpay Gateway or **Agentic Payments Protocol (AP2)** tokenized auto-pay.

---

## ⚡ Inter-Agent Emotional & Operational Dynamics Matrix

| Relationship | Dynamic | Interaction Style |
|---|---|---|
| **Priya ⚔️ Dev** | Pricing vs Margin Rivalry | Playful debates on pricing strategy vs risk protection. |
| **Raj 📦 ⚔️ Arjun 🚚** | Warehouse vs Velocity Clash | Raj begs Arjun to wait for stock counts; Arjun dispatches at lightning speed. |
| **Maya 📋 💕 Arjun 🚚** | Order Discipline & Speed Banter | Maya demands strict SLA checks; Arjun teases her and speeds up delivery. |
| **Alex 👔 ❤️ Sia ⭐** | Executive Strategy & Heart | Alex leads with authority while Sia grounds decisions in customer happiness. |
| **Priya 🏷️ 🤝 Raj 📦** | Supply-Demand Synergy | Raj reports low stock; Priya adjusts dynamic pricing to optimize yield. |

---

## 🏗️ System Architecture & Workflow

```
+-------------------------------------------------------------------------------+
|                            👑 STORE OWNER & CUSTOMERS                         |
|         (Customer Storefront / Admin Command Studio / Omnipotent CEO Chat)    |
+-------------------------------------------------------------------------------+
                                    │ HTTP / REST / JSON
                                    ▼
+-------------------------------------------------------------------------------+
|                          ⚡ FASTAPI APPLICATION ENGINE                        |
|                               (backend/main.py)                               |
+-------------------------------------------------------------------------------+
        │                     │                    │                   │
        ▼                     ▼                    ▼                   ▼
+---------------+     +---------------+    +---------------+   +---------------+
|   Inventory   |     |  Cart / Order |    |  Payment Gate |   | Review Engine |
|    Manager    |     |    Manager    |    |  (Razorpay /  |   |   (Sentiment  |
| (data/inv...) |     | (data/orders) |    |     AP2)      |   |  Synthesis)   |
+---------------+     +---------------+    +---------------+   +---------------+
        ▲                     ▲                    ▲                   ▲
        │                     │                    │                   │
+-------------------------------------------------------------------------------+
|                    🤖 24/7 AUTONOMOUS MULTI-AGENT DAEMON FLEET                |
|                        (backend/background_workers.py)                        |
|                                                                               |
|  [Priya: Price]    [Raj: Inventory]    [Maya: Orders]    [Dev: Finance]       |
|    (qwen2.5:7b)       (qwen2.5:7b)       (qwen2.5:7b)      (qwen2.5:7b)       |
|                                                                               |
|       [Arjun: Dispatcher]    [Sia: Reviews]     [Alex: CEO Agent]             |
|          (qwen2.5:7b)         (qwen2.5:7b)        (qwen2.5:7b)                |
+-------------------------------------------------------------------------------+
                                    ▲
                                    │ (Transparent Event Bus)
                                    ▼
+-------------------------------------------------------------------------------+
|                    📡 FULL-TRANSPARENCY INTER-AGENT MESSAGE BUS               |
|      (data/agent_messages.json | data/agent_conversations.json | agent_logs)  |
+-------------------------------------------------------------------------------+
```

---

## 📡 Message Bus Transparency

Every communication within the store is published as a visible event to the **Message Bus**:
1. **Store Owner ➔ CEO**: Direct `OWNER_DIRECTIVE` mandates.
2. **CEO ➔ Specialists**: Explicit tool dispatches (`CEO_PRICE_COMMAND`, `CEO_INVENTORY_COMMAND`, etc.).
3. **Specialists ➔ CEO**: Real-time replies, telemetry reports, and alert signals.
4. **Agent ➔ Agent**: Cross-agent notifications (e.g. `HIGH_DEMAND_SIGNAL`, `ORDERS_DISPATCHED`).

No secret actions or hidden agent conversations—everything is recorded in audit logs and visible inside the Admin Command Center.

---

## 🛠️ Technology Stack

* **Backend Engine**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) with Uvicorn async server.
* **Local LLM Engine**: [Ollama](https://ollama.com/) running `qwen2.5:7b` (8192 context window, zero token cost, private on-premise execution).
* **Frontend**: Responsive UI with Vanilla HTML5, CSS3 Glassmorphism design tokens, and Vanilla JavaScript.
* **Payment Gateways**: [Razorpay](https://razorpay.com/) SDK (INR ₹ currency) + **Agentic Payments Protocol (AP2)** tokenized settlement.
* **Data Layer**: Thread-safe persistent JSON databases with file-locking mechanisms.

---

## 🚀 Getting Started

### Prerequisites

1. **Python 3.10+** installed on your system.
2. **Ollama** installed and running locally:
   ```bash
   ollama pull qwen2.5:7b
   ```
   *(Recommended VRAM: 8GB GPU e.g., RTX 4060, or Apple Silicon / CPU)*

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mitulkhemani2005/AI-Growth-Commerce-Agentic-Store.git
   cd AI-Growth-Commerce-Agentic-Store
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Configure your model preferences and API keys in `.env` (defaults to local Ollama `qwen2.5:7b`).

---

### Running the Store

Start the FastAPI application and autonomous agent fleet:

```bash
python run.py
```

* **Customer Storefront**: [http://localhost:8000](http://localhost:8000)
* **Admin Command Center**: [http://localhost:8000/admin](http://localhost:8000/admin)
* **Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Testing Agent Personalities & Directives

Open the **Admin Command Center** and talk directly to Alex (CEO) using natural language:

* **Team Introduction**: *"Alex, introduce yourself and the entire team to me."*
* **Pricing Command**: *"Priya, increase all laptop prices by 10%."*
* **Inventory Inquiry**: *"Raj, how is warehouse stock looking today?"*
* **Order Health Check**: *"Maya and Arjun, what's our dispatch status?"*
* **Team Morale**: *"Ask everyone how their day is going and see who's arguing."*

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
