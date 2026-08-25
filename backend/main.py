from dotenv import load_dotenv
load_dotenv()

import os
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.agent import commerce_agent
from backend.payment_manager import payment_manager
from backend.review_manager import review_manager
from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent,
    admin_chat_agent,
    message_bus,
    # Legacy aliases for backward compatibility
    order_manager_agent,
    refund_manager_agent
)
from backend.background_workers import background_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start 24/7 autonomous background fleet
    background_worker.start()
    yield
    # Graceful shutdown
    background_worker.stop()

app = FastAPI(title="AI Growth Commerce Agentic Store", version="1.0.0", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Ensure static folders exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "images"), exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

# Request Models
class ChatRequest(BaseModel):
    user_id: str = "user_alex"
    prompt: str
    conversation_history: Optional[List[Dict[str, str]]] = None

class AddToCartRequest(BaseModel):
    user_id: str = "user_alex"
    product_id: str
    quantity: int = 1
    size: Optional[str] = None

class RemoveFromCartRequest(BaseModel):
    user_id: str = "user_alex"
    product_id: str
    quantity: Optional[int] = None

class CheckoutRequest(BaseModel):
    user_id: str = "user_alex"
    shipping_address: Optional[str] = None
    payment_method: str = "Razorpay Gateway (Online)"

class RazorpayCreateOrderRequest(BaseModel):
    user_id: str = "user_alex"
    currency: str = "INR"

class RazorpayVerifyPaymentRequest(BaseModel):
    user_id: str = "user_alex"
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    shipping_address: Optional[str] = None

class RazorpayCredentialsRequest(BaseModel):
    key_id: str
    key_secret: str

class CardPaymentRequest(BaseModel):
    user_id: str = "user_alex"
    card_number: str
    expiry_date: str
    cvv: str
    cardholder_name: str
    shipping_address: Optional[str] = None
    currency: str = "INR"

class SaveCustomerCardRequest(BaseModel):
    user_id: str = "user_alex"
    card_number: str
    expiry_date: str
    cvv: str
    cardholder_name: str

class AP2SaveTokenRequest(BaseModel):
    user_id: str = "user_alex"
    razorpay_payment_id: str
    razorpay_order_id: str
    card_details: Optional[Dict[str, Any]] = None

class SettingsRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None

# API Endpoints

@app.get("/api/user")
async def get_user_profile(user_id: str = "user_alex"):
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
async def get_inventory(
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
async def get_product(product_id: str):
    product = inventory_manager.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.get("/api/cart")
async def get_cart(user_id: str = "user_alex"):
    cart = cart_manager.get_cart(user_id)
    return cart

@app.post("/api/cart/add")
async def add_to_cart(req: AddToCartRequest):
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
async def remove_from_cart(req: RemoveFromCartRequest):
    result = cart_manager.remove_from_cart(
        user_id=req.user_id,
        product_identifier=req.product_id,
        quantity=req.quantity
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove from cart"))
    return result

@app.post("/api/cart/clear")
async def clear_cart(user_id: str = "user_alex"):
    result = cart_manager.clear_cart(user_id)
    return result

@app.post("/api/checkout")
async def checkout(req: CheckoutRequest):
    result = order_manager.create_order_from_cart(
        user_id=req.user_id,
        shipping_address=req.shipping_address,
        payment_method=req.payment_method
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Checkout failed"))
    return result

# Razorpay Payment Gateway Endpoints

@app.get("/api/payment/config")
async def get_payment_config():
    """Returns the active Razorpay Key ID for client-side checkout popup."""
    return {
        "key_id": payment_manager.get_public_key_id(),
        "gateway": "Razorpay"
    }

@app.post("/api/payment/create-order")
async def create_razorpay_order(req: RazorpayCreateOrderRequest):
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
    order_data["cart"] = cart
    return order_data

@app.post("/api/payment/verify")
async def verify_razorpay_payment(req: RazorpayVerifyPaymentRequest):
    """
    Verifies Razorpay HMAC signature, deducts stock, and records the confirmed order.
    """
    is_valid = payment_manager.verify_payment_signature(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Razorpay signature verification failed. Invalid payment.")

    # Payment is authentic! Confirm order & deduct stock
    order_result = order_manager.create_order_from_cart(
        user_id=req.user_id,
        shipping_address=req.shipping_address,
        payment_method="Razorpay Gateway (Online)",
        payment_details={
            "razorpay_order_id": req.razorpay_order_id,
            "razorpay_payment_id": req.razorpay_payment_id,
            "verified": True
        }
    )
    if not order_result.get("success"):
        raise HTTPException(status_code=400, detail=order_result.get("error", "Failed to finalize order."))

    # AP2 Protocol: Save payment token for future autonomous agent payments
    # After the first verified Razorpay checkout, agent can auto-pay without any human popup
    saved_card = cart_manager.get_customer_payment_details(req.user_id) or {}
    payment_manager.save_ap2_token_from_payment(
        user_id=req.user_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_order_id=req.razorpay_order_id,
        card_details=saved_card
    )

    return {
        "success": True,
        "message": f"Payment {req.razorpay_payment_id} verified successfully via Razorpay! AP2 auto-pay token saved.",
        "order": order_result.get("order"),
        "razorpay_payment_id": req.razorpay_payment_id,
        "ap2_token_saved": True
    }

@app.post("/api/payment/credentials")
async def update_razorpay_credentials(req: RazorpayCredentialsRequest):
    """Update Razorpay Key ID and Secret dynamically."""
    res = payment_manager.update_credentials(req.key_id, req.key_secret)
    return res

@app.post("/api/payment/card-checkout")
async def card_checkout_razorpay(req: CardPaymentRequest):
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
    return result

@app.get("/api/customer/payment-details")
async def get_customer_payment_details(user_id: str = "user_alex"):
    """Returns saved customer payment card details if available."""
    details = cart_manager.get_customer_payment_details(user_id)
    return {
        "has_saved_card": details is not None,
        "payment_details": details
    }

@app.post("/api/customer/payment-details")
async def save_customer_payment_details(req: SaveCustomerCardRequest):
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
async def get_orders(user_id: str = "user_alex"):
    orders = order_manager.get_orders_by_user(user_id)
    return {
        "count": len(orders),
        "orders": orders
    }

@app.get("/api/orders/{order_id}")
async def get_order_details(order_id: str):
    order = order_manager.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/api/orders/{order_id}/refund")
async def refund_order(order_id: str, reason: Optional[str] = "Customer Request"):
    """
    Issues a refund on Razorpay Gateway and updates customer account & inventory.
    """
    res = payment_manager.process_refund(order_id=order_id, reason=reason)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Refund failed"))
    return res

@app.get("/api/payment/dashboard-info")
async def get_payment_dashboard_info():
    """
    Returns Razorpay dashboard links, test credentials status, and navigation guide.
    """
    return payment_manager.get_dashboard_info()

@app.get("/api/payment/ap2-status")
async def get_ap2_authorization_status(user_id: str = "user_alex"):
    """
    AP2 Protocol: Check if the user has an active Razorpay authorization token for autonomous agent payments.
    """
    token = cart_manager.get_ap2_payment_token(user_id)
    if token:
        return {
            "authorized": True,
            "authorized_at": token.get("authorized_at"),
            "card_details": token.get("card_details", {}),
            "message": "AP2 auto-pay is active. Agent can place orders autonomously without any checkout popup."
        }
    return {
        "authorized": False,
        "message": "AP2 not yet authorized. Complete one-time Razorpay Checkout via the '🔐 Authorize Auto-Pay' button."
    }

@app.post("/api/payment/ap2-save-token")
async def save_ap2_token(req: AP2SaveTokenRequest):
    """
    AP2 Protocol: Manually save an AP2 authorization token after a verified Razorpay payment.
    Called by the frontend after Razorpay Checkout completes successfully.
    """
    res = payment_manager.save_ap2_token_from_payment(
        user_id=req.user_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_order_id=req.razorpay_order_id,
        card_details=req.card_details or cart_manager.get_customer_payment_details(req.user_id) or {}
    )
    return res

@app.post("/api/payment/agent-autopay")
async def agent_autonomous_pay(user_id: str = "user_alex", shipping_address: Optional[str] = None):
    """
    AP2 Protocol: Backend endpoint for fully autonomous agent payment using stored token.
    No frontend checkout modal — payment is captured server-side.
    """
    res = payment_manager.autonomous_agent_pay(user_id=user_id, shipping_address=shipping_address)
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
async def update_settings(req: SettingsRequest):
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
# 👑 ADMIN PANEL & 24/7 AGENT FLEET ENDPOINTS
# =====================================================================

# Admin agent imports (already imported above at module level)
from backend.background_workers import background_worker
from backend.review_manager import review_manager

@app.on_event("startup")
async def startup_event():
    """Start 24/7 background agent loop on server boot."""
    background_worker.start()

class AdminChatRequest(BaseModel):
    prompt: str
    conversation_history: Optional[List[Dict[str, str]]] = None

class AdminInventoryUpdateRequest(BaseModel):
    product_id: str
    stock: Optional[int] = None
    price: Optional[float] = None
    base_price: Optional[float] = None

class AdminProductAddRequest(BaseModel):
    PRODUCT_NAME: str
    PRODUCT_TYPE: str = "Accessories"
    PRODUCT_SIZE: str = "One Size"
    STOCK_REMAINING: int = 15
    BASE_PRICE: Optional[float] = None
    PRICE: float = 49.99
    DESCRIPTION: str = ""
    IMAGE: Optional[str] = "/static/images/cyberflex_runner.svg"
    TAGS: Optional[List[str]] = []

class AdminBulkPriceRequest(BaseModel):
    category: Optional[str] = None
    percentage: float

class AdminOrderStatusUpdateRequest(BaseModel):
    status: str
    tracking_number: Optional[str] = None
    notes: Optional[str] = None

class AdminOrderCancelRequest(BaseModel):
    reason: Optional[str] = "Customer Request"
    force_override: bool = False

class AdminReviewAddRequest(BaseModel):
    product_id: str
    customer_name: str
    rating: int = 5
    review_text: str
    product_name: Optional[str] = None

class AdminGenerateReviewSummaryRequest(BaseModel):
    product_id: str

class AdminAgentTriggerRequest(BaseModel):
    agent_key: str

class AdminAgentIntervalRequest(BaseModel):
    agent_key: str
    interval_seconds: int

class AdminChatRequest(BaseModel):
    prompt: str
    conversation_history: Optional[List[Dict[str, str]]] = None

@app.get("/admin")
async def serve_admin_panel():
    admin_index = os.path.join(FRONTEND_DIR, "admin", "index.html")
    if os.path.exists(admin_index):
        return FileResponse(admin_index)
    return {"message": "Admin panel frontend index.html not found"}

@app.get("/api/admin/overview")
async def get_admin_overview():
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
async def get_admin_agents_status():
    """Returns live telemetry for all 6 autonomous agents and their independent schedules."""
    return background_worker.get_status()

@app.post("/api/admin/agents/trigger")
async def trigger_admin_agent(req: AdminAgentTriggerRequest):
    """Manually triggers an instant autonomous execution cycle for an agent."""
    res = await background_worker.trigger_agent(req.agent_key)
    return res

@app.post("/api/admin/agents/interval")
async def update_admin_agent_interval(req: AdminAgentIntervalRequest):
    """Dynamically updates the schedule interval for an admin agent (e.g. 120 for 2m, 300 for 5m, 7200 for 2h)."""
    res = background_worker.update_agent_interval(req.agent_key, req.interval_seconds)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Update failed"))
    return res

@app.get("/api/admin/agent-logs")
async def get_admin_agent_logs(limit: int = 60):
    """Returns recent 24/7 autonomous agent audit log entries."""
    from backend.admin_agents import get_agent_logs as fetch_agent_logs
    logs = fetch_agent_logs(limit=limit)
    return {"logs": logs, "count": len(logs)}

@app.get("/api/admin/agent-messages")
async def get_admin_agent_messages(limit: int = 60):
    """Returns recent inter-agent communications recorded on the persistent message bus."""
    messages = message_bus.get_all_messages(limit=limit)
    return {"messages": messages, "count": len(messages)}

@app.post("/api/admin/inventory/update")
async def admin_update_inventory(req: AdminInventoryUpdateRequest):
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
    return {"success": True, "updated": updated}

@app.post("/api/admin/inventory/add")
async def admin_add_product(req: AdminProductAddRequest):
    """Adds a new product to catalog."""
    res = inventory_manager.add_product(req.dict())
    return res

@app.post("/api/admin/inventory/bulk-price")
async def admin_bulk_price(req: AdminBulkPriceRequest):
    """Applies bulk percentage discount or increase."""
    res = inventory_manager.bulk_price_adjustment(category=req.category, percentage=req.percentage)
    return res

@app.post("/api/admin/orders/{order_id}/status")
async def admin_update_order_status(order_id: str, req: AdminOrderStatusUpdateRequest):
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
        res = await refund_manager_agent.execute_command(action="refund", order_id=order_id, reason=req.reason, force=True)
    else:
        res = order_manager.evaluate_24h_cancellation_and_refund(order_id=order_id, reason=req.reason)
    
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Cancellation failed"))
    return res

@app.get("/api/admin/reviews")
async def admin_get_reviews():
    """Returns all verified customer reviews."""
    return {"reviews": review_manager.get_all_reviews()}

@app.post("/api/admin/reviews/add")
async def admin_add_review(req: AdminReviewAddRequest):
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
    """Triggers Groq AI review summary generation for a product."""
    res = await review_manager.generate_ai_review_summary(req.product_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Summary generation failed"))
    return res

@app.get("/api/admin/agent-messages")
async def get_agent_messages(limit: int = 50):
    """Returns the inter-agent message bus history for admin dashboard visibility."""
    return {
        "messages": message_bus.get_all_messages(limit=limit),
        "inbox_snapshot": message_bus.get_inbox_snapshot()
    }

@app.get("/api/admin/ceo/report")
async def get_ceo_report():
    """Triggers the CEO Agent to generate an on-demand strategic report for the Owner."""
    report = await ceo_agent.generate_owner_report()
    return report

@app.post("/api/admin/chat")
async def admin_chat(req: AdminChatRequest):
    """Owner Command Agent chatbot endpoint — routes through CEO awareness."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    output = await admin_chat_agent.run_prompt(
        prompt=req.prompt,
        conversation_history=req.conversation_history
    )
    return output


# Serve root frontend
@app.get("/")
async def root():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "AI Growth Commerce Agentic Store API is running."}

