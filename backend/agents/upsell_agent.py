"""
Nava: Agentic AI Store — Cross-Sell & Upsell Intelligence Agent
Analyzes current customer carts, browsing behavior, and hardware specifications
to recommend high-margin, complementary hardware accessories with explainable rationales.
"""

from typing import List, Dict, Any, Optional

# Complementary affinity matrix by product category & keyword
CROSS_SELL_MATRIX = {
    "Mobiles": [
        {
            "target_type": "Accessories",
            "keywords": ["charger", "gan", "cable", "case"],
            "rationale": "Recommended pairing: 100W GaN rapid charge support and military-grade drop protection."
        },
        {
            "target_type": "Audio",
            "keywords": ["anc", "earbuds", "audio"],
            "rationale": "Pairs seamlessly via Bluetooth 5.4 with low-latency spatial audio."
        }
    ],
    "Laptops": [
        {
            "target_type": "Accessories",
            "keywords": ["hub", "charger", "sleeve", "dock"],
            "rationale": "Essential companion: 100W GaN fast charging and multiport Thunderbolt expansion."
        },
        {
            "target_type": "Audio",
            "keywords": ["anc", "headphones", "studio"],
            "rationale": "High-fidelity studio acoustics with active noise cancellation for productivity."
        }
    ],
    "Audio": [
        {
            "target_type": "Accessories",
            "keywords": ["charger", "cable", "case"],
            "rationale": "Ensure uninterrupted listening with rapid charging and protective travel hardware."
        }
    ]
}

class UpsellAgent:
    def __init__(self, inventory_manager):
        self.inventory_manager = inventory_manager

    def get_recommendations_for_cart(self, cart_items: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Computes explainable, margin-preserving cross-sell recommendations
        based on products currently present in the customer's cart.
        """
        all_products = self.inventory_manager.get_all_products()
        cart_product_ids = {item.get("id") or item.get("product_id") for item in cart_items}
        
        recommendations = []
        seen_ids = set(cart_product_ids)

        for item in cart_items:
            cat = item.get("PRODUCT_TYPE", "")
            rules = CROSS_SELL_MATRIX.get(cat, CROSS_SELL_MATRIX.get("Mobiles", []))
            
            for rule in rules:
                target_type = rule["target_type"]
                keywords = rule["keywords"]
                
                for candidate in all_products:
                    cand_id = candidate.get("id")
                    if cand_id in seen_ids:
                        continue
                    
                    cand_type = candidate.get("PRODUCT_TYPE", "")
                    cand_stock = candidate.get("STOCK_REMAINING", 0)
                    cand_name = candidate.get("PRODUCT_NAME", "").lower()
                    
                    # Must be in stock and match target category or keywords
                    if cand_stock > 0 and (cand_type == target_type or any(k in cand_name for k in keywords)):
                        base_price = float(candidate.get("BASE_PRICE", candidate.get("PRICE", 100)))
                        selling_price = float(candidate.get("PRICE", base_price))
                        
                        # Bundle discount: 10% off selling price, bounded by BASE_PRICE floor
                        discounted_bundle_price = max(base_price, round(selling_price * 0.90, 2))
                        savings = round(selling_price - discounted_bundle_price, 2)
                        
                        rec = {
                            "product_id": cand_id,
                            "product_name": candidate.get("PRODUCT_NAME"),
                            "product_type": cand_type,
                            "image": candidate.get("IMAGE"),
                            "original_price": selling_price,
                            "bundle_price": discounted_bundle_price,
                            "savings": savings,
                            "stock": cand_stock,
                            "rationale": rule["rationale"],
                            "paired_with": item.get("PRODUCT_NAME", "Cart Item"),
                            "is_bounded_by_floor": discounted_bundle_price == base_price
                        }
                        recommendations.append(rec)
                        seen_ids.add(cand_id)
                        
                        if len(recommendations) >= limit:
                            return recommendations
                            
        # Fallback if no specific category matched: recommend top in-stock accessory
        if len(recommendations) < limit:
            for candidate in all_products:
                cand_id = candidate.get("id")
                if cand_id not in seen_ids and candidate.get("STOCK_REMAINING", 0) > 0:
                    base_price = float(candidate.get("BASE_PRICE", candidate.get("PRICE", 100)))
                    selling_price = float(candidate.get("PRICE", base_price))
                    rec = {
                        "product_id": cand_id,
                        "product_name": candidate.get("PRODUCT_NAME"),
                        "product_type": candidate.get("PRODUCT_TYPE"),
                        "image": candidate.get("IMAGE"),
                        "original_price": selling_price,
                        "bundle_price": max(base_price, round(selling_price * 0.90, 2)),
                        "savings": round(selling_price - max(base_price, round(selling_price * 0.90, 2)), 2),
                        "stock": candidate.get("STOCK_REMAINING", 0),
                        "rationale": "Popular customer accessory pairing with 0% tax.",
                        "paired_with": "Storewide Essential",
                        "is_bounded_by_floor": False
                    }
                    recommendations.append(rec)
                    seen_ids.add(cand_id)
                    if len(recommendations) >= limit:
                        break

        return recommendations
