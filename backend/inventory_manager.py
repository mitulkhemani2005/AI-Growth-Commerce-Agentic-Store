import json
import os
import threading
import time
from typing import List, Dict, Any, Optional

INVENTORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "inventory.json"))
_lock = threading.RLock()


class InventoryManager:
    def __init__(self, file_path: str = INVENTORY_FILE):
        self.file_path = file_path

    def _read_inventory(self) -> List[Dict[str, Any]]:
        with _lock:
            if not os.path.exists(self.file_path):
                return []
            for _ in range(5):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    time.sleep(0.02)
            return []

    def _write_inventory(self, data: List[Dict[str, Any]]) -> None:
        with _lock:
            tmp_file = f"{self.file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_file, self.file_path)
            except Exception:
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except Exception:
                        pass
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Returns all products in inventory."""
        return self._read_inventory()

    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        products = self._read_inventory()
        for p in products:
            if p.get("id") == product_id or p.get("PRODUCT_NAME", "").lower() == product_id.lower():
                return p
        return None

    def search_products(
        self,
        query: Optional[str] = None,
        product_type: Optional[str] = None,
        product_types: Optional[List[str]] = None,
        size: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search products with support for single and multiple product types, size, price, and keywords.
        """
        products = self._read_inventory()
        results = []

        query_terms = [t.lower().strip() for t in query.split()] if query else []
        target_types = []
        if product_type:
            target_types.append(product_type.lower().strip())
        if product_types:
            target_types.extend([t.lower().strip() for t in product_types if t])

        for p in products:
            p_name = p.get("PRODUCT_NAME", "").lower()
            p_desc = p.get("DESCRIPTION", "").lower()
            p_type = p.get("PRODUCT_TYPE", "").lower()
            p_tags = [t.lower() for t in p.get("TAGS", [])]
            p_price = p.get("PRICE", 0.0)
            p_stock = p.get("STOCK_REMAINING", 0)
            p_size = p.get("PRODUCT_SIZE", "")

            # Filter by multiple product types if specified
            if target_types:
                match_type = any(
                    tt in p_type or tt in p_tags or any(tt in name_word for name_word in p_name.split())
                    for tt in target_types
                )
                if not match_type:
                    continue

            # Filter by size
            if size and size.lower() != "all":
                if size.lower() not in p_size.lower():
                    continue

            # Filter by price range
            if min_price is not None and p_price < min_price:
                continue
            if max_price is not None and p_price > max_price:
                continue

            # Filter by in-stock
            if in_stock_only and p_stock <= 0:
                continue

            # Keyword query matching
            if query_terms:
                matched_all = True
                for term in query_terms:
                    term_match = (
                        term in p_name
                        or term in p_desc
                        or term in p_type
                        or any(term in tag for tag in p_tags)
                        or term == p.get("id", "").lower()
                    )
                    if not term_match:
                        matched_all = False
                        break
                if not matched_all:
                    continue

            results.append(p)

        return results

    def get_product_sizes(self, product_name: str) -> List[Dict[str, Any]]:
        """Finds all available variants/sizes for a given product base name."""
        products = self._read_inventory()
        base_name = product_name.lower().strip()
        variants = []
        for p in products:
            p_name = p.get("PRODUCT_NAME", "").lower()
            if base_name in p_name or p_name in base_name:
                variants.append({
                    "id": p.get("id"),
                    "name": p.get("PRODUCT_NAME"),
                    "size": p.get("PRODUCT_SIZE", "Standard"),
                    "stock": p.get("STOCK_REMAINING", 0),
                    "price": p.get("PRICE", 0.0),
                    "base_price": p.get("BASE_PRICE", p.get("PRICE", 0.0))
                })
        return variants

    def deduct_stock(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Atomically decrements STOCK_REMAINING for a list of items upon order placement.
        Items format: [{'id': 'prod_001', 'quantity': 2}, ...]
        """
        with _lock:
            products = self._read_inventory()
            products_map = {p["id"]: p for p in products}

            # First validate all items have sufficient stock
            for item in items:
                p_id = item.get("id")
                qty = item.get("quantity", 1)
                if p_id not in products_map:
                    return {"success": False, "error": f"Product ID {p_id} not found."}
                current_stock = products_map[p_id].get("STOCK_REMAINING", 0)
                if current_stock < qty:
                    p_name = products_map[p_id].get("PRODUCT_NAME", p_id)
                    return {
                        "success": False,
                        "error": f"Insufficient stock for '{p_name}'. Available: {current_stock}, Requested: {qty}"
                    }

            # If all valid, deduct stock
            updated_items = []
            for item in items:
                p_id = item.get("id")
                qty = item.get("quantity", 1)
                products_map[p_id]["STOCK_REMAINING"] -= qty
                updated_items.append({
                    "id": p_id,
                    "PRODUCT_NAME": products_map[p_id]["PRODUCT_NAME"],
                    "PRODUCT_SIZE": products_map[p_id]["PRODUCT_SIZE"],
                    "new_stock": products_map[p_id]["STOCK_REMAINING"]
                })

            # Save updated inventory atomically
            self._write_inventory(products)

            return {
                "success": True,
                "deducted_items": updated_items
            }

    def restore_stock(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Atomically increments STOCK_REMAINING when an order is refunded or cancelled.
        Items format: [{'id': 'prod_001', 'quantity': 1}, ...]
        """
        with _lock:
            products = self._read_inventory()
            products_map = {p["id"]: p for p in products}
            restored_items = []
            for item in items:
                p_id = item.get("id")
                qty = item.get("quantity", 1)
                if p_id in products_map:
                    products_map[p_id]["STOCK_REMAINING"] = products_map[p_id].get("STOCK_REMAINING", 0) + qty
                    restored_items.append({
                        "id": p_id,
                        "PRODUCT_NAME": products_map[p_id]["PRODUCT_NAME"],
                        "new_stock": products_map[p_id]["STOCK_REMAINING"]
                    })

            self._write_inventory(products)

            return {
                "success": True,
                "restored_items": restored_items
            }

    def update_stock(self, product_id: str, new_stock: int) -> Dict[str, Any]:
        """Directly sets STOCK_REMAINING for a product."""
        with _lock:
            products = self._read_inventory()
            found = False
            target = None
            for p in products:
                if p.get("id") == product_id or p.get("PRODUCT_NAME", "").lower() == product_id.lower():
                    p["STOCK_REMAINING"] = max(0, int(new_stock))
                    found = True
                    target = p
                    break
            if not found:
                return {"success": False, "error": f"Product '{product_id}' not found."}

            self._write_inventory(products)

            return {
                "success": True,
                "message": f"Updated stock for '{target['PRODUCT_NAME']}' to {target['STOCK_REMAINING']} units.",
                "product": target
            }

    def update_price(self, product_id: str, new_price: float, base_price: Optional[float] = None, enforce_base_price: bool = True) -> Dict[str, Any]:
        """Directly sets PRICE for a product, ensuring it meets or exceeds BASE_PRICE floor if enforced."""
        with _lock:
            products = self._read_inventory()
            found = False
            target = None
            for p in products:
                if p.get("id") == product_id or p.get("PRODUCT_NAME", "").lower() == product_id.lower():
                    if base_price is not None:
                        p["BASE_PRICE"] = round(float(base_price), 2)
                    
                    floor = p.get("BASE_PRICE", 0.0) if enforce_base_price else 0.0
                    p["PRICE"] = round(max(floor, float(new_price)), 2)
                    found = True
                    target = p
                    break
            if not found:
                return {"success": False, "error": f"Product '{product_id}' not found."}

            self._write_inventory(products)

            return {
                "success": True,
                "message": f"Updated price for '{target['PRODUCT_NAME']}' to ₹{target['PRICE']:,.2f} (Base: ₹{target.get('BASE_PRICE', target['PRICE']):,.2f}).",
                "product": target
            }

    def update_base_price(self, product_id: str, new_base_price: float) -> Dict[str, Any]:
        """Sets the BASE_PRICE threshold for a product and adjusts current PRICE if below base."""
        with _lock:
            products = self._read_inventory()
            found = False
            target = None
            for p in products:
                if p.get("id") == product_id or p.get("PRODUCT_NAME", "").lower() == product_id.lower():
                    p["BASE_PRICE"] = round(float(new_base_price), 2)
                    if p.get("PRICE", 0.0) < p["BASE_PRICE"]:
                        p["PRICE"] = p["BASE_PRICE"]
                    found = True
                    target = p
                    break
            if not found:
                return {"success": False, "error": f"Product '{product_id}' not found."}

            self._write_inventory(products)

            return {
                "success": True,
                "message": f"Updated BASE_PRICE for '{target['PRODUCT_NAME']}' to ₹{target['BASE_PRICE']:,.2f}.",
                "product": target
            }

    def restock_product(self, product_identifier: str, quantity: int) -> Dict[str, Any]:
        """Increments stock for a product by a specified quantity."""
        with _lock:
            products = self._read_inventory()
            found = False
            target = None
            ident_clean = product_identifier.lower().strip()
            for p in products:
                if p.get("id", "").lower() == ident_clean or ident_clean in p.get("PRODUCT_NAME", "").lower():
                    p["STOCK_REMAINING"] = p.get("STOCK_REMAINING", 0) + max(1, int(quantity))
                    target = p
                    found = True
                    break
            if not found:
                return {"success": False, "error": f"Product '{product_identifier}' not found."}

            self._write_inventory(products)

            return {
                "success": True,
                "message": f"Restocked {quantity} units for '{target['PRODUCT_NAME']}'. New stock: {target['STOCK_REMAINING']}.",
                "product": target
            }

    def add_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a brand new product to the catalog with BASE_PRICE."""
        with _lock:
            products = self._read_inventory()
            import uuid
            new_id = product_data.get("id") or f"prod_{uuid.uuid4().hex[:6]}"
            base_p = float(product_data.get("BASE_PRICE", product_data.get("PRICE", 49.99)))
            price_p = max(base_p, float(product_data.get("PRICE", base_p)))
            new_prod = {
                "id": new_id,
                "PRODUCT_NAME": product_data.get("PRODUCT_NAME", "New Product"),
                "PRODUCT_TYPE": product_data.get("PRODUCT_TYPE", "Accessories"),
                "PRODUCT_SIZE": product_data.get("PRODUCT_SIZE", "One Size"),
                "STOCK_REMAINING": max(0, int(product_data.get("STOCK_REMAINING", 10))),
                "BASE_PRICE": round(base_p, 2),
                "PRICE": round(price_p, 2),
                "RATING": float(product_data.get("RATING", 5.0)),
                "DESCRIPTION": product_data.get("DESCRIPTION", "Premium product in the autonomous catalog."),
                "IMAGE": product_data.get("IMAGE", "/static/images/cyberflex_runner.svg"),
                "TAGS": product_data.get("TAGS", ["new", "store"])
            }
            products.append(new_prod)
            self._write_inventory(products)

            return {
                "success": True,
                "message": f"Added product '{new_prod['PRODUCT_NAME']}' (ID: {new_prod['id']}, Base: ₹{new_prod['BASE_PRICE']:,.2f}, Price: ₹{new_prod['PRICE']:,.2f}).",
                "product": new_prod
            }

    def bulk_price_adjustment(self, category: Optional[str] = None, percentage: float = 0.0) -> Dict[str, Any]:
        """
        Adjusts prices by percentage (+10 for +10%, -5 for -5% discount).
        Respects BASE_PRICE as the absolute minimum threshold.
        """
        with _lock:
            products = self._read_inventory()
            multiplier = 1.0 + (float(percentage) / 100.0)
            updated_count = 0
            cat_clean = category.lower().strip() if category and category.lower() != "all" else None

            for p in products:
                if not cat_clean or cat_clean in p.get("PRODUCT_TYPE", "").lower():
                    current_price = p.get("PRICE", 10.0)
                    base_price = p.get("BASE_PRICE", 1.0)
                    new_price = max(base_price, round(current_price * multiplier, 2))
                    p["PRICE"] = new_price
                    updated_count += 1

            self._write_inventory(products)

            action = "increased" if percentage >= 0 else "discounted"
            return {
                "success": True,
                "message": f"Successfully {action} prices by {abs(percentage)}% across {updated_count} products (BASE_PRICE floor respected).",
                "updated_count": updated_count,
                "percentage": percentage
            }

    def update_product_ai_summary(self, product_id: str, ai_summary: str, rating: Optional[float] = None) -> Dict[str, Any]:
        """Updates product with AI-generated review summary and optional recalculated rating."""
        with _lock:
            products = self._read_inventory()
            target = None
            for p in products:
                if p.get("id") == product_id:
                    p["AI_REVIEW_SUMMARY"] = ai_summary
                    if rating is not None:
                        p["RATING"] = round(float(rating), 1)
                    target = p
                    break
            if not target:
                return {"success": False, "error": f"Product '{product_id}' not found."}

            self._write_inventory(products)

            return {
                "success": True,
                "message": f"AI review summary updated for '{target['PRODUCT_NAME']}'.",
                "product": target
            }

    def get_low_stock_products(self, threshold: int = 5) -> List[Dict[str, Any]]:
        """Returns all products with stock at or below the threshold."""
        products = self._read_inventory()
        return [p for p in products if p.get("STOCK_REMAINING", 0) <= threshold]

# Global singleton
inventory_manager = InventoryManager()
