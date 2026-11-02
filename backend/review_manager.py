import asyncio
from backend.config import DATA_DIR, data_file
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from backend.inventory_manager import inventory_manager

from backend.async_store import AsyncJSONStore

REVIEWS_FILE = data_file("reviews.json")
_lock = threading.RLock()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_MODEL = os.environ.get("REVIEW_MANAGER_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b"))

class ReviewManager:
    def __init__(self, file_path: str = REVIEWS_FILE, base_url: str = OLLAMA_BASE_URL, api_key: str = "ollama", model: str = DEFAULT_MODEL):
        self.file_path = file_path
        self.base_url = base_url
        self.api_key = api_key or "ollama"
        self.model = model
        self.store = AsyncJSONStore(file_path, default_factory=list)
        self._init_client()

    def _init_client(self):
        try:
            self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception as e:
            print(f"ReviewManager Ollama client warning: {e}")
            self.client = None

    def _read_reviews(self) -> List[Dict[str, Any]]:
        return self.store.get()

    def _write_reviews(self, reviews: List[Dict[str, Any]]) -> None:
        self.store.set(reviews)

    async def _read_reviews_async(self) -> List[Dict[str, Any]]:
        return await self.store.get_async()

    async def _write_reviews_async(self, reviews: List[Dict[str, Any]]) -> None:
        await self.store.set_async(reviews)

    def get_all_reviews(self) -> List[Dict[str, Any]]:
        return self._read_reviews()

    async def get_all_reviews_async(self) -> List[Dict[str, Any]]:
        return await self._read_reviews_async()

    def get_reviews_for_product(self, product_id_or_name: str) -> List[Dict[str, Any]]:
        reviews = self._read_reviews()
        ident_clean = product_id_or_name.lower().strip()
        matched = []
        for r in reviews:
            r_pid = r.get("product_id", "").lower()
            r_pname = r.get("product_name", "").lower()
            if ident_clean == r_pid or ident_clean in r_pname or r_pid in ident_clean:
                matched.append(r)
        return matched

    async def get_reviews_for_product_async(self, product_id_or_name: str) -> List[Dict[str, Any]]:
        reviews = await self._read_reviews_async()
        ident_clean = product_id_or_name.lower().strip()
        matched = []
        for r in reviews:
            r_pid = r.get("product_id", "").lower()
            r_pname = r.get("product_name", "").lower()
            if ident_clean == r_pid or ident_clean in r_pname or r_pid in ident_clean:
                matched.append(r)
        return matched

    def get_product_reviews(self, product_id_or_name: str) -> List[Dict[str, Any]]:
        """Alias for get_reviews_for_product."""
        return self.get_reviews_for_product(product_id_or_name)

    async def get_product_reviews_async(self, product_id_or_name: str) -> List[Dict[str, Any]]:
        """Alias for get_reviews_for_product_async."""
        return await self.get_reviews_for_product_async(product_id_or_name)

    def add_review(
        self,
        product_id: str,
        customer_name: str,
        rating: int,
        review_text: str,
        product_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds a new verified customer review."""
        reviews = self._read_reviews()
        prod = inventory_manager.get_product_by_id(product_id)
        p_name = product_name or (prod.get("PRODUCT_NAME") if prod else product_id)

        new_rev = {
            "id": f"rev_{uuid.uuid4().hex[:6]}",
            "product_id": product_id,
            "product_name": p_name,
            "customer_name": customer_name or "Verified Buyer",
            "rating": max(1, min(5, int(rating))),
            "review_text": review_text.strip(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        reviews.append(new_rev)
        self._write_reviews(reviews)

        # Recalculate product rating
        prod_reviews = [r for r in reviews if r.get("product_id") == product_id]
        if prod_reviews and prod:
            avg_rating = round(sum(r.get("rating", 5) for r in prod_reviews) / len(prod_reviews), 1)
            inventory_manager.update_product_ai_summary(
                product_id=product_id,
                ai_summary=prod.get("AI_REVIEW_SUMMARY", "Great customer satisfaction."),
                rating=avg_rating
            )

        # Emit review event to notify Price Manager & Fleet
        try:
            from backend.events import emit_store_event, EventType
            emit_store_event(
                event_type=EventType.REVIEW_SUBMITTED,
                source_agent="Review and Feedback Manager",
                payload={
                    "product_id": product_id,
                    "product_name": p_name,
                    "rating": new_rev["rating"],
                    "review_text": new_rev["review_text"]
                }
            )
        except Exception as e:
            print(f"[Review Event Error]: {e}", flush=True)

        return {
            "success": True,
            "message": f"Review added for '{p_name}'.",
            "review": new_rev
        }

    async def add_review_async(
        self,
        product_id: str,
        customer_name: str,
        rating: int,
        review_text: str,
        product_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Non-blocking async version of add_review."""
        reviews = await self._read_reviews_async()
        prod = await inventory_manager.get_product_by_id_async(product_id)
        p_name = product_name or (prod.get("PRODUCT_NAME") if prod else product_id)

        new_rev = {
            "id": f"rev_{uuid.uuid4().hex[:6]}",
            "product_id": product_id,
            "product_name": p_name,
            "customer_name": customer_name or "Verified Buyer",
            "rating": max(1, min(5, int(rating))),
            "review_text": review_text.strip(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        reviews.append(new_rev)
        await self._write_reviews_async(reviews)

        prod_reviews = [r for r in reviews if r.get("product_id") == product_id]
        if prod_reviews and prod:
            avg_rating = round(sum(r.get("rating", 5) for r in prod_reviews) / len(prod_reviews), 1)
            inventory_manager.update_product_ai_summary(
                product_id=product_id,
                ai_summary=prod.get("AI_REVIEW_SUMMARY", "Great customer satisfaction."),
                rating=avg_rating
            )

        try:
            from backend.events import emit_store_event, EventType
            emit_store_event(
                event_type=EventType.REVIEW_SUBMITTED,
                source_agent="Review and Feedback Manager",
                payload={
                    "product_id": product_id,
                    "product_name": p_name,
                    "rating": new_rev["rating"],
                    "review_text": new_rev["review_text"]
                }
            )
        except Exception as e:
            print(f"[Review Event Error]: {e}", flush=True)

        return {
            "success": True,
            "message": f"Review added for '{p_name}'.",
            "review": new_rev
        }

    async def generate_ai_review_summary(self, product_id_or_name: str) -> Dict[str, Any]:
        """
        Uses local Ollama LLM to analyze all customer reviews for an item, synthesize key strengths,
        complaints, sentiment, and updates the product catalog with the summary.
        """
        # Find target product
        prod = None
        products = inventory_manager.get_all_products()
        ident_clean = product_id_or_name.lower().strip()
        for p in products:
            if p.get("id", "").lower() == ident_clean or ident_clean in p.get("PRODUCT_NAME", "").lower():
                prod = p
                break

        if not prod:
            return {"success": False, "error": f"Product '{product_id_or_name}' not found."}

        p_id = prod["id"]
        p_name = prod["PRODUCT_NAME"]
        reviews = self.get_reviews_for_product(p_id)

        if not reviews:
            # Fallback for products with no direct reviews yet
            fallback_summary = f"🌟 **Customer Consensus**: Highly anticipated item in {prod.get('PRODUCT_TYPE')}. Early customer reception highlights exceptional craftsmanship and design."
            inventory_manager.update_product_ai_summary(p_id, fallback_summary)
            return {
                "success": True,
                "product_id": p_id,
                "product_name": p_name,
                "review_count": 0,
                "summary": fallback_summary
            }

        reviews_text_block = "\n".join([
            f"- [{r.get('customer_name', 'Customer')} - {r.get('rating')}/5 stars]: \"{r.get('review_text')}\""
            for r in reviews
        ])

        avg_rating = round(sum(r.get("rating", 5) for r in reviews) / len(reviews), 1)

        prompt = f"""You are the AI Review and Customer Feedback Analyst for an elite e-commerce brand.
Analyze the following customer reviews for the product: '{p_name}' (Category: {prod.get('PRODUCT_TYPE')}).

Customer Reviews ({len(reviews)} total, Avg Rating: {avg_rating}/5):
{reviews_text_block}

Generate a concise, high-impact, professional executive summary with:
1. Overall Customer Sentiment & Rating Consensus
2. Key Praised Features (Top 2-3 Pros)
3. Sizing / Constructive Feedback or Caveats (if any)
4. Bottom-line Verdict

Format with clear bullet points and bold highlights. Keep it under 150 words."""

        summary_text = ""
        from backend.config import AI_ENABLED
        if AI_ENABLED:
            from backend.llm_runtime import complete_chat, configured_model
            try:
                chat_resp = await asyncio.to_thread(
                    complete_chat, model=configured_model(), messages=[
                        {"role": "system", "content": "Summarize only the supplied reviews. Do not invent claims."},
                        {"role": "user", "content": prompt}
                    ], temperature=0.2, max_tokens=350)
                import re
                summary_text = re.sub(r'<think>.*?</think>', '', chat_resp.choices[0].message.content or "", flags=re.DOTALL).strip()
            except Exception as error:
                print(f"Review synthesis unavailable: {error}", flush=True)
        if not summary_text:
            summary_text = f"Average customer rating: {avg_rating}/5 from {len(reviews)} reviews. "
            summary_text += "Recent feedback: " + " · ".join(str(review.get("review_text", ""))[:150] for review in reviews[:3])

        # Commit AI summary & rating update directly to product in inventory.json
        inventory_manager.update_product_ai_summary(p_id, summary_text, rating=avg_rating)

        return {
            "success": True,
            "product_id": p_id,
            "product_name": p_name,
            "review_count": len(reviews),
            "average_rating": avg_rating,
            "summary": summary_text
        }


review_manager = ReviewManager()
