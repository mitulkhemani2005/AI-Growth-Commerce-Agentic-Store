"""
Nava: Agentic AI Store — Campaign Orchestrator Agent
Orchestrates autonomous promotional marketing campaigns, targeted flash sales,
marquee announcement updates, and demand stimulation for autonomous AI buyers.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

CAMPAIGNS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "campaigns.json")

DEFAULT_CAMPAIGNS = [
    {
        "id": "camp_5g_surge",
        "title": "5G FLAGSHIP POWER DROP",
        "category": "Mobiles",
        "discount_percent": 8.0,
        "banner_text": "⚡ 5G FLAGSHIP POWER DROP: 8% OFF MOBILES (0% TAX) • AUTONOMOUS FLASH SALE ACTIVE",
        "status": "ACTIVE",
        "launched_at": datetime.utcnow().isoformat(),
        "total_revenue_generated": 142850.0
    },
    {
        "id": "camp_audio_immersion",
        "title": "STUDIO ACOUSTICS FESTIVAL",
        "category": "Audio",
        "discount_percent": 12.0,
        "banner_text": "🎧 STUDIO ACOUSTICS FESTIVAL: 12% OFF ANC AUDIO GEAR • VERIFIED AUDIOPHILE DROPS",
        "status": "SCHEDULED",
        "launched_at": datetime.utcnow().isoformat(),
        "total_revenue_generated": 48200.0
    }
]

class CampaignOrchestrator:
    def __init__(self, inventory_manager, message_bus=None, buyer_manager=None):
        self.inventory_manager = inventory_manager
        self.message_bus = message_bus
        self.buyer_manager = buyer_manager
        self.campaigns = self._load_campaigns()

    def _load_campaigns(self) -> List[Dict[str, Any]]:
        if os.path.exists(CAMPAIGNS_FILE):
            try:
                with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CAMPAIGNS

    def _save_campaigns(self):
        os.makedirs(os.path.dirname(CAMPAIGNS_FILE), exist_ok=True)
        with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.campaigns, f, indent=2)

    def get_active_campaign(self) -> Optional[Dict[str, Any]]:
        for c in self.campaigns:
            if c.get("status") == "ACTIVE":
                return c
        return self.campaigns[0] if self.campaigns else None

    def get_all_campaigns(self) -> List[Dict[str, Any]]:
        return self.campaigns

    def launch_campaign(self, title: str, category: str, discount_percent: float, duration_hours: int = 24, auto_activate: bool = True) -> Dict[str, Any]:
        """
        Creates a promotional campaign.
        Enforces: AT MOST 1 ACTIVE CAMPAIGN PER CATEGORY.
        """
        discount_percent = min(max(float(discount_percent), 1.0), 25.0)  # Gated bounds: 1% to 25%
        campaign_id = f"camp_{int(time.time())}"
        banner_text = f"🔥 {title.upper()}: UP TO {discount_percent:.0f}% OFF {category.upper()} • 0% TAX STOREWIDE"

        target_cat = category.upper()
        # Enforce at most 1 active campaign per category
        if auto_activate:
            for c in self.campaigns:
                if c.get("status") == "ACTIVE":
                    cat = c.get("category", "ALL").upper()
                    if target_cat == "ALL" or cat == "ALL" or cat == target_cat:
                        c["status"] = "COMPLETED"

        new_campaign = {
            "id": campaign_id,
            "title": title,
            "category": category,
            "discount_percent": discount_percent,
            "banner_text": banner_text,
            "duration_hours": duration_hours,
            "status": "ACTIVE" if auto_activate else "SCHEDULED",
            "launched_at": datetime.utcnow().isoformat(),
            "total_revenue_generated": 0.0,
            "orders_count": 0
        }
        self.campaigns.insert(0, new_campaign)
        self._save_campaigns()

        # Adjust prices if active
        adjusted_count = 0
        if auto_activate:
            products = self.inventory_manager.get_all_products()
            multiplier = 1.0 - (discount_percent / 100.0)
            for p in products:
                if category == "ALL" or (p.get("PRODUCT_TYPE", "").lower() == category.lower()):
                    base_price = float(p.get("BASE_PRICE", p.get("PRICE", 100)))
                    current_price = float(p.get("PRICE", base_price))
                    new_price = max(base_price, round(current_price * multiplier, 2))
                    if new_price != current_price:
                        self.inventory_manager.update_price(p.get("id"), new_price)
                        adjusted_count += 1

        return {
            "success": True,
            "campaign": new_campaign,
            "adjusted_products_count": adjusted_count,
            "message": f"Campaign '{title}' created for {category} (At most 1 active campaign per category enforced)."
        }

    def activate_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Activates a campaign selected by human store owner.
        Enforces: AT MOST 1 ACTIVE CAMPAIGN PER CATEGORY.
        """
        target = None
        for c in self.campaigns:
            if c.get("id") == campaign_id:
                target = c
                break

        if not target:
            return {"success": False, "error": f"Campaign '{campaign_id}' not found."}

        target_cat = target.get("category", "ALL").upper()
        deactivated = []

        # Enforce at most 1 active campaign per category
        for c in self.campaigns:
            if c.get("id") != campaign_id and c.get("status") == "ACTIVE":
                cat = c.get("category", "ALL").upper()
                if target_cat == "ALL" or cat == "ALL" or cat == target_cat:
                    c["status"] = "COMPLETED"
                    deactivated.append(c.get("title"))

        target["status"] = "ACTIVE"
        target["launched_at"] = datetime.utcnow().isoformat()
        self._save_campaigns()

        # Apply bounded price discounts for this category
        discount_percent = float(target.get("discount_percent", 10.0))
        multiplier = 1.0 - (discount_percent / 100.0)
        products = self.inventory_manager.get_all_products()
        adjusted_count = 0

        for p in products:
            p_cat = p.get("PRODUCT_TYPE", "").upper()
            if target_cat == "ALL" or p_cat == target_cat:
                base_price = float(p.get("BASE_PRICE", p.get("PRICE", 100)))
                current_price = float(p.get("PRICE", base_price))
                new_price = max(base_price, round(current_price * multiplier, 2))
                if new_price != current_price:
                    self.inventory_manager.update_price(p.get("id"), new_price)
                    adjusted_count += 1

        msg = f"Campaign '{target['title']}' is now ACTIVE for {target.get('category')}."
        if deactivated:
            msg += f" (Deactivated previous {', '.join(deactivated)} to enforce 1 active campaign per category rule)."

        return {
            "success": True,
            "message": msg,
            "campaign": target,
            "adjusted_count": adjusted_count
        }

    def stop_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Stops/pauses an active campaign selected by human store owner.
        Reverts category prices back to standard margin above base price floor.
        """
        target = None
        for c in self.campaigns:
            if c.get("id") == campaign_id:
                target = c
                break

        if not target:
            return {"success": False, "error": f"Campaign '{campaign_id}' not found."}

        target["status"] = "COMPLETED"
        self._save_campaigns()

        target_cat = target.get("category", "ALL").upper()
        products = self.inventory_manager.get_all_products()
        reverted_count = 0

        for p in products:
            p_cat = p.get("PRODUCT_TYPE", "").upper()
            if target_cat == "ALL" or p_cat == target_cat:
                base_price = float(p.get("BASE_PRICE", 100))
                standard_price = round(base_price * 1.217, 2)
                self.inventory_manager.update_price(p.get("id"), standard_price)
                reverted_count += 1

        return {
            "success": True,
            "message": f"Campaign '{target['title']}' has been STOPPED. {reverted_count} product prices restored.",
            "campaign": target
        }

    def delete_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Deletes a campaign selected by human store owner."""
        idx_to_remove = None
        for idx, c in enumerate(self.campaigns):
            if c.get("id") == campaign_id:
                idx_to_remove = idx
                break

        if idx_to_remove is None:
            return {"success": False, "error": f"Campaign '{campaign_id}' not found."}

        removed = self.campaigns.pop(idx_to_remove)
        if removed.get("status") == "ACTIVE":
            target_cat = removed.get("category", "ALL").upper()
            products = self.inventory_manager.get_all_products()
            for p in products:
                if target_cat == "ALL" or p.get("PRODUCT_TYPE", "").upper() == target_cat:
                    base_price = float(p.get("BASE_PRICE", 100))
                    self.inventory_manager.update_price(p.get("id"), round(base_price * 1.217, 2))

        self._save_campaigns()
        return {
            "success": True,
            "message": f"Campaign '{removed.get('title')}' deleted successfully."
        }

