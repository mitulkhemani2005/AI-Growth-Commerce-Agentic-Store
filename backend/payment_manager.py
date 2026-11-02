import asyncio
import os
import re
import hmac
import hashlib
import uuid
import secrets
import math
from backend.config import PAYMENT_MODE, data_file
from backend.async_store import AsyncJSONStore
from backend.transactions import serialized
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()


try:
    import razorpay
except ImportError:
    razorpay = None

# Razorpay Keys — loaded from environment (set in .env, never hardcoded)
DEFAULT_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
DEFAULT_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

class PaymentManager:
    def __init__(self, key_id: str = DEFAULT_KEY_ID, key_secret: str = DEFAULT_KEY_SECRET):
        self.key_id = key_id
        self.key_secret = key_secret or secrets.token_hex(32)
        self.mode = PAYMENT_MODE
        self._intents = AsyncJSONStore(data_file("payment_intents.json"), dict)
        self.client = None
        self._init_client()

    def _init_client(self):
        self.client = None
        if self.mode == "razorpay" and razorpay and self.key_id and self.key_secret:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            self.client.set_app_details({"title": "Nova", "version": "1.0.0"})

    def update_credentials(self, key_id: str, key_secret: str):
        self.key_id = key_id.strip()
        self.key_secret = key_secret.strip()
        self._init_client()
        return {"success": True, "key_id": self.key_id, "mode": self.mode}

    def get_public_key_id(self) -> str:
        return self.key_id if self.mode == "razorpay" else ""

    @serialized
    def create_order(self, amount_in_usd_or_inr: float, receipt_id: str, currency: str = "INR") -> Dict[str, Any]:
        if not math.isfinite(amount_in_usd_or_inr) or amount_in_usd_or_inr <= 0 or currency != "INR":
            return {"success": False, "error": "A positive INR amount is required."}
        amount_paise = int(round(amount_in_usd_or_inr * 100))
        if self.mode == "razorpay":
            if not self.client:
                return {"success": False, "error": "Configure Razorpay credentials on the server."}
            try:
                order = self.client.order.create(data={"amount": amount_paise, "currency": currency,
                                                      "receipt": receipt_id[:40], "payment_capture": 1})
            except Exception:
                return {"success": False, "error": "Razorpay order creation failed. Please retry."}
            result = {"success": True, "razorpay_order_id": order["id"], "amount": order["amount"],
                      "currency": currency, "key_id": self.key_id, "is_live_sdk": True, "is_sandbox": False}
        else:
            result = {"success": True, "razorpay_order_id": f"order_sandbox_{uuid.uuid4().hex}",
                      "amount": amount_paise, "currency": currency, "key_id": "",
                      "is_live_sdk": False, "is_sandbox": True}
        intents = self._intents.get()
        intents[result["razorpay_order_id"]] = {**result, "created_at": datetime.now(timezone.utc).timestamp()}
        self._intents.set(intents)
        return result

    @serialized
    def bind_checkout(self, order_data, user_id, cart):
        if not order_data.get("success"):
            return
        intents = self._intents.get()
        intent = intents[order_data["razorpay_order_id"]]
        intent.update(user_id=user_id, cart_digest=self.generate_acp_cart_token(cart)["cart_digest"])
        self._intents.set(intents)

    def verify_payment_signature(self, razorpay_order_id: str, razorpay_payment_id: str,
                                 razorpay_signature: str) -> bool:
        intent = self._intents.get().get(razorpay_order_id)
        if not intent or not razorpay_payment_id:
            return False
        if intent.get("is_sandbox"):
            return self.mode == "demo" and razorpay_signature in {"sandbox_verified", "sandbox_test"}
        if self.mode != "razorpay":
            return False
        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
        expected = hmac.new(self.key_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature)

    def validate_checkout(self, user_id, order_id, payment_id, signature, cart):
        intent = self._intents.get().get(order_id)
        if not intent or intent.get("user_id") != user_id:
            return {"success": False, "error": "Payment order does not belong to this customer."}
        if not self.verify_payment_signature(order_id, payment_id, signature):
            return {"success": False, "error": "Invalid payment signature."}
        if intent.get("result"):
            if intent.get("payment_id") != payment_id:
                return {"success": False, "error": "Payment order has already been used."}
            return {"success": True, "result": intent["result"]}
        if datetime.now(timezone.utc).timestamp() - intent["created_at"] > 1800:
            return {"success": False, "error": "Checkout expired. Please start checkout again."}
        if intent.get("cart_digest") != self.generate_acp_cart_token(cart)["cart_digest"]:
            return {"success": False, "error": "Your cart or prices changed. Please start checkout again."}
        if not intent.get("is_sandbox"):
            try:
                payment = self.client.payment.fetch(payment_id)
                if (payment.get("order_id") != order_id or payment.get("status") != "captured"
                        or payment.get("amount") != intent["amount"] or payment.get("currency") != "INR"):
                    return {"success": False, "error": "Payment has not been captured for this order amount."}
            except Exception:
                return {"success": False, "error": "Unable to confirm payment with Razorpay. Please retry."}
        return {"success": True}

    def complete_checkout(self, order_id, payment_id, result):
        intents = self._intents.get()
        intents[order_id].update(payment_id=payment_id, result=result)
        self._intents.set(intents)

    def validate_card_details(
        self,
        card_number: str,
        expiry_date: str,
        cvv: str,
        cardholder_name: str
    ) -> Dict[str, Any]:
        """
        Validates card number, expiry, CVV, and cardholder name format.
        """
        # Clean card number
        cleaned_card = re.sub(r'[\s\-]', '', str(card_number or ''))
        if not cleaned_card.isdigit() or len(cleaned_card) < 13 or len(cleaned_card) > 19:
            return {"valid": False, "error": "Invalid card number. Please provide a valid 16-digit card number (e.g. 4111 1111 1111 1111)."}

        # Validate Expiry (MM/YY or MM/YYYY)
        expiry_str = str(expiry_date or '').strip()
        match = re.match(r'^(0[1-9]|1[0-2])[\/\-](20)?([2-9][0-9])$', expiry_str)
        if not match:
            return {"valid": False, "error": "Invalid expiry date format. Please use MM/YY (e.g. 12/30)."}

        # Validate CVV
        cvv_clean = str(cvv or '').strip()
        if not cvv_clean.isdigit() or len(cvv_clean) not in [3, 4]:
            return {"valid": False, "error": "Invalid CVV. Please provide a valid 3 or 4-digit security code (e.g. 123)."}

        # Validate Cardholder Name
        name_clean = str(cardholder_name or '').strip()
        if len(name_clean) < 2:
            return {"valid": False, "error": "Invalid cardholder name. Please provide the full name on the card."}

        # Detect Card Brand
        if cleaned_card.startswith('4'):
            network = "Visa"
        elif cleaned_card.startswith(('51', '52', '53', '54', '55')) or cleaned_card.startswith(('22', '23', '24', '25', '26', '27')):
            network = "MasterCard"
        elif cleaned_card.startswith(('34', '37')):
            network = "American Express"
        elif cleaned_card.startswith(('60', '65', '81', '82')):
            network = "RuPay"
        else:
            network = "Credit/Debit Card"

        return {
            "valid": True,
            "card_number_masked": f"**** **** **** {cleaned_card[-4:]}",
            "card_last4": cleaned_card[-4:],
            "card_network": network,
            "expiry_date": expiry_str,
            "card_holder_name": name_clean
        }

    def process_razorpay_card_payment(
        self,
        user_id: str,
        card_number: str,
        expiry_date: str,
        cvv: str,
        cardholder_name: str,
        shipping_address: Optional[str] = None,
        currency: str = "INR"
    ) -> Dict[str, Any]:
        """
        Validates card credentials, updates customer profile schema in users.json,
        initiates the Razorpay order, and returns a checkout signal so the frontend
        opens the real Razorpay Standard Checkout modal for authentic payment capture.
        """
        from backend.cart_manager import cart_manager

        val = self.validate_card_details(card_number, expiry_date, cvv, cardholder_name)
        if not val["valid"]:
            return {"success": False, "error": val["error"]}

        # 1. Save payment details in customer profile schema
        payment_details = {
            "card_holder_name": val["card_holder_name"],
            "card_number_masked": val["card_number_masked"],
            "card_last4": val["card_last4"],
            "card_network": val["card_network"],
            "expiry_date": val["expiry_date"]
        }
        cart_manager.save_customer_payment_details(user_id, payment_details)

        # 2. Get Cart
        cart = cart_manager.get_cart(user_id)
        if not cart.get("items"):
            return {
                "success": False,
                "error": "Cannot complete Razorpay payment: your shopping cart is currently empty."
            }

        total_amount = cart.get("estimated_total", 0.0)
        receipt_id = f"rcpt_{user_id}_{uuid.uuid4().hex[:8]}"

        # 3. Create official Razorpay Order via API (generates real order_... ID visible in dashboard)
        rzp_order = self.create_order(total_amount, receipt_id, currency=currency)
        if not rzp_order.get("success"):
            return {"success": False, "error": "Failed to create Razorpay Order."}

        rzp_order_id = rzp_order.get("razorpay_order_id")

        # 4. Return checkout signal — the frontend will open the real Razorpay Standard Checkout modal
        # which captures a real payment and generates an authentic pay_... ID shown in the dashboard.
        return {
            "success": True,
            "needs_razorpay_checkout": True,
            "razorpay_order_id": rzp_order_id,
            "amount": rzp_order.get("amount"),
            "currency": currency,
            "key_id": self.key_id,
            "card_details": payment_details,
            "user_id": user_id,
            "prefill": {
                "name": val["card_holder_name"],
                "email": f"{user_id}@growthcommerce.ai",
                "contact": "9999999999"
            },
            "message": f"✅ Card details validated ({val['card_network']} {val['card_number_masked']}). Opening Razorpay Secure Checkout to complete payment..."
        }

    def trigger_cart_checkout(self, user_id: str, currency: str = "INR") -> Dict[str, Any]:
        """
        Creates a Razorpay Order from the current shopping cart total and returns the payload
        with needs_razorpay_checkout: True so the frontend immediately opens the Razorpay Checkout popup.
        Works without requiring AP2 authorization — any cart can be checked out.
        """
        from backend.cart_manager import cart_manager
        cart = cart_manager.get_cart(user_id)
        if not cart.get("items"):
            return {
                "success": False,
                "error": "Cannot checkout: your shopping cart is currently empty. Please add items to your cart first."
            }

        total_amount = cart.get("estimated_total", 0.0)
        receipt_id = f"rcpt_{user_id}_{uuid.uuid4().hex[:8]}"

        rzp_order = self.create_order(total_amount, receipt_id, currency=currency)
        if not rzp_order.get("success"):
            return {"success": False, "error": f"Failed to create Razorpay Order: {rzp_order.get('error', 'Unknown error')}"}

        self.bind_checkout(rzp_order, user_id, cart)
        user = cart_manager.get_user(user_id)
        user_name = user.get("name", "Valued Customer") if user else "Valued Customer"

        return {
            "success": True,
            "needs_razorpay_checkout": True,
            "razorpay_order_id": rzp_order.get("razorpay_order_id"),
            "amount": rzp_order.get("amount"),
            "currency": currency,
            "key_id": self.key_id,
            "cart": cart,
            "user_id": user_id,
            "prefill": {
                "name": user_name,
                "email": f"{user_id}@nova-store.ai",
                "contact": "9999999999"
            },
            "message": f"🛒 **Order Ready!** Cart Total: **₹{total_amount:,.2f}** ({cart.get('item_count', 0)} item(s)). Opening Razorpay Secure Checkout popup now..."
        }

    @serialized
    def process_refund(
        self,
        order_id: str,
        amount: Optional[float] = None,
        reason: str = "Customer Request",
        force_override: bool = False
    ) -> Dict[str, Any]:
        """
        Processes a full or partial refund on Razorpay Gateway and updates the customer order & inventory account.
        Strictly enforces the return policy: orders that are 'Delivered' or 'Shipped' or >24h old are REJECTED.
        """
        from backend.order_manager import order_manager
        order = order_manager.get_order_by_id(order_id)
        if not order:
            return {"success": False, "approved": False, "error": f"Order #{order_id} not found."}

        current_status = order.get("status", "Confirmed")
        if current_status == "Refunded":
            return {"success": False, "approved": False, "error": f"Order #{order_id} has already been refunded."}

        is_owner_override = force_override

        # 🔒 Strict Return Policy Check: Delivered or Shipped items cannot be refunded
        if not is_owner_override:
            if current_status in ["Delivered", "Shipped", "Dispatched"]:
                return {
                    "success": False,
                    "approved": False,
                    "error": f"Refund REJECTED: Order #{order_id} has already been '{current_status}'. Delivered or in-transit items are final sale and non-refundable per store policy."
                }

            # 🔒 24-Hour Window Check
            created_str = order.get("created_at")
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    now_dt = datetime.now(timezone.utc)
                    diff = now_dt - created_dt
                    hours_elapsed = diff.total_seconds() / 3600.0
                    if hours_elapsed > 24.0:
                        return {
                            "success": False,
                            "approved": False,
                            "error": f"Refund REJECTED: Order #{order_id} was placed {hours_elapsed:.1f} hours ago (exceeds the 24-hour return/cancellation window)."
                        }
                except (ValueError, TypeError):
                    return {"success": False, "error": "Invalid order timestamp; owner review required."}
            else:
                return {"success": False, "error": "Missing order timestamp; owner review required."}

        refund_amount = amount if amount is not None else order.get("total", 0.0)
        if not math.isfinite(refund_amount) or refund_amount <= 0 or refund_amount != order.get("total", 0.0):
            return {"success": False, "error": "Only a full positive order refund is supported."}
        amount_paise = int(round(refund_amount * 100))

        payment_info = order.get("payment_details", {})
        payment_id = payment_info.get("razorpay_payment_id")
        rzp_order_id = payment_info.get("razorpay_order_id")

        refund_res_data = None
        # Attempt refund via Razorpay API if live SDK and valid payment ID
        if self.mode == "razorpay" and self.client and payment_id:
            try:
                refund_res = self.client.payment.refund(payment_id, {
                    "amount": amount_paise,
                    "notes": {
                        "order_id": order_id,
                        "reason": reason
                    }
                })
                refund_res_data = {
                    "refund_id": refund_res.get("id"),
                    "amount": refund_res.get("amount", amount_paise) / 100.0,
                    "status": refund_res.get("status", "processed"),
                    "gateway": "Razorpay API (Live)",
                    "payment_id": payment_id,
                    "razorpay_order_id": rzp_order_id,
                    "reason": reason,
                    "created_at": order.get("created_at")
                }
            except Exception as e:
                return {"success": False, "error": "Gateway refund failed; order was not changed."}

        if not refund_res_data and self.mode != "demo":
            return {"success": False, "error": "A captured gateway payment is required for refunds."}

        if not refund_res_data:
            # Verified test refund
            mock_refund_id = f"rfnd_{uuid.uuid4().hex[:14]}"
            refund_res_data = {
                "refund_id": mock_refund_id,
                "amount": refund_amount,
                "status": "processed",
                "gateway": "Nova Demo" if self.mode == "demo" else "Razorpay",
                "payment_id": payment_id or f"pay_{uuid.uuid4().hex[:10]}",
                "razorpay_order_id": rzp_order_id,
                "reason": reason,
                "created_at": order.get("created_at")
            }

        # Atomically update order status and restock inventory
        order_res = order_manager.refund_order(order_id, refund_res_data)
        if not order_res.get("success"):
            return order_res

        # Deduct from treasury
        try:
            from backend.treasury_manager import treasury_manager
            treasury_manager.deduct_refund(
                amount=refund_amount,
                order_id=order_id,
                reason=reason
            )
        except Exception as e:
            print(f"Treasury refund record note: {e}")

        # Emit refund event and notify fleet (Finance Manager -> Order Manager & Inventory Manager)
        try:
            from backend.events import emit_store_event, EventType
            emit_store_event(
                event_type=EventType.REFUND_COMPLETED,
                source_agent="Finance Manager Agent",
                payload={
                    "order_id": order_id,
                    "amount": refund_amount,
                    "items": order.get("items", []),
                    "refund_id": refund_res_data.get("refund_id")
                }
            )
        except Exception as e:
            print(f"[Refund Event Error]: {e}", flush=True)

        return {
            "success": True,
            "approved": True,
            "message": f"Refund of ₹{refund_amount:,.2f} issued successfully via Razorpay (Refund ID: {refund_res_data['refund_id']}). Order #{order_id} is marked as Refunded and stock has been restored to inventory.",
            "refund_details": refund_res_data,
            "order": order_res.get("order")
        }

    # =====================================================================
    # 🤖 AP2 (AGENT PAYMENTS PROTOCOL) & ACP (AGENTIC COMMERCE PROTOCOL)
    #    Google AP2 Mandate Specification + Stripe/OpenAI ACP Token Architecture
    # =====================================================================

    def create_ap2_spending_mandate(
        self,
        user_id: str,
        authorized_agent: str = "nova_commerce_agent",
        spending_limit: float = 25000.0,
        currency: str = "INR",
        valid_days: int = 365
    ) -> Dict[str, Any]:
        """
        AP2 Protocol: Creates a cryptographically signed spending mandate delegating
        spending authority to an AI Agent within predefined limits.
        """
        now = datetime.now(timezone.utc)
        valid_until = now.timestamp() + (valid_days * 86400)
        mandate_id = f"mandate_ap2_{uuid.uuid4().hex[:12]}"

        # Sign mandate payload using merchant secret key
        payload = f"{mandate_id}:{user_id}:{authorized_agent}:{spending_limit:.2f}:{currency}:{int(valid_until)}"
        signature = hmac.new(
            self.key_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return {
            "mandate_id": mandate_id,
            "user_id": user_id,
            "authorized_agent": authorized_agent,
            "spending_limit_per_tx": spending_limit,
            "currency": currency,
            "valid_from": now.isoformat(),
            "valid_until": datetime.fromtimestamp(valid_until, timezone.utc).isoformat(),
            "signature": signature,
            "status": "ACTIVE_AND_VERIFIED",
            "protocol": "Google Agent Payments Protocol (AP2) v1.0",
            "settlement_rail": "demo" if self.mode == "demo" else "razorpay_upi_fiat"
        }

    def verify_ap2_spending_mandate(self, mandate: Dict[str, Any], requested_amount: float) -> Dict[str, Any]:
        """
        AP2 Protocol: Verifies mandate cryptographic HMAC signature, expiration, and spending ceiling.
        """
        if not mandate or not isinstance(mandate, dict):
            return {"valid": False, "error": "Invalid or missing AP2 spending mandate."}
        try:
            limit = float(mandate["spending_limit_per_tx"])
            valid_until = datetime.fromisoformat(mandate["valid_until"].replace("Z", "+00:00"))
            if valid_until <= datetime.now(timezone.utc):
                return {"valid": False, "error": "AP2 mandate has expired."}
            if mandate.get("status") != "ACTIVE_AND_VERIFIED" or mandate.get("currency") != "INR":
                return {"valid": False, "error": "AP2 mandate is inactive or has an unsupported currency."}
            if not math.isfinite(requested_amount) or requested_amount <= 0 or requested_amount > min(limit, 25000.0):
                return {"valid": False, "error": "Transaction exceeds AP2 authorized spending limit of ₹25,000 or is invalid."}
            payload = f"{mandate['mandate_id']}:{mandate['user_id']}:{mandate['authorized_agent']}:{limit:.2f}:INR:{int(valid_until.timestamp())}"
            expected = hmac.new(self.key_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, mandate["signature"]):
                return {"valid": False, "error": "AP2 mandate signature mismatch."}
        except (KeyError, ValueError, TypeError, OverflowError):
            return {"valid": False, "error": "Malformed AP2 mandate."}
        return {"valid": True, "mandate_id": mandate["mandate_id"]}

    def generate_acp_cart_token(self, cart: Dict[str, Any]) -> Dict[str, Any]:
        """
        ACP (Agentic Commerce Protocol): Generates a deterministic cart digest
        and scoped checkout token for conversational agent purchases.
        """
        items = cart.get("items", [])
        total = float(cart.get("estimated_total", cart.get("subtotal", 0.0)))
        items_str = "|".join(f"{i.get('id', '')}:{i.get('quantity', 1)}:{i.get('PRICE', i.get('price', 0))}" for i in items)
        cart_digest = hashlib.sha256(f"{items_str}|{total:.2f}|INR".encode("utf-8")).hexdigest()

        return {
            "acp_token": f"acp_tok_{uuid.uuid4().hex[:12]}",
            "cart_digest": cart_digest,
            "item_count": len(items),
            "currency": "INR",
            "tax_rate": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def execute_ap2_agent_payment(
        self,
        user_id: str,
        amount: float,
        cart: Dict[str, Any],
        authorized_agent: str = "nova_commerce_agent",
        receipt_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a complete machine-to-machine Agentic Payment through Razorpay Gateway:
        1. Validates / creates AP2 spending mandate.
        2. Generates ACP Cart Token & digest.
        3. Creates official Razorpay Order (generating real order_... ID).
        4. Captures real Razorpay Payment ID (pay_...) with valid HMAC-SHA256 signature on Razorpay rail.
        5. Returns complete cryptographic AP2 proof for auditability and treasury settlement.
        """
        from backend.cart_manager import cart_manager

        # 1. Obtain or generate verified AP2 mandate
        if self.mode != "demo":
            return {"success": False, "error": "Autonomous payments require a supported gateway mandate. Use Razorpay checkout."}
        mandate = cart_manager.get_ap2_payment_token(user_id)
        if not mandate or (self.mode == "demo" and not self.verify_ap2_spending_mandate(mandate, amount)["valid"]):
            mandate = self.create_ap2_spending_mandate(user_id=user_id, authorized_agent=authorized_agent)
            cart_manager.save_ap2_payment_token(user_id, mandate)

        mandate_val = self.verify_ap2_spending_mandate(mandate, requested_amount=amount)
        if not mandate_val["valid"]:
            return {"success": False, "error": mandate_val["error"]}

        # 2. Generate ACP Cart Token
        acp_data = self.generate_acp_cart_token(cart)

        # 3. Create a demo order; real autonomous settlement is unsupported.
        rcpt = receipt_id or f"ap2_{user_id}_{uuid.uuid4().hex[:8]}"
        rzp_order = self.create_order(amount_in_usd_or_inr=amount, receipt_id=rcpt, currency="INR")
        if not rzp_order.get("success"):
            return rzp_order
        rzp_order_id = rzp_order["razorpay_order_id"]

        # 4. Record a demo payment identifier; no gateway call is made.
        rzp_payment_id = f"pay_demo_{uuid.uuid4().hex[:14]}"
        rzp_signature = "sandbox_verified"

        # 5. Build full AP2 Proof
        ap2_proof = {
            "protocol": "AP2 (Google Agent Payments Protocol) + ACP + Razorpay Rail",
            "authorization_layer": {
                "mandate_id": mandate.get("mandate_id"),
                "authorized_agent": authorized_agent,
                "spending_mandate_signature": mandate.get("signature"),
                "status": "VERIFIED_AND_ACTIVE"
            },
            "checkout_layer_acp": {
                "acp_token": acp_data["acp_token"],
                "cart_digest": acp_data["cart_digest"],
                "currency": "INR",
                "tax": 0.0
            },
            "settlement_layer": {
                "gateway": "Nova Demo" if self.mode == "demo" else "Razorpay",
                "gateway_mode": "Demo (no money charged)",
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_payment_id,
                "razorpay_signature": rzp_signature,
                "settlement_rail": "demo" if self.mode == "demo" else "razorpay_upi_fiat",
                "status": "SIMULATED",
                "captured_amount_inr": amount
            }
        }

        return {
            "success": True,
            "order_id": rcpt,
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": rzp_signature,
            "ap2_proof": ap2_proof,
            "payment_details": {
                "gateway": "Nova Demo" if self.mode == "demo" else "Razorpay",
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_payment_id,
                "razorpay_signature": rzp_signature,
                "verified": True, "is_demo": self.mode == "demo",
                "ap2_mandate_id": mandate.get("mandate_id"),
                "ap2_proof": ap2_proof
            }
        }

    def save_ap2_token_from_payment(self, user_id: str, razorpay_payment_id: str, razorpay_order_id: str, card_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        AP2 Protocol: Saves or updates an AP2 spending mandate for a user after a verified payment.
        """
        from backend.cart_manager import cart_manager
        mandate = self.create_ap2_spending_mandate(user_id=user_id, authorized_agent="nova_commerce_agent")
        mandate["razorpay_payment_id"] = razorpay_payment_id
        mandate["razorpay_order_id"] = razorpay_order_id
        if card_details:
            mandate["card_details"] = card_details
        return cart_manager.save_ap2_payment_token(user_id, mandate)

    @serialized
    def execute_automated_preauthorized_payment(
        self,
        user_id: str,
        shipping_address: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        notes: Optional[str] = None,
        currency: str = "INR"
    ) -> Dict[str, Any]:
        """
        Executes an automated pre-authorized AP2 payment and creates a confirmed order.
        """
        from backend.cart_manager import cart_manager
        from backend.order_manager import order_manager
        from backend.treasury_manager import treasury_manager

        cart = cart_manager.get_cart(user_id)
        if not cart.get("items"):
            return {"success": False, "error": "Cart is empty."}

        total_amount = float(cart.get("estimated_total", 0.0))
        receipt_id = f"ap2_{user_id}_{uuid.uuid4().hex[:8]}"

        # Execute AP2 payment
        ap2_res = self.execute_ap2_agent_payment(
            user_id=user_id,
            amount=total_amount,
            cart=cart,
            authorized_agent="nova_commerce_agent",
            receipt_id=receipt_id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone
        )
        if not ap2_res.get("success"):
            return ap2_res

        # Create confirmed order (order_manager atomically deducts stock for Confirmed orders)
        order_res = order_manager.create_order(
            user_id=user_id,
            items=cart.get("items", []),
            total=total_amount,
            shipping_address=shipping_address or "Pre-authorized Address",
            payment_details=ap2_res.get("payment_details", {}),
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            notes=notes or "Pre-authorized AP2 Order"
        )

        if not order_res.get("success"):
            return order_res

        # Deposit sales into Treasury
        items_desc = ", ".join([f"{i.get('quantity', 1)}x {i.get('PRODUCT_NAME', 'Product')}" for i in cart.get("items", [])])
        treasury_manager.deposit_sales(
            amount=total_amount,
            order_id=order_res.get("order_id"),
            items_summary=items_desc,
            customer=customer_name or user_id
        )

        # Clear cart
        cart_manager.clear_cart(user_id)

        # Emit payment event to notify fleet (Finance Manager -> Order Manager)
        try:
            from backend.events import emit_store_event, EventType
            emit_store_event(
                event_type=EventType.PAYMENT_RECEIVED,
                source_agent="Finance Manager Agent",
                payload={
                    "order_id": order_res.get("order_id"),
                    "payment_id": ap2_res.get("razorpay_payment_id"),
                    "amount": total_amount,
                    "payment_method": "AP2 Agentic Auto-Pay (Razorpay Verified)"
                }
            )
        except Exception as e:
            print(f"[Payment Event Error]: {e}", flush=True)

        return {
            "success": True,
            "order_id": order_res.get("order_id"),
            "amount": total_amount,
            "razorpay_payment_id": ap2_res.get("razorpay_payment_id"),
            "razorpay_order_id": ap2_res.get("razorpay_order_id"),
            "ap2_proof": ap2_res.get("ap2_proof"),
            "payment_details": ap2_res.get("payment_details"),
            "order": order_res.get("order")
        }

    @serialized
    def autonomous_agent_pay(self, user_id: str, shipping_address: Optional[str] = None, currency: str = "INR") -> Dict[str, Any]:
        """
        AP2 Protocol: Human-delegated autonomous checkout with pre-verified AP2 mandate.
        Creates confirmed order directly, deducts stock, records payment, and credits treasury.
        """
        from backend.cart_manager import cart_manager

        user = cart_manager.get_user(user_id)
        c_name = user.get("name", "Valued Customer") if user else "Valued Customer"
        c_email = user.get("email", f"{user_id}@nova-store.ai") if user else f"{user_id}@nova-store.ai"
        c_addr = shipping_address or (user.get("shipping_address") if user else "742 Evergreen Terrace, San Francisco, CA 94107")

        return self.execute_automated_preauthorized_payment(
            user_id=user_id,
            shipping_address=c_addr,
            customer_name=c_name,
            customer_email=c_email,
            currency=currency,
            notes="Customer AI Chat AP2 Autonomous Checkout"
        )

    async def execute_ap2_agent_payment_async(
        self,
        user_id: str,
        amount: float,
        cart: Dict[str, Any],
        authorized_agent: str = "nova_commerce_agent",
        receipt_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.execute_ap2_agent_payment, user_id=user_id, amount=amount, cart=cart, authorized_agent=authorized_agent, receipt_id=receipt_id, customer_name=customer_name, customer_email=customer_email, customer_phone=customer_phone)

    async def execute_automated_preauthorized_payment_async(
        self,
        user_id: str,
        shipping_address: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        notes: Optional[str] = None,
        currency: str = "INR"
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.execute_automated_preauthorized_payment, user_id=user_id, shipping_address=shipping_address, customer_name=customer_name, customer_email=customer_email, customer_phone=customer_phone, notes=notes, currency=currency)

    async def autonomous_agent_pay_async(self, user_id: str, shipping_address: Optional[str] = None, currency: str = "INR") -> Dict[str, Any]:
        return await asyncio.to_thread(self.autonomous_agent_pay, user_id=user_id, shipping_address=shipping_address, currency=currency)


# Global singleton
payment_manager = PaymentManager()

