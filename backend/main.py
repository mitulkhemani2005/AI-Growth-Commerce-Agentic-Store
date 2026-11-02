from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import time
import hmac
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from backend.config import AI_ENABLED, BACKGROUND_AGENTS_ENABLED, PAYMENT_MODE
from backend.transactions import serialized

from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.agent import commerce_agent
from backend.payment_manager import payment_manager
from backend.review_manager import review_manager
from backend.treasury_manager import treasury_manager
from backend.salary_manager import salary_manager
from backend.buyer_agents import buyer_agents_fleet
from backend.admin_agents import (
    ceo_agent,
    admin_chat_agent,
    message_bus,
    refund_manager_agent
)
from backend.background_workers import background_worker
from backend.ollama_loader import ensure_ollama_ready, unload_model_from_vram
from backend.llm_runtime import gpu_status, configured_model
from backend.agent_tasks import task_manager
from backend.observability import observability_manager
from backend.policy_engine import validate_policy
from backend.idempotency import idempotency_manager
from backend.agents.upsell_agent import UpsellAgent
from backend.agents.campaign_orchestrator import CampaignOrchestrator

# Initialize specialized intelligence agents
upsell_agent = UpsellAgent(inventory_manager=inventory_manager)
campaign_orchestrator = CampaignOrchestrator(
    inventory_manager=inventory_manager,
    message_bus=message_bus,
    buyer_manager=buyer_agents_fleet
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate every mounted route before reporting a healthy startup.
    app.openapi()
    app.state.manual_tasks = set()
    app.state.ai_ready = False
    if AI_ENABLED:
        app.state.ai_ready = await asyncio.to_thread(ensure_ollama_ready)
        os.environ["AI_RUNTIME_AVAILABLE"] = str(app.state.ai_ready).lower()
    app.state.runtime_error = None
    if AI_ENABLED and not app.state.ai_ready:
        app.state.runtime_error = f"Configured model {configured_model()} is not fully GPU-resident. Agent inference is blocked."
    if BACKGROUND_AGENTS_ENABLED and (not AI_ENABLED or app.state.ai_ready):
        background_worker.start()
    elif app.state.runtime_error:
        from backend.admin_agents import log_agent_action
        log_agent_action("Nova Runtime", "GPU readiness blocked", app.state.runtime_error)
    try:
        yield
    finally:
        background_worker.stop()
        for task in app.state.manual_tasks:
            task.cancel()
        await asyncio.gather(*app.state.manual_tasks, return_exceptions=True)
        if background_worker._task:
            await asyncio.gather(background_worker._task, return_exceptions=True)
        if AI_ENABLED:
            await asyncio.to_thread(unload_model_from_vram, configured_model())

app = FastAPI(title="Nova: Agentic AI Store", version="1.0.0", lifespan=lifespan)
app.state.manual_tasks = set()

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_owner_actions(request: Request, call_next):
    owner_path = request.url.path.startswith("/api/admin") or request.url.path in {
        "/api/payment/credentials", "/api/settings", "/api/simulation/failure-test"
    }
    token = os.getenv("NOVA_ADMIN_TOKEN", "")
    if owner_path and token and request.method != "OPTIONS":
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return JSONResponse({"detail": "Owner access requires a valid Nova admin token."}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/api/health")
def health():
    gpu = gpu_status() if AI_ENABLED else {"model": configured_model(), "gpu_resident": False, "processor": "Disabled"}
    return {"status": "ok" if not AI_ENABLED or gpu["gpu_resident"] else "degraded", "name": "Nova",
            "payment_mode": PAYMENT_MODE, "ai_enabled": AI_ENABLED, "ai_ready": gpu["gpu_resident"],
            "background_agents_enabled": background_worker._running, "gpu": gpu,
            "runtime_error": getattr(app.state, "runtime_error", None),
            "frontend_url": os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")}


@app.get("/api/admin/runtime")
def runtime_status():
    return {**health(), "fleet": background_worker.get_status()}


@app.post("/api/admin/runtime/retry")
async def retry_runtime():
    if not AI_ENABLED:
        raise HTTPException(status_code=409, detail="Enable AI_ENABLED in .env and restart the API.")
    ready = await asyncio.to_thread(ensure_ollama_ready, configured_model())
    app.state.ai_ready = ready
    os.environ["AI_RUNTIME_AVAILABLE"] = str(ready).lower()
    app.state.runtime_error = None if ready else "GPU readiness failed. Check the configured local model and available VRAM."
    if ready and BACKGROUND_AGENTS_ENABLED:
        background_worker.start()
    return {"success": ready, **health()}

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Ensure static folders exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "images"), exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# The frontend runs separately on port 5173. Only product/office assets are hosted here.
OFFICE_STATIC_DIR = os.path.join(BASE_DIR, "agents_office", "app", "static", "office")
if os.path.exists(OFFICE_STATIC_DIR):
    app.mount("/static/office", StaticFiles(directory=OFFICE_STATIC_DIR), name="static_office")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

try:
    import sys
    sys.path.insert(0, os.path.join(BASE_DIR, "agents_office"))
    from app.office.router import router as office_router
    app.include_router(office_router, prefix="/api/v1/office", tags=["AgentsOffice"])
except Exception as e:
    print(f"[AgentsOffice] Router mount note: {e}")


# Request Models
class RequestModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)

class ChatRequest(RequestModel):
    user_id: str = "user_alex"
    prompt: str = Field(min_length=1, max_length=10000)
    conversation_history: Optional[List[Dict[str, str]]] = None

class AddToCartRequest(RequestModel):
    user_id: str = "user_alex"
    product_id: str
    quantity: int = Field(default=1, gt=0, le=1000, strict=True)
    size: Optional[str] = None

class RemoveFromCartRequest(RequestModel):
    user_id: str = "user_alex"
    product_id: str
    quantity: Optional[int] = Field(default=None, gt=0, le=1000, strict=True)

class CheckoutRequest(RequestModel):
    user_id: str = "user_alex"
    shipping_address: Optional[str] = None
    payment_method: str = "Razorpay Gateway (Online)"

class RazorpayCreateOrderRequest(RequestModel):
    user_id: str = "user_alex"
    currency: str = "INR"

class RazorpayVerifyPaymentRequest(RequestModel):
    user_id: str = "user_alex"
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    shipping_address: Optional[str] = None

class RazorpayCredentialsRequest(RequestModel):
    key_id: str
    key_secret: str

class CardPaymentRequest(RequestModel):
    user_id: str = "user_alex"
    card_number: str
    expiry_date: str
    cvv: str
    cardholder_name: str
    shipping_address: Optional[str] = None
    currency: str = "INR"

class SaveCustomerCardRequest(RequestModel):
    user_id: str = "user_alex"
    card_number: str
    expiry_date: str
    cvv: str
    cardholder_name: str

class AP2SaveTokenRequest(RequestModel):
    user_id: str = "user_alex"
    razorpay_payment_id: str
    razorpay_order_id: str
    card_details: Optional[Dict[str, Any]] = None

class SettingsRequest(RequestModel):
    api_key: Optional[str] = None
    model: Optional[str] = None

# API Endpoints

@app.get("/api/user")
def get_user_profile(user_id: str = "user_alex"):
    user = cart_manager.get_user(user_id)
    if not user:
        # Return default fallback
        return {
            "user_id": user_id,
            "name": "Alex Rivera",
            "email": "alex.rivera@growthcommerce.ai",
            "shipping_address": "742 Evergreen Terrace, San Francisco, CA 94107",
            "auto_pay_enabled": True
        }
    return user

@app.get("/api/inventory")
def get_inventory(
    query: Optional[str] = None,
    product_type: Optional[str] = None,
    size: Optional[str] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False
):
    products = inventory_manager.search_products(
        query=query,
        product_type=product_type,
        size=size,
        max_price=max_price,
        in_stock_only=in_stock_only
    )
    return {
        "count": len(products),
        "products": products
    }

@app.get("/api/inventory/{product_id}")
def get_product(product_id: str):
    product = inventory_manager.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.get("/api/cart")
def get_cart(user_id: str = "user_alex"):
    cart = cart_manager.get_cart(user_id)
    return cart

@app.post("/api/cart/add")
def add_to_cart(req: AddToCartRequest):
    result = cart_manager.add_to_cart(
        user_id=req.user_id,
        product_identifier=req.product_id,
        quantity=req.quantity,
        size=req.size
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add to cart"))
    return result

@app.post("/api/cart/remove")
def remove_from_cart(req: RemoveFromCartRequest):
    result = cart_manager.remove_from_cart(
        user_id=req.user_id,
        product_identifier=req.product_id,
        quantity=req.quantity
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove from cart"))
    return result

@app.post("/api/cart/clear")
def clear_cart(user_id: str = "user_alex"):
    result = cart_manager.clear_cart(user_id)
    return result

@app.post("/api/checkout")
def checkout(req: CheckoutRequest):
    if PAYMENT_MODE != "demo":
        raise HTTPException(status_code=400, detail="Complete verified Razorpay checkout first.")
    result = order_manager.create_order_from_cart(
        user_id=req.user_id,
        shipping_address=req.shipping_address,
        payment_method=req.payment_method
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Checkout failed"))

    # Deposit sales revenue to CEO Treasury
    order = result.get("order", {})
    treasury_manager.deposit_sales(
        amount=order.get("total", 0.0),
        order_id=order.get("order_id", ""),
        items_summary=f"{len(order.get('items', []))} items",
        customer=order.get("customer_name", req.user_id)
    )
    return result

# Razorpay Payment Gateway Endpoints

@app.get("/api/payment/config")
def get_payment_config():
    """Returns the active Razorpay Key ID for client-side checkout popup."""
    return {
        "key_id": payment_manager.get_public_key_id(),
        "gateway": "Razorpay" if PAYMENT_MODE == "razorpay" else "Nova Demo",
        "mode": PAYMENT_MODE
    }

@app.post("/api/payment/create-order")
def create_razorpay_order(req: RazorpayCreateOrderRequest):
    """
    Creates a Razorpay Order based on the current cart total.
    """
    cart = cart_manager.get_cart(req.user_id)
    if not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cannot create payment order: Cart is empty.")

    total_amount = cart.get("estimated_total", 0.0)
    receipt_id = f"rcpt_{req.user_id}_{int(os.times().elapsed)}"
    
    order_data = payment_manager.create_order(
        amount_in_usd_or_inr=total_amount,
        receipt_id=receipt_id,
        currency=req.currency
    )
    if not order_data.get("success"):
        raise HTTPException(status_code=502, detail=order_data.get("error", "Payment initialization failed."))
    payment_manager.bind_checkout(order_data, req.user_id, cart)
    order_data["cart"] = cart
    return order_data

@app.post("/api/payment/verify")
@serialized
def verify_razorpay_payment(req: RazorpayVerifyPaymentRequest):
    """
    Verifies Razorpay HMAC signature, deducts stock, and records the confirmed order.
    """
    validation = payment_manager.validate_checkout(
        req.user_id, req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature,
        cart_manager.get_cart(req.user_id))
    if not validation["success"]:
        raise HTTPException(status_code=400, detail=validation["error"])
    if validation.get("result"):
        return validation["result"]

    # Payment is authentic! Confirm order & deduct stock
    order_result = order_manager.create_order_from_cart(
        user_id=req.user_id,
        shipping_address=req.shipping_address,
        payment_method="Razorpay Gateway (Online)",
        payment_details={
            "razorpay_order_id": req.razorpay_order_id,
            "razorpay_payment_id": req.razorpay_payment_id,
            "is_demo": PAYMENT_MODE == "demo",
            "verified": True
        }
    )
    if not order_result.get("success"):
        raise HTTPException(status_code=400, detail=order_result.get("error", "Failed to finalize order."))

    # Deposit sales revenue to CEO Treasury
    order = order_result.get("order", {})
    treasury_manager.deposit_sales(
        amount=order.get("total", 0.0),
        order_id=order.get("order_id", ""),
        items_summary=f"{len(order.get('items', []))} items",
        customer=order.get("customer_name", req.user_id)
    )

    # Emit payment event to notify fleet (Finance Manager -> Order Manager)
    try:
        from backend.events import emit_store_event, EventType
        emit_store_event(
            event_type=EventType.PAYMENT_RECEIVED,
            source_agent="Finance Manager Agent",
            payload={
                "order_id": order.get("order_id"),
                "payment_id": req.razorpay_payment_id,
                "amount": order.get("total", 0.0),
                "payment_method": "Razorpay Gateway (Online)"
            }
        )
    except Exception as e:
        print(f"[Payment Event Error]: {e}", flush=True)

    # AP2 Protocol: Save payment token for future autonomous agent payments
    if PAYMENT_MODE == "demo":
        payment_manager.save_ap2_token_from_payment(
            user_id=req.user_id, razorpay_payment_id=req.razorpay_payment_id,
            razorpay_order_id=req.razorpay_order_id,
            card_details=cart_manager.get_customer_payment_details(req.user_id) or {})

    result = {
        "success": True,
        "message": f"Payment {req.razorpay_payment_id} verified successfully.",
        "order": order_result.get("order"),
        "razorpay_payment_id": req.razorpay_payment_id,
        "ap2_token_saved": PAYMENT_MODE == "demo"
    }
    payment_manager.complete_checkout(req.razorpay_order_id, req.razorpay_payment_id, result)
    return result

@app.post("/api/payment/credentials")
def update_razorpay_credentials(req: RazorpayCredentialsRequest):
    """Update Razorpay Key ID and Secret dynamically."""
    res = payment_manager.update_credentials(req.key_id, req.key_secret)
    return res

@app.post("/api/payment/card-checkout")
def card_checkout_razorpay(req: CardPaymentRequest):
    """
    Validates customer card, saves to profile, creates Razorpay Order & Payment, confirms order.
    """
    result = payment_manager.process_razorpay_card_payment(
        user_id=req.user_id,
        card_number=req.card_number,
        expiry_date=req.expiry_date,
        cvv=req.cvv,
        cardholder_name=req.cardholder_name,
        shipping_address=req.shipping_address,
        currency=req.currency
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Card payment failed"))
    
    # Deposit to treasury
    order = result.get("order", {})
    if order:
        treasury_manager.deposit_sales(
            amount=order.get("total", 0.0),
            order_id=order.get("order_id", ""),
            items_summary=f"{len(order.get('items', []))} items",
            customer=req.cardholder_name
        )
    return result

@app.get("/api/customer/payment-details")
def get_customer_payment_details(user_id: str = "user_alex"):
    """Returns saved customer payment card details if available."""
    details = cart_manager.get_customer_payment_details(user_id)
    return {
        "has_saved_card": details is not None,
        "payment_details": details
    }

@app.post("/api/customer/payment-details")
def save_customer_payment_details(req: SaveCustomerCardRequest):
    """Validates and saves customer payment card details."""
    val = payment_manager.validate_card_details(
        card_number=req.card_number,
        expiry_date=req.expiry_date,
        cvv=req.cvv,
        cardholder_name=req.cardholder_name
    )
    if not val["valid"]:
        raise HTTPException(status_code=400, detail=val.get("error", "Invalid card details"))
    
    saved = cart_manager.save_customer_payment_details(req.user_id, {
        "card_holder_name": val["card_holder_name"],
        "card_number_masked": val["card_number_masked"],
        "card_last4": val["card_last4"],
        "card_network": val["card_network"],
        "expiry_date": val["expiry_date"]
    })
    return saved

@app.get("/api/orders")
def get_orders(user_id: Optional[str] = None):
    """
    Returns orders list. If user_id is None or 'ALL', returns all store orders.
    Otherwise returns orders for the specified user.
    """
    if not user_id or user_id.upper() == "ALL":
        orders = order_manager.get_all_orders()
    else:
        orders = order_manager.get_orders_by_user(user_id)
    return {
        "count": len(orders),
        "orders": orders
    }

@app.get("/api/admin/orders")
def get_admin_all_orders():
    """Returns 100% of all customer and AI shopper orders for the Admin Dashboard."""
    orders = order_manager.get_all_orders()
    return {
        "count": len(orders),
        "orders": orders
    }


@app.get("/api/orders/{order_id}")
def get_order_details(order_id: str):
    order = order_manager.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/api/orders/{order_id}/refund")
def refund_order(order_id: str, reason: Optional[str] = "Customer Request"):
    """
    Issues a refund on Razorpay Gateway and updates customer account & inventory.
    """
    res = payment_manager.process_refund(order_id=order_id, reason=reason or "Customer Request")
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Refund failed"))
    return res


@app.get("/api/payment/dashboard-info")
def get_payment_dashboard_info():
    """
    Returns Razorpay dashboard links, test credentials status, and navigation guide.
    """
    return payment_manager.get_dashboard_info()

@app.get("/api/payment/ap2-status")
def get_ap2_authorization_status(user_id: str = "user_alex"):
    """
    AP2 Protocol: Check if the user has an active cryptographically signed AP2 spending mandate for autonomous agent payments.
    """
    token = cart_manager.get_ap2_payment_token(user_id)
    if PAYMENT_MODE == "demo" and token and payment_manager.verify_ap2_spending_mandate(token, 0.01)["valid"]:
        return {
            "authorized": True,
            "mandate_id": token.get("mandate_id"),
            "spending_limit": token.get("spending_limit_per_tx", 1000000.0),
            "protocol": token.get("protocol", "Google Agent Payments Protocol (AP2) v1.0"),
            "authorized_agent": token.get("authorized_agent", "nova_commerce_agent"),
            "valid_until": token.get("valid_until"),
            "card_details": token.get("card_details", {}),
            "message": f"AP2 Auto-Pay Mandate active ({token.get('mandate_id', 'Verified')}). Agent can place orders autonomously via Razorpay without checkout popups."
        }
    return {
        "authorized": False,
        "message": "AP2 not yet authorized. Complete one-time Razorpay setup via the '🔐 Authorize Auto-Pay' button."
    }


@app.post("/api/payment/ap2-save-token")
def save_ap2_token(req: AP2SaveTokenRequest):
    """
    AP2 Protocol: Manually save an AP2 authorization token after a verified Razorpay payment.
    Called by the frontend after Razorpay Checkout completes successfully.
    """
    matching = [order for order in order_manager.get_orders_by_user(req.user_id)
                if order.get("razorpay_order_id") == req.razorpay_order_id
                and order.get("razorpay_payment_id") == req.razorpay_payment_id
                and order.get("payment_details", {}).get("verified")]
    if not matching:
        raise HTTPException(status_code=400, detail="A verified payment belonging to this customer is required.")
    res = payment_manager.save_ap2_token_from_payment(
        user_id=req.user_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_order_id=req.razorpay_order_id,
        card_details=req.card_details or cart_manager.get_customer_payment_details(req.user_id) or {}
    )
    return res

@app.post("/api/payment/agent-autopay")
async def agent_autonomous_pay(req: CheckoutRequest):
    """
    AP2 Protocol: Backend endpoint for fully autonomous agent payment using stored token.
    No frontend checkout modal — payment is captured server-side.
    """
    res = await payment_manager.autonomous_agent_pay_async(user_id=req.user_id, shipping_address=req.shipping_address)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "AP2 autonomous payment failed"))
    return res

@app.post("/api/chat")
async def chat_with_agent(req: ChatRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    agent_output = await commerce_agent.run_prompt(
        prompt=req.prompt,
        user_id=req.user_id,
        conversation_history=req.conversation_history
    )
    return agent_output


@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    if req.api_key:
        commerce_agent.api_key = req.api_key
        commerce_agent._init_client()
    if req.model:
        commerce_agent.model = req.model
    return {
        "success": True,
        "message": "Settings updated",
        "current_model": commerce_agent.model
    }


# =====================================================================
# 🤖 AGENT-READABLE CATALOG & MACHINE-TO-MACHINE PROTOCOLS (UAP / ACP / AP2)
# =====================================================================

@app.get("/.well-known/agent-catalog.json")
@app.get("/api/agent-catalog")
def get_agent_readable_catalog():
    """
    Standards-compliant Agent-Readable Catalog adhering to UAP / ACP specifications.
    Enables external and local autonomous AI agents to discover inventory, price floors,
    dynamic surge states, and supported settlement rails.
    """
    products = inventory_manager.get_all_products()
    items = []
    for p in products:
        base_price = float(p.get("BASE_PRICE", p.get("PRICE", 100)))
        selling_price = float(p.get("PRICE", base_price))
        items.append({
            "@context": "https://schema.org",
            "@type": "Product",
            "product_id": p.get("id"),
            "name": p.get("PRODUCT_NAME"),
            "category": p.get("PRODUCT_TYPE"),
            "description": p.get("DESCRIPTION"),
            "image": p.get("IMAGE"),
            "offers": {
                "@type": "Offer",
                "price": selling_price,
                "priceCurrency": "INR",
                "taxRate": 0.0,
                "priceFloor": base_price,
                "availability": "https://schema.org/InStock" if p.get("STOCK_REMAINING", 0) > 0 else "https://schema.org/OutOfStock",
                "itemCondition": "https://schema.org/NewCondition"
            },
            "inventory": {
                "units_available": p.get("STOCK_REMAINING", 0)
            },
            "policies": {
                "refund_window_hours": 24,
                "shipping_coverage": "India Standard (0% Tax)",
                "payment_rails": ["AP2_MANDATE", "RAZORPAY_INR"]
            }
        })
    return {
        "protocol": "UAP/ACP/AP2",
        "version": "1.0",
        "store_name": "Nova: Agentic AI Store",
        "currency": "INR",
        "tax_policy": "0% Tax Storewide",
        "merchant_endpoints": {
            "catalog": "/api/inventory",
            "quote": "/api/cart",
            "autonomous_checkout": "/api/payment/agent-autopay",
            "conversational_checkout": "/api/chat/conversational-checkout",
            "razorpay_checkout": "/api/payment/create-order",
            "cross_sells": "/api/cart/cross-sells"
        },
        "item_count": len(items),
        "products": items
    }


@app.get("/.well-known/ap2-manifest.json")
def get_ap2_manifest():
    """Manifest specification for Agentic Payments Protocol (AP2)."""
    return {
        "protocol": "AP2",
        "version": "2.4",
        "issuer": "Nova: Agentic AI Store",
        "supported_currencies": ["INR"],
        "mandate_limits": {
            "max_single_transaction_inr": 25000.0,
            "daily_cap_inr": 100000.0,
            "require_signature": True
        },
        "settlement_rails": ["RAZORPAY_TEST_MODE", "TOKENIZED_MANDATE"],
        "security_gates": {
            "base_price_floor_enforcement": True,
            "refund_window_hours": 24,
            "pre_shipment_only": True
        }
    }


# =====================================================================
# 📦 UPSELL & CROSS-SELL AGENT ENDPOINTS
# =====================================================================

@app.get("/api/cart/cross-sells")
def get_cart_cross_sells(user_id: str = "user_alex"):
    """
    Returns explainable, margin-preserving cross-sell accessory recommendations
    tailored to items currently in the customer's cart.
    """
    cart = cart_manager.get_cart(user_id)
    cart_items = cart.get("items", [])
    recommendations = upsell_agent.get_recommendations_for_cart(cart_items, limit=3)
    return {
        "success": True,
        "recommendations": recommendations,
        "count": len(recommendations)
    }


# =====================================================================
# ⚡ PROMOTIONAL CAMPAIGN ORCHESTRATOR ENDPOINTS
# =====================================================================

@app.get("/api/campaigns/active")
def get_active_campaign():
    """Returns current active promotional flash sale campaign."""
    campaign = campaign_orchestrator.get_active_campaign()
    return {"success": True, "campaign": campaign}


@app.get("/api/admin/campaigns")
def get_admin_campaigns():
    """Returns all promotional marketing campaigns."""
    return {
        "success": True,
        "campaigns": campaign_orchestrator.get_all_campaigns()
    }


class LaunchCampaignRequest(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "ALL"
    discount_percent: float = Field(default=10.0, ge=1, le=25)
    duration_hours: int = Field(default=24, gt=0, le=8760)


@app.post("/api/admin/campaigns/launch")
def launch_admin_campaign(req: LaunchCampaignRequest):
    """Launches or schedules a promotional campaign bounded by base price floors."""
    res = campaign_orchestrator.launch_campaign(
        title=req.title,
        category=req.category,
        discount_percent=req.discount_percent,
        duration_hours=req.duration_hours,
        auto_activate=True
    )
    return res

@app.post("/api/admin/campaigns/{campaign_id}/activate")
def activate_admin_campaign(campaign_id: str):
    """Activates a campaign ensuring at most 1 active campaign per category."""
    res = campaign_orchestrator.activate_campaign(campaign_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to activate campaign"))
    return res

@app.post("/api/admin/campaigns/{campaign_id}/stop")
def stop_admin_campaign(campaign_id: str):
    """Stops an active campaign and restores baseline pricing."""
    res = campaign_orchestrator.stop_campaign(campaign_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to stop campaign"))
    return res

@app.delete("/api/admin/campaigns/{campaign_id}")
def delete_admin_campaign(campaign_id: str):
    """Deletes a promotional campaign."""
    res = campaign_orchestrator.delete_campaign(campaign_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to delete campaign"))
    return res



# =====================================================================
# 💬 IN-APP CONVERSATIONAL CHECKOUT (AP2 TOKENIZED DIRECT SETTLEMENT)
# =====================================================================

class ConversationalCheckoutRequest(RequestModel):
    user_id: str = "user_alex"
    payment_method: str = "AP2"
    shipping_address: Optional[str] = None


@app.post("/api/chat/conversational-checkout")
def conversational_checkout(req: ConversationalCheckoutRequest):
    """
    Executes in-app conversational checkout directly from the chat copilot
    using the customer's AP2 tokenized mandate without frontend popups.
    """
    cart = cart_manager.get_cart(req.user_id)
    if not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cannot checkout: Cart is empty.")
    
    total = float(cart.get("estimated_total", 0.0))
    MAX_AP2_BOUND = 25000.0
    if total > MAX_AP2_BOUND:
        raise HTTPException(
            status_code=400,
            detail=f"Order total ₹{total:,.2f} exceeds AP2 single mandate safety limit of ₹{MAX_AP2_BOUND:,.2f}. Please use standard Razorpay checkout."
        )

    res = payment_manager.autonomous_agent_pay(
        user_id=req.user_id,
        shipping_address=req.shipping_address or cart_manager.get_customer_address(req.user_id)
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "AP2 conversational checkout failed."))
    
    order = res.get("order", {})
    return {
        "success": True,
        "order_id": order.get("order_id"),
        "total": order.get("total", total),
        "tracking_number": order.get("tracking_number", "TRK-AP2-DIRECT"),
        "message": f"Order {order.get('order_id')} confirmed via 1-click AP2 Protocol! ₹{total:,.2f} captured on Razorpay rails."
    }


# =====================================================================
# 🛡️ EXPLAINABLE AUDIT TRAIL & GRACEFUL FAILURE HANDLING
# =====================================================================

@app.get("/api/admin/audit-trail")
def get_audit_trail():
    """
    Returns an immutable chronological audit trail where every financial transaction
    is explainable, bounded, and gated.
    """
    transactions = treasury_manager.get_transactions()
    audited_trail = []
    for tx in transactions:
        audited_trail.append({
            "timestamp": tx.get("timestamp"),
            "transaction_id": tx.get("id") or f"TX_{abs(hash(str(tx.get('timestamp')))) % 1000000}",
            "type": tx.get("type"),
            "amount": float(tx.get("amount", 0.0)),
            "balance_after": float(tx.get("balance_after", 0.0)),
            "actor": tx.get("actor") or "Autonomous Engine",
            "explainability": tx.get("description") or "Wholesale base acquisition or customer sales revenue.",
            "is_bounded": True,
            "policy_gate": "0% Tax Storewide / Base Price Floor / 24h Refund"
        })
    return {
        "success": True,
        "total_actions": len(audited_trail),
        "audit_trail": audited_trail
    }


class FailureSimulationRequest(RequestModel):
    failure_type: str  # "AP2_OVERSPEND" | "EXPIRED_REFUND" | "BASE_FLOOR_BREACH"


@app.post("/api/simulation/failure-test")
def simulate_failure_mode(req: FailureSimulationRequest):
    """
    Demonstrates graceful, explainable failure handling for financial edge cases.
    """
    if req.failure_type == "AP2_OVERSPEND":
        attempted_amount = 38500.0
        max_bound = 25000.0
        return {
            "success": False,
            "status": "BOUNDED_REJECTION",
            "attempted_action": f"AP2 Autonomous Tokenized Payment of ₹{attempted_amount:,.2f}",
            "error_code": "AP2_MANDATE_LIMIT_EXCEEDED",
            "message": f"Transaction rejected safely: Attempted ₹{attempted_amount:,.2f} exceeds user's pre-approved mandate cap of ₹{max_bound:,.2f}.",
            "explainability": "Financial safety bound enforced. System refuses un-gated credit expansion without interactive multi-factor re-authorization.",
            "graceful_recovery": "Fallback to standard Razorpay OTP checkout presented to user."
        }

    elif req.failure_type == "EXPIRED_REFUND":
        return {
            "success": False,
            "status": "GATED_REJECTION",
            "attempted_action": "Automated 1-Click Refund Processing",
            "error_code": "REFUND_WINDOW_EXPIRED",
            "message": "Refund request rejected safely: Order age exceeds 24-hour non-shipped policy threshold and tracking is active in transit.",
            "explainability": "Merchant governance policy forbids automated stock deduction after carrier dispatch to prevent inventory discrepancy.",
            "graceful_recovery": "Option provided for manual Store Owner exception override in Owner Studio."
        }

    elif req.failure_type == "BASE_FLOOR_BREACH":
        attempted_price = 299.0
        base_floor = 450.0
        clamped_price = max(base_floor, attempted_price)
        return {
            "success": True,
            "status": "BOUNDED_ENFORCEMENT",
            "attempted_action": f"Price Manager Discount to ₹{attempted_price:.2f}",
            "base_floor": f"₹{base_floor:.2f}",
            "clamped_price": f"₹{clamped_price:.2f}",
            "message": f"Breach prevented: Requested price ₹{attempted_price:.2f} was below wholesale base floor ₹{base_floor:.2f}. Clamped to ₹{clamped_price:.2f}.",
            "explainability": "The Store Owner locks the Base Price Floor as an immutable constraint. Margin cannot be negative.",
            "graceful_recovery": "Selling price automatically protected at zero margin risk."
        }

    raise HTTPException(status_code=400, detail=f"Unknown failure test type: {req.failure_type}")


class AdminChatRequest(RequestModel):
    prompt: str = Field(min_length=1, max_length=10000)
    conversation_history: Optional[List[Dict[str, str]]] = None

class AdminInventoryUpdateRequest(RequestModel):
    product_id: str
    stock: Optional[int] = Field(default=None, ge=0, strict=True)
    price: Optional[float] = Field(default=None, gt=0)
    base_price: Optional[float] = Field(default=None, ge=0)

class AdminProductAddRequest(RequestModel):
    PRODUCT_NAME: str
    PRODUCT_TYPE: str = "Accessories"
    PRODUCT_SIZE: str = "One Size"
    STOCK_REMAINING: int = Field(default=15, ge=0, strict=True)
    BASE_PRICE: Optional[float] = Field(default=None, ge=0)
    PRICE: float = Field(default=49.99, gt=0)
    DESCRIPTION: str = ""
    IMAGE: Optional[str] = "/static/images/cyberflex_runner.svg"
    TAGS: List[str] = Field(default_factory=list)

class AdminBulkPriceRequest(RequestModel):
    category: Optional[str] = None
    percentage: float = Field(gt=-100, le=1000)

class AdminOrderStatusUpdateRequest(RequestModel):
    status: str
    tracking_number: Optional[str] = None
    notes: Optional[str] = None

class AdminOrderCancelRequest(RequestModel):
    reason: Optional[str] = "Customer Request"
    force_override: bool = False

class AdminReviewAddRequest(RequestModel):
    product_id: str
    customer_name: str
    rating: int = Field(default=5, ge=1, le=5, strict=True)
    review_text: str
    product_name: Optional[str] = None

class AdminGenerateReviewSummaryRequest(RequestModel):
    product_id: str

class AdminAgentTriggerRequest(RequestModel):
    agent_key: str

class AdminAgentIntervalRequest(RequestModel):
    agent_key: str
    interval_seconds: int = Field(ge=5, le=86400)

class AdminAcquireStockRequest(RequestModel):
    product_id: str
    quantity: int = Field(default=20, gt=0, le=10000, strict=True)
    actor: Optional[str] = "Store Owner"

class AdminResetTreasuryRequest(RequestModel):
    bank_balance: Optional[float] = None

class AdminNegotiateSalaryRequest(RequestModel):
    agent_name: str
    proposed_salary: float
    rationale: Optional[str] = "Performance and store growth review"

class AdminPaySalaryRequest(RequestModel):
    agent_name: Optional[str] = None
    actor: Optional[str] = "Store Owner"

class AdminUpdateSalaryRequest(RequestModel):
    agent_name: str
    new_salary: float
    status: Optional[str] = "Agreed"

class AdminBuyerTriggerRequest(RequestModel):
    buyer_id: str = "buyer_alex"

class AdminBuyerToggleRequest(RequestModel):
    enabled: Optional[bool] = None

class AdminCEODiscussionRequest(RequestModel):
    topic: str
    participants: Optional[str] = "ALL_AGENTS"


@app.get("/api/admin/overview")
def get_admin_overview():
    """Returns comprehensive KPIs, revenue, order breakdown, and stock metrics."""
    orders = order_manager.get_all_orders()
    products = inventory_manager.get_all_products()
    reviews = review_manager.get_all_reviews()
    agent_status = background_worker.get_status()

    total_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
    
    # Status breakdown
    status_counts = {}
    for o in orders:
        st = o.get("status", "Confirmed")
        status_counts[st] = status_counts.get(st, 0) + 1

    low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]
    out_of_stock = [p for p in products if p.get("STOCK_REMAINING", 0) == 0]

    # Total autonomous actions
    total_actions = sum(a.get("actions_count", 0) for a in agent_status.get("agents", {}).values())

    return {
        "success": True,
        "kpis": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": len(orders),
            "active_orders": sum(status_counts.get(st, 0) for st in ["Pending", "Confirmed", "Dispatched", "Shipped"]),
            "delivered_orders": status_counts.get("Delivered", 0),
            "refunded_orders": status_counts.get("Refunded", 0),
            "cancelled_orders": status_counts.get("Cancelled", 0),
            "total_products": len(products),
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
            "total_reviews": len(reviews),
            "agent_autonomous_actions": total_actions
        },
        "status_breakdown": status_counts,
        "low_stock_items": low_stock[:6]
    }

@app.get("/api/admin/agents/status")
def get_admin_agents_status():
    """Returns live telemetry for all 6 autonomous agents and their independent schedules."""
    return background_worker.get_status()

@app.post("/api/admin/agents/trigger")
async def trigger_admin_agent(req: AdminAgentTriggerRequest):
    """Fires an instant autonomous execution cycle for an agent (non-blocking fire-and-forget)."""
    agent_key = req.agent_key
    state = background_worker.agent_states.get(agent_key)
    if not state:
        raise HTTPException(status_code=404, detail=f"Unknown agent: '{agent_key}'")
    # Reset last_run_ts so the background loop picks it up on next tick
    state["last_run_ts"] = 0.0
    # Fire-and-forget: schedule the cycle as a background task so HTTP returns immediately
    from backend.admin_agents import log_agent_action
    log_agent_action(state.get("name", agent_key), "Cycle queued", "Manual run requested from the operations console.", autonomous=False)
    task = asyncio.create_task(background_worker.trigger_agent(agent_key))
    app.state.manual_tasks.add(task)
    task.add_done_callback(app.state.manual_tasks.discard)
    return {
        "success": True,
        "agent": agent_key,
        "message": f"Triggered '{state.get('name', agent_key)}' — executing in background.",
        "status": "QUEUED"
    }

@app.post("/api/admin/agents/interval")
def update_admin_agent_interval(req: AdminAgentIntervalRequest):
    """Dynamically updates the schedule interval for an admin agent (e.g. 120 for 2m, 300 for 5m, 7200 for 2h)."""
    res = background_worker.update_agent_interval(req.agent_key, req.interval_seconds)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Update failed"))
    return res

@app.get("/api/admin/agent-logs")
def get_admin_agent_logs(limit: int = 60):
    """Returns recent 24/7 autonomous agent audit log entries."""
    from backend.admin_agents import get_agent_logs as fetch_agent_logs
    logs = fetch_agent_logs(limit=limit)
    return {"logs": logs, "count": len(logs)}

@app.get("/api/admin/agent-memory")
def get_admin_agent_memory(agent_name: Optional[str] = None):
    """Returns the 5-layer Hybrid Layered Memory state for all agents or a specific agent."""
    from backend.agent_memory import memory_manager
    if agent_name:
        return {"agent": agent_name, "memory": memory_manager.get_memory_report(agent_name)}
    return {"fleet_memory": memory_manager.get_all_memories_report()}

@app.get("/api/admin/agent-rl")
def get_admin_agent_rl(agent_name: Optional[str] = None):
    """Returns the Reinforcement Learning (RL) performance report and Q-learning metrics."""
    from backend.agent_rl import rl_manager
    if agent_name:
        pol = rl_manager.get_policy(agent_name)
        return {"agent": agent_name, "policy": pol.to_dict()}
    return {"fleet_rl": rl_manager.get_fleet_performance_report()}

@app.post("/api/admin/inventory/update")
def admin_update_inventory(req: AdminInventoryUpdateRequest):
    """Directly modifies stock, price, or base_price for a product."""
    updated = {}
    if req.stock is not None:
        stock_res = inventory_manager.update_stock(req.product_id, req.stock)
        updated["stock"] = stock_res
    if req.base_price is not None and req.price is None:
        # Only base_price sent — update BASE_PRICE floor without touching PRICE
        price_res = inventory_manager.update_base_price(
            product_id=req.product_id,
            new_base_price=req.base_price
        )
        updated["price"] = price_res
    elif req.price is not None:
        # Both or price-only update — enforce base_price floor on PRICE
        price_res = inventory_manager.update_price(
            product_id=req.product_id,
            new_price=req.price,
            base_price=req.base_price,
            enforce_base_price=True
        )
        updated["price"] = price_res
    for change in updated.values():
        if not change.get("success"):
            raise HTTPException(status_code=400, detail=change.get("error", "Inventory update failed"))
    return {"success": True, "updated": updated}

@app.post("/api/admin/inventory/add")
def admin_add_product(req: AdminProductAddRequest):
    """Adds a new product to catalog."""
    res = inventory_manager.add_product(req.model_dump())
    return res

@app.post("/api/admin/inventory/bulk-price")
def admin_bulk_price(req: AdminBulkPriceRequest):
    """Applies bulk percentage discount or increase."""
    res = inventory_manager.bulk_price_adjustment(category=req.category, percentage=req.percentage)
    return res

@app.post("/api/admin/orders/{order_id}/status")
def admin_update_order_status(order_id: str, req: AdminOrderStatusUpdateRequest):
    """Updates order status across the lifecycle."""
    res = order_manager.update_order_status(
        order_id=order_id,
        new_status=req.status,
        tracking_number=req.tracking_number,
        notes=req.notes
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Status update failed"))
    return res

@app.post("/api/admin/orders/{order_id}/cancel")
async def admin_cancel_order(order_id: str, req: AdminOrderCancelRequest):
    """
    Evaluates strict 24-hour and non-shipped refund rule for order cancellation.
    If eligible, processes automated Razorpay refund and stock restoration.
    """
    if req.force_override:
        res = await asyncio.to_thread(payment_manager.process_refund, order_id=order_id, reason=req.reason or "Owner refund", force_override=True)
    else:
        res = order_manager.evaluate_24h_cancellation_and_refund(order_id=order_id, reason=req.reason)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Cancellation failed"))
    return res

@app.get("/api/admin/reviews")
def admin_get_reviews():
    """Returns all verified customer reviews."""
    return {"reviews": review_manager.get_all_reviews()}

@app.post("/api/admin/reviews/add")
def admin_add_review(req: AdminReviewAddRequest):
    """Adds a customer review."""
    res = review_manager.add_review(
        product_id=req.product_id,
        customer_name=req.customer_name,
        rating=req.rating,
        review_text=req.review_text,
        product_name=req.product_name
    )
    return res

@app.post("/api/admin/reviews/generate-summary")
async def admin_generate_review_summary(req: AdminGenerateReviewSummaryRequest):
    """Triggers Ollama AI review summary generation for a product."""
    res = await review_manager.generate_ai_review_summary(req.product_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Summary generation failed"))
    return res

@app.get("/api/admin/agent-messages")
def get_agent_messages(limit: int = 50):
    """Returns the inter-agent message bus history for admin dashboard visibility."""
    return {
        "messages": message_bus.get_all_messages(limit=limit),
        "inbox_snapshot": message_bus.get_inbox_snapshot()
    }

@app.get("/api/admin/agent-conversations")
def get_admin_agent_conversations(agent_name: Optional[str] = None, limit: int = 20):
    """Returns conversation and instruction history for all agents or a specific specialist agent."""
    from backend.admin_agents import conversation_history
    if agent_name:
        return {"agent": agent_name, "conversations": conversation_history.get(agent_name, limit=limit)}
    return {"conversations": conversation_history.get_all(limit_per_agent=limit)}

@app.get("/api/admin/ceo/report")
async def get_ceo_report():
    """Triggers the CEO Agent to generate an on-demand strategic report for the Owner."""
    report = await ceo_agent.generate_owner_report()
    return report

@app.post("/api/admin/chat")
async def admin_chat(req: AdminChatRequest):
    """Owner Direct AI Command Center endpoint — directly consults and commands CEO Agent (No Middleman)."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    output = await admin_chat_agent.run_prompt(
        prompt=req.prompt,
        conversation_history=req.conversation_history
    )
    return output


# =====================================================================
# 💰 TREASURY & WHOLESALE INVENTORY ACQUISITION ENDPOINTS
# =====================================================================

@app.get("/api/admin/treasury")
def get_treasury_summary(limit: int = 30):
    """Returns live Treasury Bank Balance, sales revenues, inventory spend, salary payouts, and net profit."""
    summary = treasury_manager.get_summary()
    transactions = treasury_manager.get_transactions(limit=limit)
    summary["transactions"] = transactions
    return summary

@app.post("/api/admin/treasury/acquire-stock")
def admin_acquire_stock(req: AdminAcquireStockRequest):
    """Acquires inventory stock at wholesale BASE_PRICE using CEO Treasury Bank Balance."""
    res = inventory_manager.acquire_wholesale_stock(
        product_identifier=req.product_id,
        quantity=req.quantity,
        actor=req.actor or "Store Owner"
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Stock acquisition failed"))
    return res

@app.post("/api/admin/treasury/reset")
def admin_reset_treasury(req: AdminResetTreasuryRequest):
    """Resets the store treasury bank balance."""
    res = treasury_manager.reset_treasury(req.bank_balance)
    return res


# =====================================================================
# 💼 AGENT SALARY MANAGEMENT & INTERACTIVE NEGOTIATION ENDPOINTS
# =====================================================================

@app.get("/api/admin/salaries")
def get_agent_salaries():
    """Returns salary breakdown, performance metrics, and negotiation status for all specialist agents."""
    return salary_manager.get_all_salaries()

@app.post("/api/admin/salaries/negotiate")
async def negotiate_agent_salary(req: AdminNegotiateSalaryRequest):
    """Interactive multi-agent salary negotiation with AI agents formulating reasoned counter-offers."""
    res = await salary_manager.negotiate_salary(
        agent_name=req.agent_name,
        proposed_salary=req.proposed_salary,
        rationale=req.rationale or "Performance review",
        speaker="Store Owner / CEO"
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Negotiation failed"))
    return res

@app.post("/api/admin/salaries/pay")
def pay_agent_salaries(req: AdminPaySalaryRequest):
    """Disburses salary payments to specialist agents from the CEO Treasury Bank Balance."""
    res = salary_manager.pay_salaries(agent_name=req.agent_name, actor=req.actor or "Store Owner")
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Payroll disbursal failed"))
    return res

@app.post("/api/admin/salaries/update")
def update_agent_salary(req: AdminUpdateSalaryRequest):
    """Directly sets an agent's salary amount."""
    res = salary_manager.update_agent_salary(agent_name=req.agent_name, new_salary=req.new_salary, status=req.status or "Agreed")
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Salary update failed"))
    return res


# =====================================================================
# 🛍️ 5 AI AUTONOMOUS BUYER AGENTS ENDPOINTS
# =====================================================================

@app.get("/api/admin/buyers")
def get_ai_buyers():
    """Returns all 5 AI buyer personas, activity statuses, total spent, and preferences."""
    buyers = buyer_agents_fleet.get_all_buyers()
    return {
        "success": True,
        "count": len(buyers),
        "buyers": buyers
    }

@app.post("/api/admin/buyers/trigger")
async def trigger_ai_buyer(req: AdminBuyerTriggerRequest):
    """Fires an autonomous shopping cycle for a buyer (non-blocking fire-and-forget)."""
    b_id = req.buyer_id.lower().strip()
    async def _fire():
        try:
            if b_id in ["all", "all_buyers", "everyone"]:
                await buyer_agents_fleet.run_all_buyers_step()
            else:
                await buyer_agents_fleet.execute_buyer_step(b_id)
        except Exception as e:
            print(f"[BuyerTrigger] Background error: {e}", flush=True)
    asyncio.create_task(_fire())
    return {
        "success": True,
        "buyer_id": b_id,
        "message": f"AI buyer '{b_id}' cycle queued — executing in background.",
        "status": "QUEUED"
    }

@app.post("/api/admin/buyers/toggle")
def toggle_ai_buyers(req: AdminBuyerToggleRequest):
    """Enables or disables 24/7 background autonomous buyer simulation."""
    b_state = background_worker.agent_states.get("buyer_agents", {})
    if req.enabled is not None:
        b_state["enabled"] = req.enabled
    else:
        b_state["enabled"] = not b_state.get("enabled", True)
    return {
        "success": True,
        "enabled": b_state["enabled"],
        "message": f"Autonomous Buyer Simulation is now {'ENABLED' if b_state['enabled'] else 'PAUSED'}."
    }

class AdminBuyerIntervalRequest(RequestModel):
    buyer_id: Optional[str] = "all"
    interval_seconds: int = 60

@app.post("/api/admin/buyers/interval")
def update_ai_buyer_interval(req: AdminBuyerIntervalRequest):
    """Updates browsing schedule interval for AI buyers fleet or a specific buyer."""
    interval_sec = max(5, int(req.interval_seconds))
    background_worker.update_agent_interval("buyer_agents", interval_sec)
    b_id = (req.buyer_id or "all").lower().strip()
    buyers = buyer_agents_fleet.get_all_buyers()
    if b_id in ["all", "all_buyers"]:
        for b in buyers:
            b["interval_seconds"] = interval_sec
            b["next_action_ts"] = time.time() + interval_sec
    else:
        buyer = next((b for b in buyers if b["id"] == b_id), None)
        if not buyer:
            raise HTTPException(status_code=404, detail="Buyer not found")
        if buyer:
            buyer["interval_seconds"] = interval_sec
            buyer["next_action_ts"] = time.time() + interval_sec
    buyer_agents_fleet._write_buyers(buyers)
    return {
        "success": True,
        "buyer_id": req.buyer_id,
        "interval_seconds": interval_sec,
        "message": f"AI Buyer shopping interval updated to {interval_sec}s."
    }



# =====================================================================
# 👔 CEO MULTI-AGENT ROUNDTABLE DISCUSSION ENDPOINTS
# =====================================================================

@app.post("/api/admin/ceo/discussion")
async def start_ceo_discussion(req: AdminCEODiscussionRequest):
    """Convenes a strategic CEO roundtable discussion with specialist agents."""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Discussion topic cannot be empty")
    res = await ceo_agent.conduct_ceo_discussion(topic=req.topic, participants=req.participants or "ALL_AGENTS")
    return res

@app.post("/api/admin/reset-store")
@serialized
def reset_store_complete():
    """
    Resets the store to initial clean state:
    1. Sets all 27 products inventory stock to 0 STOCK (wholesale restock required).
    2. Resets all orders to empty.
    3. Resets customer reviews to empty.
    4. Resets Treasury Bank Balance to default ₹1,000.0.
    5. Resets specialist agent salaries to CEO base ₹50.0 / 100 cycles with 0 total earned.
    6. Resets all 5 AI buyers with staggered random 0-5m purchase schedules.
    7. Clears all active shopping carts.
    8. Clears message bus history, agent inboxes, conversation turns, and audit logs.
    """
    from backend.admin_agents import conversation_history, LOGS_FILE, _log_lock

    # 1. Reset inventory to 0 stock
    products = inventory_manager.get_all_products()
    for p in products:
        p["STOCK_REMAINING"] = 0
        base_p = float(p.get("BASE_PRICE") or 10.0)
        p["PRICE"] = round(base_p * 1.25, 2)
    inventory_manager._write_inventory(products)

    # 2. Reset orders
    order_manager._write_orders([])

    # 3. Reset customer reviews
    review_manager._write_reviews([])

    # 4. Reset treasury to 10000.0
    treasury_manager.reset_treasury(new_balance=10000.0)

    # 5. Reset salaries
    salary_manager.reset_salaries()

    # 6. Reset buyers with staggered 0-5m countdowns
    buyer_agents_fleet.reset_buyers()

    # 7. Clear carts
    users = cart_manager._read_users()
    for user in users:
        user["cart"] = []
        user.pop("ap2_payment_token", None)
    cart_manager._write_users(users)
    campaign_orchestrator.store.set([])
    payment_manager._intents.set({})

    # 8. Clear message bus, conversation history, and audit logs
    message_bus.clear_history()
    conversation_history.clear()
    task_manager.clear()
    idempotency_manager.clear()

    with _log_lock:
        try:
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass

    return {
        "success": True,
        "bank_balance": 10000.0,
        "message": "Store successfully reset: All 27 products at 0 stock (Wholesale restock required), Orders & Reviews cleared, Bank Balance reset to ₹10,000.0, Staff Salaries reset to ₹50/100 cycles, and AI Shoppers staggered across 0–5 minutes."
    }


# =====================================================================
# 📋 AGENT TASKS & DELEGATION ENDPOINTS
# =====================================================================

class CreateTaskRequest(RequestModel):
    created_by: str = "Store Owner"
    assigned_to: str
    objective: str
    priority: str = "normal"
    constraints: Optional[List[str]] = None
    deadline: Optional[str] = None

class ClaimTaskRequest(RequestModel):
    task_id: str
    agent_name: str

class CompleteTaskRequest(RequestModel):
    task_id: str
    result: Any

@app.get("/api/admin/tasks")
def get_agent_tasks(assigned_to: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    """Returns agent tasks with optional filtering."""
    tasks = task_manager.get_tasks(assigned_to=assigned_to, status=status, limit=limit)
    return {"success": True, "count": len(tasks), "tasks": tasks}

@app.post("/api/admin/tasks")
def create_agent_task(req: CreateTaskRequest):
    """Creates a new structured agent delegation task."""
    task = task_manager.create_task(
        created_by=req.created_by,
        assigned_to=req.assigned_to,
        objective=req.objective,
        priority=req.priority,
        constraints=req.constraints,
        deadline=req.deadline
    )
    return {"success": True, "task": task.to_dict()}

@app.post("/api/admin/tasks/claim")
def claim_agent_task(req: ClaimTaskRequest):
    task = task_manager.claim_task(req.task_id, req.agent_name)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not in pending state")
    return {"success": True, "task": task.to_dict()}

@app.post("/api/admin/tasks/complete")
def complete_agent_task(req: CompleteTaskRequest):
    task = task_manager.complete_task(req.task_id, req.result)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task.to_dict()}


# =====================================================================
# 📊 OBSERVABILITY & ALERT AGGREGATION ENDPOINTS
# =====================================================================

@app.get("/api/admin/observability/metrics")
def get_observability_metrics():
    """Returns execution metrics, failure counts, and latency averages per tool."""
    return {"success": True, "metrics": observability_manager.get_tool_metrics()}

@app.get("/api/admin/observability/alerts")
def get_observability_alerts(timeframe_seconds: float = 3600.0):
    """Returns aggregated executive alert summaries."""
    return {"success": True, "alerts": observability_manager.aggregate_alerts(timeframe_seconds)}

@app.get("/api/admin/observability/activity")
def get_observability_activity(limit: int = 50, agent_name: Optional[str] = None):
    return {"success": True, "activity": observability_manager.get_agent_activity(limit, agent_name)}


# =====================================================================
# 🛡️ POLICY ENGINE & INVARIANT VALIDATION ENDPOINTS
# =====================================================================

class ValidatePolicyRequest(RequestModel):
    action: str
    actor: str
    resource: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

@app.post("/api/admin/policy/validate")
def validate_policy_endpoint(req: ValidatePolicyRequest):
    """Validates an action against deterministic policy rules."""
    res = validate_policy(
        action=req.action,
        actor=req.actor,
        resource=req.resource,
        parameters=req.parameters
    )
    return res

@app.get("/api/admin/qa/invariants")
def validate_qa_invariants():
    """Continuous integration invariant validation check across catalog, treasury, and orders."""
    res = buyer_agents_fleet.validate_business_invariants()
    return res

@app.get("/api/admin/qa/report")
def get_qa_report():
    """Generates continuous QA testing report."""
    res = buyer_agents_fleet.generate_test_report()
    return res


# =====================================================================
# 🔮 STRATEGIC DECISION SIMULATION ENDPOINTS
# =====================================================================

class SimulateDecisionRequest(RequestModel):
    scenario: str
    assumptions: Optional[Dict[str, Any]] = None

@app.post("/api/admin/simulation/decision")
def simulate_decision_endpoint(req: SimulateDecisionRequest):
    """Simulates business decision impact on revenue, margins, and turnover."""
    res = ceo_agent.simulate_business_decision(req.scenario, req.assumptions)
    return res


@app.get("/")
def root():
    return {"name": "Nova Backend", "service": "api", "docs": "/docs", "health": "/api/health",
            "frontend": os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")}
