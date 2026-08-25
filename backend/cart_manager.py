import json
import os
import threading
from typing import List, Dict, Any, Optional
from backend.inventory_manager import inventory_manager

USERS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "users.json"))
_lock = threading.RLock()


class CartManager:
    def __init__(self, file_path: str = USERS_FILE):
        self.file_path = file_path

    def _read_users(self) -> List[Dict[str, Any]]:
        with _lock:
            if not os.path.exists(self.file_path):
                return []
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def _write_users(self, users: List[Dict[str, Any]]) -> None:
        with _lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        users = self._read_users()
        for u in users:
            if u.get("user_id") == user_id:
                return u
        return None

    def get_cart(self, user_id: str) -> Dict[str, Any]:
        user = self.get_user(user_id)
        if not user:
            return {"user_id": user_id, "items": [], "item_count": 0, "subtotal": 0.0}

        cart_items = user.get("cart", [])
        # Enrich items with latest product info and calculate totals
        enriched_items = []
        subtotal = 0.0
        total_items = 0

        for item in cart_items:
            prod = inventory_manager.get_product_by_id(item["id"])
            if prod:
                qty = item.get("quantity", 1)
                price = prod.get("PRICE", 0.0)
                item_total = round(price * qty, 2)
                subtotal += item_total
                total_items += qty
                enriched_items.append({
                    "id": prod["id"],
                    "PRODUCT_NAME": prod["PRODUCT_NAME"],
                    "PRODUCT_TYPE": prod["PRODUCT_TYPE"],
                    "PRODUCT_SIZE": item.get("size", prod["PRODUCT_SIZE"]),
                    "PRICE": price,
                    "STOCK_REMAINING": prod["STOCK_REMAINING"],
                    "IMAGE": prod.get("IMAGE", ""),
                    "quantity": qty,
                    "item_total": item_total
                })

        return {
            "user_id": user_id,
            "customer_name": user.get("name", "Valued Customer"),
            "items": enriched_items,
            "item_count": total_items,
            "currency": "INR",
            "subtotal": round(subtotal, 2),
            "estimated_tax": 0.0,
            "estimated_total": round(subtotal, 2)
        }

    def add_to_cart(self, user_id: str, product_identifier: str, quantity: int = 1, size: Optional[str] = None) -> Dict[str, Any]:
        """
        Adds a product to the user's cart by product ID or product name matching.
        """
        # Find product
        products = inventory_manager.get_all_products()
        target_prod = None
        ident_clean = product_identifier.lower().strip()

        # Match exact ID or name substring
        for p in products:
            if p["id"].lower() == ident_clean:
                target_prod = p
                break
        
        if not target_prod:
            for p in products:
                if ident_clean in p["PRODUCT_NAME"].lower():
                    if size and size.lower().strip() in p["PRODUCT_SIZE"].lower():
                        target_prod = p
                        break
                    elif not target_prod:
                        target_prod = p

        if not target_prod:
            return {"success": False, "error": f"Product '{product_identifier}' not found in catalog."}

        stock = target_prod.get("STOCK_REMAINING", 0)
        if stock <= 0:
            return {
                "success": False,
                "error": f"'{target_prod['PRODUCT_NAME']}' is currently out of stock."
            }

        users = self._read_users()
        user_idx = None
        for i, u in enumerate(users):
            if u.get("user_id") == user_id:
                user_idx = i
                break

        if user_idx is None:
            # Create user if doesn't exist
            new_user = {
                "user_id": user_id,
                "name": "Guest User",
                "email": f"{user_id}@example.com",
                "shipping_address": "100 Tech Blvd, San Francisco, CA",
                "auto_pay_enabled": True,
                "cart": []
            }
            users.append(new_user)
            user_idx = len(users) - 1

        cart = users[user_idx].setdefault("cart", [])
        chosen_size = size or target_prod["PRODUCT_SIZE"]

        # Check if already in cart
        found_in_cart = False
        for item in cart:
            if item["id"] == target_prod["id"]:
                item["quantity"] = item.get("quantity", 0) + quantity
                found_in_cart = True
                break

        if not found_in_cart:
            cart.append({
                "id": target_prod["id"],
                "quantity": quantity,
                "size": chosen_size
            })

        self._write_users(users)
        updated_cart = self.get_cart(user_id)
        return {
            "success": True,
            "message": f"Added {quantity}x '{target_prod['PRODUCT_NAME']}' (Size: {chosen_size}) to your cart.",
            "product": target_prod,
            "cart": updated_cart
        }

    def remove_from_cart(self, user_id: str, product_identifier: str, quantity: Optional[int] = None) -> Dict[str, Any]:
        """
        Removes a product or decreases quantity in the user's cart.
        """
        users = self._read_users()
        user_obj = None
        for u in users:
            if u.get("user_id") == user_id:
                user_obj = u
                break

        if not user_obj or not user_obj.get("cart"):
            return {"success": False, "error": "Your shopping cart is currently empty."}

        cart = user_obj["cart"]
        ident_clean = product_identifier.lower().strip()

        # Find matching item in cart
        target_item_idx = None
        target_prod = None

        for idx, item in enumerate(cart):
            prod = inventory_manager.get_product_by_id(item["id"])
            if prod:
                if prod["id"].lower() == ident_clean or ident_clean in prod["PRODUCT_NAME"].lower():
                    target_item_idx = idx
                    target_prod = prod
                    break

        if target_item_idx is None:
            return {"success": False, "error": f"Item '{product_identifier}' was not found in your cart."}

        item = cart[target_item_idx]
        current_qty = item.get("quantity", 1)

        if quantity is None or quantity >= current_qty:
            # Remove entirely
            cart.pop(target_item_idx)
            msg = f"Removed '{target_prod['PRODUCT_NAME']}' from your cart."
        else:
            item["quantity"] = current_qty - quantity
            msg = f"Reduced '{target_prod['PRODUCT_NAME']}' quantity by {quantity} (Remaining: {item['quantity']})."

        self._write_users(users)
        updated_cart = self.get_cart(user_id)
        return {
            "success": True,
            "message": msg,
            "cart": updated_cart
        }

    def batch_add_to_cart(self, user_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Adds multiple items to cart in a single batch operation.
        Each item is dict: {'product_name_or_id': '...', 'quantity': 1, 'size': '...'}
        """
        added = []
        errors = []
        for item in items:
            ident = item.get("product_name_or_id") or item.get("id") or item.get("PRODUCT_NAME")
            qty = item.get("quantity", 1)
            size = item.get("size") or item.get("PRODUCT_SIZE")
            if ident:
                res = self.add_to_cart(user_id=user_id, product_identifier=str(ident), quantity=int(qty), size=size)
                if res.get("success"):
                    added.append(res.get("product", {}).get("PRODUCT_NAME", ident))
                else:
                    errors.append(res.get("error", "Unknown error"))

        return {
            "success": len(added) > 0,
            "added_count": len(added),
            "added_items": added,
            "errors": errors,
            "cart": self.get_cart(user_id)
        }

    add_item_by_name = add_to_cart
    remove_item_by_name = remove_from_cart

    def clear_cart(self, user_id: str) -> Dict[str, Any]:
        users = self._read_users()
        for u in users:
            if u.get("user_id") == user_id:
                u["cart"] = []
                break
        self._write_users(users)
        return {"success": True, "message": "Cart cleared."}

    def save_customer_payment_details(self, user_id: str, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves or updates payment card details in the customer schema in users.json.
        """
        users = self._read_users()
        user_obj = None
        for u in users:
            if u.get("user_id") == user_id:
                user_obj = u
                break

        if not user_obj:
            user_obj = {
                "user_id": user_id,
                "name": payment_details.get("card_holder_name", "Valued Customer"),
                "email": f"{user_id}@growthcommerce.ai",
                "shipping_address": "742 Evergreen Terrace, San Francisco, CA 94107",
                "cart": []
            }
            users.append(user_obj)

        user_obj["payment_details"] = payment_details
        self._write_users(users)
        return {
            "success": True,
            "message": "Customer payment details updated successfully.",
            "payment_details": payment_details
        }

    def get_customer_payment_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the saved payment details for the customer.
        """
        user = self.get_user(user_id)
        if user and "payment_details" in user and user["payment_details"]:
            return user["payment_details"]
        return None

    def save_ap2_payment_token(self, user_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        AP2 Protocol: Saves the Razorpay payment authorization token for fully autonomous
        agent payments. Token is set after the user's first verified Razorpay Checkout payment.
        Subsequent agent payments use this token via S2S API — no human checkout popup needed.
        """
        users = self._read_users()
        user_obj = None
        for u in users:
            if u.get("user_id") == user_id:
                user_obj = u
                break
        if not user_obj:
            user_obj = {
                "user_id": user_id,
                "name": "Valued Customer",
                "email": f"{user_id}@growthcommerce.ai",
                "shipping_address": "742 Evergreen Terrace, San Francisco, CA 94107",
                "cart": []
            }
            users.append(user_obj)
        user_obj["ap2_payment_token"] = token_data
        with _lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)
        return {"success": True, "message": "AP2 payment token saved. Agent can now auto-pay.", "token_data": token_data}

    def get_ap2_payment_token(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        AP2 Protocol: Retrieves the Razorpay authorization token for autonomous agent payment.
        Returns None if no token exists (user must authorize via Razorpay Checkout first).
        """
        user = self.get_user(user_id)
        if user and user.get("ap2_payment_token"):
            return user["ap2_payment_token"]
        return None

cart_manager = CartManager()
