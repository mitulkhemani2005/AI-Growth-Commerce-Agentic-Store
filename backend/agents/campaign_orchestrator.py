"""Persisted Nova promotions with reversible, floor-bounded price changes."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from backend.config import data_file
from backend.async_store import AsyncJSONStore
from backend.transactions import serialized

CAMPAIGNS_FILE = data_file("campaigns.json")


class CampaignOrchestrator:
    def __init__(self, inventory_manager, message_bus=None, buyer_manager=None):
        self.inventory_manager = inventory_manager
        self.message_bus = message_bus
        self.buyer_manager = buyer_manager
        self.store = AsyncJSONStore(CAMPAIGNS_FILE, list)

    @staticmethod
    def _overlaps(first, second):
        return first.upper() == "ALL" or second.upper() == "ALL" or first.upper() == second.upper()

    def _restore(self, campaign):
        for pid, prior in campaign.get("original_prices", {}).items():
            product = self.inventory_manager.get_product_by_id(pid)
            if product and product["PRICE"] == campaign.get("applied_prices", {}).get(pid):
                self.inventory_manager.update_price(pid, prior)
        campaign["status"] = "COMPLETED"

    def _expire(self, campaigns):
        changed = False
        now = datetime.now(timezone.utc)
        for campaign in campaigns:
            if campaign.get("status") != "ACTIVE" or not campaign.get("expires_at"):
                continue
            try:
                expires = datetime.fromisoformat(campaign["expires_at"].replace("Z", "+00:00"))
                if expires <= now:
                    self._restore(campaign)
                    changed = True
            except (ValueError, TypeError):
                self._restore(campaign)
                changed = True
        if changed:
            self.store.set(campaigns)

    @serialized
    def get_all_campaigns(self) -> List[Dict[str, Any]]:
        campaigns = self.store.get()
        self._expire(campaigns)
        return campaigns

    def get_active_campaign(self) -> Optional[Dict[str, Any]]:
        return next((c for c in self.get_all_campaigns() if c.get("status") == "ACTIVE"), None)

    @serialized
    def launch_campaign(self, title: str, category: str, discount_percent: float,
                        duration_hours: int = 24, auto_activate: bool = True) -> Dict[str, Any]:
        if not title.strip() or not 1 <= discount_percent <= 25 or not 1 <= duration_hours <= 8760:
            return {"success": False, "error": "Provide a title, a 1–25% discount, and a positive duration."}
        categories = {p.get("PRODUCT_TYPE", "").lower(): p.get("PRODUCT_TYPE") for p in self.inventory_manager.get_all_products()}
        if category.lower() != "all" and category.lower() not in categories:
            return {"success": False, "error": "Unknown product category."}
        category = "ALL" if category.lower() == "all" else categories[category.lower()]
        campaign = {"id": f"camp_{uuid.uuid4().hex[:12]}", "title": title.strip(), "category": category,
                    "discount_percent": discount_percent, "duration_hours": duration_hours,
                    "status": "SCHEDULED", "launched_at": None,
                    "banner_text": f"{title.upper()}: UP TO {discount_percent:g}% OFF {category.upper()}",
                    "total_revenue_generated": 0.0, "orders_count": 0}
        campaigns = self.get_all_campaigns()
        campaigns.insert(0, campaign)
        self.store.set(campaigns)
        if auto_activate:
            activated = self.activate_campaign(campaign["id"])
            return {**activated, "adjusted_products_count": activated.get("adjusted_count", 0)}
        return {"success": True, "campaign": campaign, "adjusted_products_count": 0,
                "message": f"Campaign '{title}' scheduled."}

    @serialized
    def activate_campaign(self, campaign_id: str) -> Dict[str, Any]:
        campaigns = self.get_all_campaigns()
        target = next((c for c in campaigns if c.get("id") == campaign_id), None)
        if not target:
            return {"success": False, "error": "Campaign not found."}
        if target.get("status") == "ACTIVE":
            return {"success": True, "campaign": target, "adjusted_count": 0, "message": "Campaign already active."}
        for other in campaigns:
            if other.get("status") == "ACTIVE" and self._overlaps(target["category"], other["category"]):
                self._restore(other)
        now = datetime.now(timezone.utc)
        target.update(status="ACTIVE", launched_at=now.isoformat(),
                      expires_at=(now + timedelta(hours=target.get("duration_hours", 24))).isoformat(),
                      original_prices={}, applied_prices={})
        count = 0
        for product in self.inventory_manager.get_all_products():
            if target["category"].upper() != "ALL" and product.get("PRODUCT_TYPE", "").lower() != target["category"].lower():
                continue
            price = float(product["PRICE"])
            discounted = max(float(product.get("BASE_PRICE", 0)), round(price * (1 - target["discount_percent"] / 100), 2))
            target["original_prices"][product["id"]] = price
            target["applied_prices"][product["id"]] = discounted
            if price != discounted:
                self.inventory_manager.update_price(product["id"], discounted)
                count += 1
        self.store.set(campaigns)
        return {"success": True, "campaign": target, "adjusted_count": count,
                "message": f"Campaign '{target['title']}' activated."}

    @serialized
    def stop_campaign(self, campaign_id: str) -> Dict[str, Any]:
        campaigns = self.get_all_campaigns()
        target = next((c for c in campaigns if c.get("id") == campaign_id), None)
        if not target:
            return {"success": False, "error": "Campaign not found."}
        self._restore(target)
        self.store.set(campaigns)
        return {"success": True, "campaign": target, "message": "Campaign stopped."}

    @serialized
    def delete_campaign(self, campaign_id: str) -> Dict[str, Any]:
        campaigns = self.get_all_campaigns()
        target = next((c for c in campaigns if c.get("id") == campaign_id), None)
        if not target:
            return {"success": False, "error": "Campaign not found."}
        if target.get("status") == "ACTIVE":
            self._restore(target)
        self.store.set([c for c in campaigns if c.get("id") != campaign_id])
        return {"success": True, "message": "Campaign deleted."}
