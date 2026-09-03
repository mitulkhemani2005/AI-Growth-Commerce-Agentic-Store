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

    def launch_campaign(self, title: str, category: str, discount_percent: float, duration_hours: int = 24) -> Dict[str, Any]:
        """
        Launches an autonomous promotional campaign.
        - Applies bounded price adjustments on the target category (never breaching BASE_PRICE floor).
        - Broadcasts notification across the Inter-Agent Message Bus.
        - Notifies the 5 AI shoppers fleet to evaluate new deals.
        """
        discount_percent = min(max(float(discount_percent), 1.0), 25.0)  # Gated bounds: 1% to 25%
        campaign_id = f"camp_{int(time.time())}"
        banner_text = f"🔥 {title.upper()}: UP TO {discount_percent:.0f}% OFF {category.upper()} • 0% TAX STOREWIDE"

        # Mark previous active campaigns as COMPLETED
        for c in self.campaigns:
            if c.get("status") == "ACTIVE":
                c["status"] = "COMPLETED"

        new_campaign = {
            "id": campaign_id,
            "title": title,
            "category": category,
            "discount_percent": discount_percent,
            "banner_text": banner_text,
            "duration_hours": duration_hours,
            "status": "ACTIVE",
            "launched_at": datetime.utcnow().isoformat(),
            "total_revenue_generated": 0.0,
            "orders_count": 0
        }
        self.campaigns.insert(0, new_campaign)
        self._save_campaigns()

        # 1. Adjust prices in inventory within immutable BASE_PRICE floor
        products = self.inventory_manager.get_all_products()
        adjusted_count = 0
        multiplier = 1.0 - (discount_percent / 100.0)

        for p in products:
            if category == "ALL" or (p.get("PRODUCT_TYPE", "").lower() == category.lower()):
                base_price = float(p.get("BASE_PRICE", p.get("PRICE", 100)))
                current_price = float(p.get("PRICE", base_price))
                new_price = max(base_price, round(current_price * multiplier, 2))
                
                if new_price != current_price:
                    self.inventory_manager.update_price(p.get("id"), new_price)
                    adjusted_count += 1


        # 2. Broadcast on Inter-Agent Message Bus
        if self.message_bus:
            try:
                self.message_bus.send_message(
                    from_agent="Campaign Orchestrator",
                    to_agent="ALL_AGENTS",
                    subject=f"CAMPAIGN_LAUNCH: {title}",
                    content={
                        "campaign_id": campaign_id,
                        "category": category,
                        "discount": f"{discount_percent}%",
                        "adjusted_products": adjusted_count,
                        "directive": "Price Manager & Inventory Manager align stock and dynamic margin protection."
                    }
                )
            except Exception:
                pass

        # 3. Trigger 5 AI buyers to evaluate deals
        if self.buyer_manager:
            try:
                self.buyer_manager.trigger_step()
            except Exception:
                pass

        return {
            "success": True,
            "campaign": new_campaign,
            "adjusted_products_count": adjusted_count,
            "message": f"Campaign '{title}' launched successfully! {adjusted_count} products adjusted within base price floor."
        }
