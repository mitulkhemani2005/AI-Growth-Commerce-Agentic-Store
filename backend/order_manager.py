import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager

ORDERS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "orders.json"))
_lock = threading.RLock()


VALID_STATUSES = ["Pending", "Confirmed", "Dispatched", "Shipped", "Delivered", "Cancelled", "Refunded"]

class OrderManager:
    def __init__(self, file_path: str = ORDERS_FILE):
        self.file_path = file_path

    def _read_orders(self) -> List[Dict[str, Any]]:
        with _lock:
            if not os.path.exists(self.file_path):
                return []
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def _write_orders(self, orders: List[Dict[str, Any]]) -> None:
        with _lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(orders, f, indent=2)

    def get_all_orders(self) -> List[Dict[str, Any]]:
        orders = self._read_orders()
        return sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_orders_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        orders = self._read_orders()
        user_orders = [o for o in orders if o.get("user_id") == user_id]
        return sorted(user_orders, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        orders = self._read_orders()
        order_id_clean = order_id.upper().strip()
        for o in orders:
            if o.get("order_id", "").upper() == order_id_clean:
                return o
        return None

    def create_order(
        self,
        user_id: str,
        items: Optional[List[Dict[str, Any]]] = None,
        total: Optional[float] = None,
        shipping_address: Optional[str] = None,
        payment_method: str = "Razorpay Gateway (Online)",
        payment_details: Optional[Dict[str, Any]] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        notes: Optional[str] = None,
        initial_status: str = "Confirmed"
    ) -> Dict[str, Any]:
        """Creates a confirmed order directly or from cart."""
        if items:
            cart_manager.clear_cart(user_id)
            for it in items:
                pid = it.get("id") or it.get("product_id")
                qty = it.get("quantity", 1)
                sz = it.get("PRODUCT_SIZE") or it.get("size", "Standard")
                cart_manager.add_to_cart(user_id, pid, quantity=qty, size=sz)

        res = self.create_order_from_cart(
            user_id=user_id,
            shipping_address=shipping_address,
            payment_method=payment_method,
            payment_details=payment_details,
            initial_status=initial_status
        )
        if res.get("success") and res.get("order"):
            res["order_id"] = res["order"]["order_id"]
        return res

    def create_order_from_cart(
        self,
        user_id: str,
        shipping_address: Optional[str] = None,
        payment_method: str = "Razorpay Gateway (Online)",
        payment_details: Optional[Dict[str, Any]] = None,
        initial_status: str = "Confirmed"
    ) -> Dict[str, Any]:
        """
        Creates an order from user cart.
        When initial_status is 'Confirmed' (default for online payments), atomically deducts stock in inventory.json.
        """
        if not payment_method or "auto-pay" in payment_method.lower() or "1-click" in payment_method.lower():
            payment_method = "Razorpay Gateway (Online)"
        cart = cart_manager.get_cart(user_id)
        if not cart.get("items"):
            return {
                "success": False,
                "error": "Cannot place order: your shopping cart is currently empty."
            }

        user = cart_manager.get_user(user_id)
        customer_name = user.get("name", "Alex Rivera") if user else "Alex Rivera"
        address = shipping_address or (user.get("shipping_address") if user else "742 Evergreen Terrace, San Francisco, CA 94107")

        # Prepare items
        items_to_deduct = []
        order_items = []
        subtotal = 0.0

        for item in cart["items"]:
            items_to_deduct.append({
                "id": item["id"],
                "quantity": item["quantity"]
            })
            item_total = item["PRICE"] * item["quantity"]
            subtotal += item_total
            order_items.append({
                "id": item["id"],
                "PRODUCT_NAME": item["PRODUCT_NAME"],
                "PRODUCT_TYPE": item["PRODUCT_TYPE"],
                "PRODUCT_SIZE": item["PRODUCT_SIZE"],
                "quantity": item["quantity"],
                "price": item["PRICE"],
                "item_total": round(item_total, 2),
                "IMAGE": item.get("IMAGE", "")
            })

        # Atomic stock deduction in inventory.json strictly when status is Confirmed
        deducted_items = []
        if initial_status.capitalize() == "Confirmed":
            deduct_res = inventory_manager.deduct_stock(items_to_deduct)
            if not deduct_res.get("success"):
                return {
                    "success": False,
                    "error": f"Order failed due to inventory check: {deduct_res.get('error')}"
                }
            deducted_items = deduct_res.get("deducted_items", [])

        # Calculate totals (0% Tax Free Storewide in INR)
        tax = 0.0
        total = round(subtotal, 2)

        order_id = f"ORD-{datetime.utcnow().strftime('%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        new_order = {
            "order_id": order_id,
            "user_id": user_id,
            "customer_name": customer_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": initial_status.capitalize(),
            "delivery_estimate": "2-3 Business Days",
            "tracking_number": None,
            "items": order_items,
            "currency": "INR",
            "subtotal": round(subtotal, 2),
            "tax": 0.0,
            "total": total,
            "payment_method": payment_method,
            "payment_details": payment_details or {},
            "shipping_address": address,
            "inventory_deducted": (initial_status.capitalize() == "Confirmed")
        }

        # Save order
        orders = self._read_orders()
        orders.append(new_order)
        self._write_orders(orders)

        # Clear cart
        cart_manager.clear_cart(user_id)

        return {
            "success": True,
            "message": f"Order {order_id} created with status '{new_order['status']}'.",
            "order": new_order,
            "deducted_items": deducted_items
        }

    def update_order_status(
        self,
        order_id: str,
        new_status: str,
        tracking_number: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates order status with lifecycle integrity:
        - If moving from Pending -> Confirmed: deducts inventory stock.
        - If moving to Cancelled (and inventory was deducted): restores stock.
        - If moving to Dispatched or Shipped: automatically ensures tracking number exists.
        """
        status_clean = new_status.capitalize().strip()
        if status_clean not in VALID_STATUSES:
            return {
                "success": False,
                "error": f"Invalid status '{new_status}'. Allowed: {', '.join(VALID_STATUSES)}"
            }

        orders = self._read_orders()
        order_idx = None
        order_id_clean = order_id.upper().strip()
        for i, o in enumerate(orders):
            if o.get("order_id", "").upper() == order_id_clean:
                order_idx = i
                break

        if order_idx is None:
            return {"success": False, "error": f"Order #{order_id} not found."}

        order = orders[order_idx]
        old_status = order.get("status", "Confirmed")

        # 1. Pending -> Confirmed: Trigger inventory deduction
        if old_status == "Pending" and status_clean == "Confirmed":
            if not order.get("inventory_deducted"):
                items_to_deduct = [{"id": item["id"], "quantity": item.get("quantity", 1)} for item in order.get("items", [])]
                deduct_res = inventory_manager.deduct_stock(items_to_deduct)
                if not deduct_res.get("success"):
                    return {"success": False, "error": f"Cannot confirm order #{order_id}: {deduct_res.get('error')}"}
                order["inventory_deducted"] = True

        # 2. Transition to Cancelled: Restore inventory if previously deducted
        if status_clean == "Cancelled" and old_status not in ["Cancelled", "Refunded"]:
            if order.get("inventory_deducted", True):
                items_to_restore = [{"id": item["id"], "quantity": item.get("quantity", 1)} for item in order.get("items", [])]
                inventory_manager.restore_stock(items_to_restore)
                order["inventory_deducted"] = False

        # 3. Tracking number assignment
        if tracking_number:
            order["tracking_number"] = tracking_number
        elif status_clean in ["Dispatched", "Shipped"] and not order.get("tracking_number"):
            order["tracking_number"] = f"TRK-{uuid.uuid4().hex[:8].upper()}"

        order["status"] = status_clean
        order["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        if notes:
            order["status_notes"] = notes

        self._write_orders(orders)
        return {
            "success": True,
            "message": f"Order #{order_id} status updated from '{old_status}' to '{status_clean}'.",
            "order": order
        }

    def assign_tracking_number(self, order_id: str, tracking_number: Optional[str] = None) -> Dict[str, Any]:
        """Assigns logistics tracking number and transitions status to Dispatched/Shipped."""
        trk = tracking_number or f"TRK-{uuid.uuid4().hex[:8].upper()}"
        return self.update_order_status(order_id, new_status="Dispatched", tracking_number=trk)

    def evaluate_24h_cancellation_and_refund(self, order_id: str, reason: str = "Customer Cancellation") -> Dict[str, Any]:
        """
        Strict 24-Hour & Non-Shipped Refund Rule:
        - Auto-Approved: Cancelled within 24 hours of creation AND status is not 'Shipped' or 'Delivered'.
        - Rejected: > 24 hours elapsed OR order has already been Shipped/Delivered.
        """
        order = self.get_order_by_id(order_id)
        if not order:
            return {"success": False, "approved": False, "error": f"Order #{order_id} not found."}

        current_status = order.get("status", "Confirmed")
        if current_status == "Refunded":
            return {"success": False, "approved": False, "error": f"Order #{order_id} has already been refunded."}

        # Rule Check 1: Must not be shipped or delivered
        if current_status in ["Shipped", "Delivered"]:
            return {
                "success": False,
                "approved": False,
                "error": f"Refund REJECTED: Order #{order_id} has already been '{current_status}'. Orders that have been shipped cannot be auto-refunded."
            }

        # Rule Check 2: Must be within 24 hours
        created_str = order.get("created_at")
        is_within_24h = True
        hours_elapsed = 0.0

        if created_str:
            try:
                # Parse created_at safely
                created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                diff = now_dt - created_dt
                hours_elapsed = round(diff.total_seconds() / 3600.0, 2)
                if diff.total_seconds() > 86400:  # 24 hours
                    is_within_24h = False
            except Exception as e:
                print(f"Date parse warning: {e}")

        if not is_within_24h:
            return {
                "success": False,
                "approved": False,
                "error": f"Refund REJECTED: Order #{order_id} was placed {hours_elapsed:.1f} hours ago (exceeds 24-hour cancellation window)."
            }

        # Eligible! Execute full refund via payment_manager
        from backend.payment_manager import payment_manager
        refund_res = payment_manager.process_refund(order_id=order_id, reason=f"[24h Auto-Approval] {reason}")
        if not refund_res.get("success"):
            return {
                "success": False,
                "approved": False,
                "error": f"Refund failed during payment gateway execution: {refund_res.get('error')}"
            }

        return {
            "success": True,
            "approved": True,
            "message": f"✅ Refund APPROVED & PROCESSED: Order #{order_id} was cancelled within {hours_elapsed:.1f}h (< 24h) before shipping. Refund ID: {refund_res.get('refund_details', {}).get('refund_id')}.",
            "refund_details": refund_res.get("refund_details"),
            "order": refund_res.get("order")
        }

    def refund_order(self, order_id: str, refund_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Marks an order as Refunded, records refund details, and restocks inventory.
        """
        orders = self._read_orders()
        order_idx = None
        order_id_clean = order_id.upper().strip()
        for i, o in enumerate(orders):
            if o.get("order_id", "").upper() == order_id_clean:
                order_idx = i
                break

        if order_idx is None:
            return {"success": False, "error": f"Order #{order_id} not found."}

        order = orders[order_idx]
        if order.get("status") == "Refunded":
            return {"success": False, "error": f"Order #{order_id} has already been refunded."}

        # Restock inventory in inventory.json if it was deducted
        if order.get("inventory_deducted", True):
            items_to_restore = [{"id": item.get("id") or item.get("product_id", ""), "quantity": item.get("quantity", 1)} for item in order.get("items", [])]
            inventory_manager.restore_stock(items_to_restore)
            order["inventory_deducted"] = False

        # Update order status & refund info
        order["status"] = "Refunded"
        order["refund_details"] = refund_details
        order["refunded_at"] = datetime.now(timezone.utc).isoformat()

        self._write_orders(orders)
        return {
            "success": True,
            "message": f"Order #{order_id} has been marked as Refunded.",
            "order": order
        }

order_manager = OrderManager()
