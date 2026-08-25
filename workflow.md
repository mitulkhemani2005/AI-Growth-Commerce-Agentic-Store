# 🔄 AI Growth Commerce - Agentic Store
## Complete Operational & Multi-Agent Workflow Specification

---

## 1. 🌐 Overall System Ecosystem Workflow

```mermaid
flowchart TD
    User([Customer / Shopper]) -->|Natural Language Prompt| Nova[Customer Copilot Nova]
    User -->|Direct UI Interaction| Storefront[Customer Storefront UI]
    
    Nova -->|Tool Execution| FastAPIServer[FastAPI Backend Engine]
    Storefront -->|REST API Calls| FastAPIServer
    
    FastAPIServer --> InventoryDB[(data/inventory.json)]
    FastAPIServer --> OrdersDB[(data/orders.json)]
    FastAPIServer --> ReviewsDB[(data/reviews.json)]
    
    subgraph Autonomous Fleet [24/7 Autonomous Multi-Agent Daemon Fleet]
        FinanceAgent[Finance Manager Agent]
        InventoryAgent[Inventory Manager Agent]
        PriceAgent[Price Manager Agent]
        OrderAgent[Order Manager Agent]
        DispatcherAgent[Dispatcher Agent]
        ReviewAgent[Review & Feedback Agent]
        CEOAgent[CEO Agent]
        
        MessageBus[(data/agent_messages.json)]
        AuditLogs[(data/agent_logs.json)]
        
        FinanceAgent <-->|Alerts & Directives| MessageBus
        InventoryAgent <-->|Demand & Restock Signals| MessageBus
        PriceAgent <-->|Pricing Reports| MessageBus
        OrderAgent <-->|Lifecycle Reports| MessageBus
        DispatcherAgent <-->|Dispatched Signals| MessageBus
        CEOAgent <-->|Directives & Acknowledgments| MessageBus
        
        FinanceAgent --> AuditLogs
        InventoryAgent --> AuditLogs
        PriceAgent --> AuditLogs
        OrderAgent --> AuditLogs
        DispatcherAgent --> AuditLogs
        CEOAgent --> AuditLogs
    end
    
    FastAPIServer <--> AutonomousFleet
    Owner([Store Owner]) <-->|Admin Studio / Omnipotent Chat| AdminPanel[Admin Command Center]
    AdminPanel <--> FastAPIServer
```

---

## 2. 🛍️ Customer Shopping & Payment Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer
    participant Copilot as Nova AI Copilot
    participant Server as FastAPI Server
    participant Inv as Inventory DB
    participant Cart as Cart Manager
    participant Rzp as Razorpay Gateway / AP2

    Customer->>Copilot: "Show me running shoes and add size US 10 to my cart"
    Copilot->>Server: Tool: search_inventory(types=["Footwear"])
    Server->>Inv: Query in-stock items
    Inv-->>Server: Return CyberFlex Runner (Stock: 34, Price: ₹4,398.90)
    Copilot->>Server: Tool: add_to_cart(product_id="prod_001", size="US 10")
    Server->>Cart: Add 1 unit to cart
    Cart-->>Server: Updated Cart (Subtotal: ₹4,398.90, Tax 0%: ₹0.00)
    Server-->>Copilot: Cart synchronized
    Copilot-->>Customer: "Added CyberFlex Apex Runner to your cart! Total: ₹4,398.90"

    Customer->>Copilot: "Proceed to checkout now"
    alt Standard Razorpay Gateway Popup
        Copilot->>Server: Tool: trigger_razorpay_checkout()
        Server->>Rzp: Create Razorpay Order (amount: 439890 paise)
        Rzp-->>Server: Order ID `order_xyz`
        Server-->>Customer: Render Official Razorpay SDK Popup
        Customer->>Rzp: Submit payment (UPI / Card / NetBanking)
        Rzp-->>Server: Verify Payment Signature
    else Agentic Payments Protocol (AP2 Auto-Pay)
        Copilot->>Server: Tool: auto_pay_with_ap2_token()
        Server->>Rzp: Validate cryptographic user AP2 token
        Server->>Rzp: Execute autonomous zero-friction settlement
    end

    Server->>Inv: Atomically reduce stock by 1 unit
    Server->>OrdersDB: Create order #ORD-XXXXX (Status: Confirmed)
    Server-->>Customer: "🎉 Order Confirmed! Tracking will be assigned by Dispatcher."
```

---

## 3. 🤖 Closed-Loop Multi-Agent Collaboration Workflow

```mermaid
sequenceDiagram
    autonumber
    participant InvAgent as Inventory Manager Agent
    participant PriceAgent as Price Manager Agent
    participant FinAgent as Finance Manager Agent
    participant CEO as CEO Agent
    participant DispAgent as Dispatcher Agent
    participant Bus as Inter-Agent Message Bus

    Note over FinAgent,CEO: Cycle 1: Financial & Refund Rate Monitoring
    FinAgent->>FinAgent: Audit orders & compute refund rate (33.3%)
    FinAgent->>Bus: Post `FINANCE_ALERT` to CEO Agent
    
    Note over CEO,PriceAgent: Cycle 2: CEO Strategy & Directive Issuance
    CEO->>Bus: Read Inbox (1 message from Finance)
    CEO->>Bus: Post `CEO_FINANCE_ACKNOWLEDGE` to Finance Agent
    CEO->>Bus: Post `CEO_PRICE_DIRECTIVE` to Price Manager (Target: +10% Surge)
    
    Note over PriceAgent: Cycle 3: Pricing Optimization & Floor Verification
    PriceAgent->>Bus: Read `CEO_PRICE_DIRECTIVE`
    PriceAgent->>PriceAgent: Calculate Dynamic Prices (Ensure PRICE >= BASE_PRICE)
    PriceAgent->>Bus: Post `PRICE_CHANGES_REPORT` to CEO
    
    Note over InvAgent,PriceAgent: Cycle 4: Stock Velocity & Demand Signaling
    InvAgent->>InvAgent: Warehouse audit identifies high velocity SKU
    InvAgent->>Bus: Post `HIGH_DEMAND_SIGNAL` to Price Manager
    InvAgent->>Bus: Post `RESTOCK_ALERT` to CEO (if stock <= 5)
    
    Note over DispAgent: Cycle 5: Fulfillment & Logistics
    DispAgent->>DispAgent: Scan confirmed orders
    DispAgent->>DispAgent: Generate Tracking `TRK-84920`
    DispAgent->>Bus: Post `ORDERS_DISPATCHED` to Order Management Agent
```

---

## 4. 📦 Order Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> Pending: Customer places order
    Pending --> Confirmed: Payment Verified (Stock Deducted)
    Confirmed --> Dispatched: Dispatcher Agent assigns carrier tracking
    Dispatched --> Shipped: Carrier in transit
    Shipped --> Delivered: Customer receives package
    
    Pending --> Cancelled: Customer initiates cancellation
    Confirmed --> Cancelled: Customer initiates cancellation
    
    Cancelled --> Refunded: 24h Policy Evaluated (Age <= 24h & Not Shipped)
    Refunded --> [*]: Stock Restocked & Razorpay Refund Issued
    Delivered --> [*]: Order Completed
```

---

## 5. 💰 Strict 24-Hour Refund Decision Tree

```mermaid
flowchart TD
    Start([Cancellation / Refund Request Initiated]) --> CheckAge{Order Age <= 24 Hours?}
    
    CheckAge -- No (> 24h) --> Reject[❌ Refund Rejected: Exceeds 24-hour window]
    CheckAge -- Yes (<= 24h) --> CheckStatus{Status in 'Shipped' or 'Delivered'?}
    
    CheckStatus -- Yes --> RejectShip[❌ Refund Rejected: Order already in transit / delivered]
    CheckStatus -- No --> Approve[✅ Auto-Approved: Complies with 24-hour policy]
    
    Approve --> RazorpayRefund[Execute Razorpay Refund API]
    RazorpayRefund --> Restock[Atomically Restock Items in inventory.json]
    Restock --> UpdateStatus[Update Order Status to 'Refunded']
    UpdateStatus --> AlertCEO[Finance Manager logs decision & notifies CEO]
```

---

## 6. 👑 Store Owner Command & Control Workflow

```mermaid
flowchart LR
    Owner([Store Owner]) -->|Adjust Floor Price| BasePrice[Set BASE_PRICE in Admin Studio]
    Owner -->|Natural Language Directive| AdminChat[Admin AI Executive Chatbot]
    
    BasePrice -->|Enforces Immutable Floor| Engine[Dynamic Pricing Engine]
    
    AdminChat -->|Translates intent into function calls| Tools[Agent Command Tools]
    Tools -->|command_price_manager| PriceAgent[Price Manager Agent]
    Tools -->|command_inventory_manager| InvAgent[Inventory Manager Agent]
    Tools -->|command_order_manager| OrderAgent[Order Management Agent]
    Tools -->|command_finance_manager| FinAgent[Finance Manager Agent]
    Tools -->|command_ceo_agent| CEOAgent[CEO Agent]
```
