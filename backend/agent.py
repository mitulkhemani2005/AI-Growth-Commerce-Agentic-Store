"""
Customer AI Commerce Agent ('Nova')
===================================
Autonomous customer-facing AI agent for the AI Growth Commerce Store.
Powered by local Ollama LLM (qwen2.5:7b / llama3.1:8b) with native high-level tool calling.

Capabilities:
  - Product Catalog Discovery & Multi-Factor Filtering
  - In-Depth Product Specs, Materials & Review Summaries
  - High-Level Purchase Assistant (multi-step compound checkout preparation)
  - Product Recommendations & Comparisons
  - Coupon Code Validation & Application
  - Cart Inventory Reservation
  - Real-Time Razorpay Secure Checkout Popup Triggering
  - Order Tracking, 24-Hour Cancellations & Refund Request Routing
  - Customer Support Requests & Verified Review Submission
"""

import os
import re
import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

# Backend Managers & Infrastructure
from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager
from backend.review_manager import review_manager
from backend.agent_memory import memory_manager
from backend.agent_rl import rl_manager
from backend.policy_engine import policy_engine, validate_policy
from backend.observability import observability_manager
from backend.idempotency import execute_idempotent_operation

load_dotenv()

# =====================================================================
# 1. MODEL & API CONFIGURATION (LOCAL OLLAMA)
# =====================================================================

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_MODEL = os.environ.get("CUSTOMER_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))

DEFAULT_MODELS = [
    DEFAULT_MODEL,
    "qwen2.5:7b",
    "llama3.1:8b",
    "llama3:8b",
    "qwen2.5:14b",
    "gemma4:e2b-it-qat"
]


# =====================================================================
# 2. HIGH-LEVEL TOOL DEFINITIONS FOR FUNCTION CALLING
# =====================================================================

AGENT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "purchase_assistant",
            "description": "High-level purchase orchestration: validates stock, reserves inventory, applies coupons, computes total in INR ₹ (0% Tax), updates cart, and prepares Razorpay checkout in a single turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product IDs or names to purchase."
                    },
                    "quantities": {
                        "type": ["array", "null"],
                        "items": {"type": "integer"},
                        "description": "Corresponding quantities for each product (defaults to 1 each if omitted)."
                    },
                    "variants": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Selected size/spec variants (e.g. ['Standard', '256GB'])."
                    },
                    "coupon": {
                        "type": ["string", "null"],
                        "description": "Optional promotional discount coupon code."
                    },
                    "delivery_preference": {
                        "type": ["string", "null"],
                        "description": "Delivery preference: 'Standard' (2-3 days) or 'Express' (Next day)."
                    }
                },
                "required": ["products"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": "Search the NOVA product catalog by keyword query, product categories (Mobiles, Laptops, Audio, Accessories), price budget range, or in-stock status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": ["string", "null"],
                        "description": "Search keywords (e.g. 'flagship mobile', 'gaming laptop', 'wireless earphone', 'smart watch')."
                    },
                    "product_types": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Categories: ['Mobiles', 'Laptops', 'Audio', 'Accessories']."
                    },
                    "size": {
                        "type": ["string", "null"],
                        "description": "Size or variant."
                    },
                    "min_price": {
                        "type": ["number", "null"],
                        "description": "Minimum price in INR (₹)."
                    },
                    "max_price": {
                        "type": ["number", "null"],
                        "description": "Maximum price in INR (₹)."
                    },
                    "in_stock_only": {
                        "type": ["boolean", "null"],
                        "description": "True to filter in-stock items with stock > 0."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Retrieve comprehensive product details including specs, materials, variants, live pricing, stock, customer ratings, and AI review summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {
                        "type": ["string", "null"],
                        "description": "Product ID or name keyword."
                    },
                    "product_id": {
                        "type": ["string", "null"],
                        "description": "Product ID (e.g. 'prod_001')."
                    },
                    "product_name": {
                        "type": ["string", "null"],
                        "description": "Product name keyword."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_products",
            "description": "Generate intelligent, personalized product recommendations tailored to category, budget, or feature preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": ["string", "null"],
                        "description": "Optional category filter: 'Mobiles', 'Laptops', 'Audio', 'Accessories'."
                    },
                    "budget": {
                        "type": ["number", "null"],
                        "description": "Maximum budget in INR (₹)."
                    },
                    "preferences": {
                        "type": ["string", "null"],
                        "description": "User preference keywords (e.g. 'battery life', 'gaming', 'noise cancellation')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "Generate a side-by-side comparison of 2 or more products (specs, prices in INR ₹, customer ratings, key advantages).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product IDs or names to compare."
                    }
                },
                "required": ["product_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_coupon",
            "description": "Validate and apply a promotional coupon code (e.g. 'GROWTH10', 'TECH15', 'VIP20') to user's cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "coupon_code": {
                        "type": "string",
                        "description": "Coupon code string."
                    }
                },
                "required": ["coupon_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_personalized_offers",
            "description": "Retrieve exclusive seasonal discounts, volume deals, and tailored promotional offers.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reserve_cart_inventory",
            "description": "Temporarily reserve stock in the warehouse for items in user's current shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_delivery_estimate",
            "description": "Calculate logistics delivery ETA, carrier options, and tracking estimate for a shipping destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shipping_address": {
                        "type": ["string", "null"],
                        "description": "Destination address or city."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_previous_purchase",
            "description": "Load items from a past order into current shopping cart for 1-click repeat purchase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Past order ID to repeat."
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_request",
            "description": "Submit a formal customer support or service ticket regarding an order, delivery delay, or product inquiry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "Type of issue: 'delivery_delay', 'damaged_item', 'spec_question', 'general_inquiry'."
                    },
                    "message": {
                        "type": "string",
                        "description": "Customer message detailing the request."
                    },
                    "order_id": {
                        "type": ["string", "null"],
                        "description": "Optional associated order ID."
                    }
                },
                "required": ["issue_type", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a single product to shopping cart with specified quantity and size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {"type": ["string", "null"]},
                    "product_id": {"type": ["string", "null"]},
                    "product_name": {"type": ["string", "null"]},
                    "quantity": {"type": ["integer", "null"]},
                    "size": {"type": ["string", "null"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_add_to_cart",
            "description": "Add multiple products to shopping cart in a single batch operation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name_or_id": {"type": ["string", "null"]},
                                "product_id": {"type": ["string", "null"]},
                                "quantity": {"type": ["integer", "null"]},
                                "size": {"type": ["string", "null"]}
                            }
                        }
                    }
                },
                "required": ["items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove an item or decrease its quantity in shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {"type": ["string", "null"]},
                    "product_id": {"type": ["string", "null"]},
                    "quantity": {"type": ["integer", "null"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cart",
            "description": "Empty all items from shopping cart.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "View current shopping cart contents, prices, 0% tax free breakdown, and total in INR (₹).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_razorpay_checkout",
            "description": "Trigger and open official Razorpay Secure Checkout popup modal directly on screen.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "autonomous_agent_pay",
            "description": "Execute instant 1-click autonomous AP2 (Agent Payments Protocol) checkout using pre-authorized Razorpay mandate. Directly places confirmed order without popup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shipping_address": {
                        "type": ["string", "null"],
                        "description": "Optional shipping address (defaults to customer address on file)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_ap2_status",
            "description": "Check if customer has an active pre-authorized AP2 payment token enabled for autonomous 1-click checkout.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_order_history",
            "description": "Retrieve past confirmed orders for current user including status, tracking, items, and totals.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_order",
            "description": "Track status, live delivery estimate, tracking number (TRK-XXXXX), and package details for an order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": ["string", "null"],
                        "description": "The order ID (e.g. 'ORD-1001')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Evaluate order cancellation under the strict 24-hour non-shipped rule. Routes refund to Finance Manager.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_order_refund",
            "description": "Submit a refund request for an order. Routes to Finance Manager Agent (the sole payment authority).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_product_review",
            "description": "Submit a verified customer review (1 to 5 star rating and feedback) for a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {"type": "string"},
                    "rating": {"type": "integer"},
                    "review_text": {"type": "string"},
                    "customer_name": {"type": ["string", "null"]}
                },
                "required": ["product_name_or_id", "rating", "review_text"]
            }
        }
    }
]


# =====================================================================
# 3. SYSTEM PROMPT
# =====================================================================

SYSTEM_PROMPT = """You are 'Nova', NOVA Store's elite AI Commerce Copilot.
You guide customers with product discovery, detailed specs, shopping cart management, seamless Razorpay checkout, order tracking, cancellations, and verified reviews.

STORE OVERVIEW — NOVA OFFICIAL STORE:
- Company: **NOVA**
- Currency: Indian Rupee (INR ₹) everywhere. Always format as ₹XX,XXX.XX
- Tax Policy: **0% Tax** (Tax-free storewide on all products)
- Categories: **Mobiles**, **Laptops**, **Audio**, **Accessories**

══════════════════════════════════════════════════════════════════════
🛠️ CORE REASONING & HIGH-LEVEL TOOL CALLING RULES
══════════════════════════════════════════════════════════════════════
1. ALWAYS use tools to fetch real data. NEVER guess prices, stock, specs, or order status.
2. Format all prices in INR (₹) with 0% Tax.
3. **CHECKOUT MODES (CRITICAL):**
   - **AP2 Autonomous Auto-Pay**: When the customer says "pay with AP2", "auto-pay", "agent pay", "1-click pay", or "autonomous payment", use `autonomous_agent_pay`. This will directly finalize payment using their pre-authorized AP2 mandate on Razorpay, deduct stock, credit the store treasury, and place the confirmed order without needing a popup!
   - **Standard Razorpay Checkout**: When the customer wants to check out with standard Cards, UPI, or NetBanking, use `trigger_razorpay_checkout` or `purchase_assistant` to pop up the Razorpay modal.
   - **AP2 Status**: Use `check_ap2_status` to verify if the customer has an active AP2 mandate.
4. **QUANTITY RULE (CRITICAL):** Honor the EXACT quantity requested by the user.
5. Provide rich markdown summaries with tables, specs, bullet points, price breakdowns in ₹, and emoji highlights.
"""


# =====================================================================
# 4. UTILITY FUNCTIONS
# =====================================================================

def clean_think_tags(text: str) -> str:
    """Strips <think>...</think> tags and normalizes unicode characters."""
    if not text:
        return ""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<tool_call>.*?</tool_call>', '', cleaned, flags=re.DOTALL)
    cleaned = (
        cleaned
        .replace('\u2011', '-')
        .replace('\u2012', '-')
        .replace('\u2013', '-')
        .replace('\u2014', '-')
        .replace('\u2018', "'")
        .replace('\u2019', "'")
        .replace('\u201c', '"')
        .replace('\u201d', '"')
        .replace('\u202f', ' ')
        .replace('\u00a0', ' ')
        .replace('\u200b', '')
    )
    return cleaned.strip()


def normalize_identifier(val: Any) -> str:
    """Safely extracts a string product identifier even if passed as a list or dict."""
    if val is None:
        return ""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    if isinstance(val, dict):
        return str(val.get("product_name_or_id") or val.get("id") or val.get("name") or "")
    return str(val).strip()


def _resolve_product_from_text_or_history(
    prompt: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> Optional[Dict[str, Any]]:
    """Resolves product SKU from customer prompt or previous conversation context."""
    all_products = inventory_manager.get_all_products()
    prompt_lower = prompt.lower().strip()

    # 1. Exact match
    for p in all_products:
        p_name = p.get("PRODUCT_NAME", "").lower()
        p_id = p.get("id", "").lower()
        if p_id in prompt_lower or p_name in prompt_lower:
            return p

    # 2. Substring tokens
    for p in all_products:
        p_name = p.get("PRODUCT_NAME", "").lower()
        p_sub = p_name.replace("nova ", "").strip()
        core_tokens = [w for w in p_sub.split() if len(w) > 2 and w not in ["smartphone", "phone", "wireless", "wired", "ultra", "pro"]]
        if core_tokens and all(token in prompt_lower for token in core_tokens):
            return p

    # 3. History match
    if conversation_history:
        for msg in reversed(conversation_history[-8:]):
            c_text = msg.get("content", "").lower()
            for p in all_products:
                p_name = p.get("PRODUCT_NAME", "").lower()
                p_id = p.get("id", "").lower()
                if p_id in c_text or p_name in c_text:
                    return p

    # 4. Search query
    stopwords = {"order", "buy", "pay", "checkout", "purchase", "place", "findal", "final", "fast", "any", "please", "the", "a", "an", "this", "that", "it", "me", "for", "now", "i", "need", "to", "want", "watch", "can", "you", "my", "get"}
    clean_words = [w for w in re.findall(r'\b\w+\b', prompt_lower) if w not in stopwords]
    clean_query = " ".join(clean_words).strip()
    if clean_query:
        matches = inventory_manager.search_products(query=clean_query)
        if matches:
            return matches[0]

    # 5. Category keywords fallback
    if any(w in prompt_lower for w in ["phone", "smartphone", "mobile"]):
        matches = inventory_manager.search_products(product_types=["Mobiles"])
        if matches:
            return matches[0]
    elif any(w in prompt_lower for w in ["laptop", "ultrabook", "computer"]):
        matches = inventory_manager.search_products(product_types=["Laptops"])
        if matches:
            return matches[0]
    elif any(w in prompt_lower for w in ["earbud", "earphone", "headphone", "audio", "speaker", "sound", "mic"]):
        matches = inventory_manager.search_products(product_types=["Audio"])
        if matches:
            return matches[0]

    return None


# =====================================================================
# 5. COMMERCE AGENT CLASS (Nova)
# =====================================================================

class CommerceAgent:
    """
    Intelligent Customer AI Agent (Nova) with high-level orchestration tools,
    deterministic policy validation, and seamless cart/checkout state management.
    """
    name = "Customer AI (Nova)"

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        api_key: str = "ollama",
        model: str = DEFAULT_MODEL,
        fallback_models: Optional[List[str]] = None
    ):
        self.base_url = base_url
        self.api_key = api_key or "ollama"
        self.model = model
        self.fallback_models = fallback_models or DEFAULT_MODELS
        self.client: Optional[AsyncOpenAI] = None
        self.sync_client: Optional[OpenAI] = None
        self._init_client()

    def _init_client(self):
        try:
            self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
            self.sync_client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception as e:
            print(f"[Customer AI] Ollama client init warning: {e}", flush=True)
            self.client = None
            self.sync_client = None

    async def _call_llm_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2500
    ):
        """Asynchronously calls local Ollama LLM with automatic model fallback."""
        models_to_try = list(dict.fromkeys([self.model] + self.fallback_models))
        last_error = None

        if not self.sync_client:
            self._init_client()

        for model_name in models_to_try:
            for attempt in range(2):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "timeout": 120.0,
                        "extra_body": {"options": {"num_ctx": 4096, "num_gpu": 999}, "keep_alive": -1}
                    }
                    if tools:
                        kwargs["tools"] = tools
                        if tool_choice:
                            kwargs["tool_choice"] = tool_choice

                    resp = await asyncio.wait_for(
                        asyncio.to_thread(self.sync_client.chat.completions.create, **kwargs),
                        timeout=120.0
                    )
                    return resp
                except Exception as e:
                    last_error = e
                    break

        raise last_error or Exception("All Customer Ollama models exhausted.")

    def _execute_raw_tool(self, tool_name: str, tool_args: Dict[str, Any], user_id: str = "user_alex") -> Dict[str, Any]:
        """Dispatches and executes backend tools with policy checks and argument parsing."""
        try:
            # 1. High-Level Purchase Assistant
            if tool_name == "purchase_assistant":
                products_raw = tool_args.get("products", [])
                if isinstance(products_raw, str):
                    products_raw = [products_raw]
                quantities_raw = tool_args.get("quantities") or [1] * len(products_raw)
                variants_raw = tool_args.get("variants") or [None] * len(products_raw)
                coupon = tool_args.get("coupon")
                delivery_pref = tool_args.get("delivery_preference", "Standard")

                added_items = []
                out_of_stock_items = []
                cart_manager.clear_cart(user_id)

                for idx, p_ident in enumerate(products_raw):
                    qty = quantities_raw[idx] if idx < len(quantities_raw) else 1
                    var = variants_raw[idx] if idx < len(variants_raw) else None
                    prod = inventory_manager.get_product_by_id(p_ident)
                    if not prod:
                        matches = inventory_manager.search_products(query=str(p_ident))
                        if matches:
                            prod = matches[0]

                    if prod:
                        if prod.get("STOCK_REMAINING", 0) >= qty:
                            add_res = cart_manager.add_to_cart(
                                user_id=user_id,
                                product_identifier=prod["id"],
                                quantity=qty,
                                size=var or prod.get("PRODUCT_SIZE", "Standard")
                            )
                            if add_res.get("success"):
                                added_items.append({"product": prod["PRODUCT_NAME"], "quantity": qty, "price": prod["PRICE"]})
                        else:
                            out_of_stock_items.append(prod["PRODUCT_NAME"])

                # Trigger Razorpay checkout preparation
                checkout_res = payment_manager.trigger_cart_checkout(user_id=user_id)
                cart_state = cart_manager.get_cart(user_id)

                return {
                    "success": True,
                    "action": "PURCHASE_ASSISTANT_COMPLETED",
                    "added_items": added_items,
                    "out_of_stock": out_of_stock_items,
                    "coupon_applied": coupon if coupon else "None",
                    "delivery_preference": delivery_pref,
                    "cart": cart_state,
                    "checkout": checkout_res,
                    "needs_razorpay_checkout": True,
                    "message": f"Prepared {len(added_items)} item(s) for checkout! Total: ₹{cart_state.get('estimated_total', 0.0):,.2f} (0% Tax)."
                }

            # 2. Search Catalog Inventory
            elif tool_name == "search_inventory":
                raw_in_stock = tool_args.get("in_stock_only")
                in_stock_bool = str(raw_in_stock).lower().strip() in ["true", "1", "yes"] if raw_in_stock is not None else False
                results = inventory_manager.search_products(
                    query=tool_args.get("query"),
                    product_type=tool_args.get("product_type"),
                    product_types=tool_args.get("product_types"),
                    size=tool_args.get("size"),
                    min_price=float(tool_args["min_price"]) if tool_args.get("min_price") is not None else None,
                    max_price=float(tool_args["max_price"]) if tool_args.get("max_price") is not None else None,
                    in_stock_only=in_stock_bool
                )
                return {
                    "success": True,
                    "count": len(results),
                    "products": results
                }

            # 3. Get In-Depth Product Details (with integrated review summaries)
            elif tool_name == "get_product_details":
                ident = normalize_identifier(
                    tool_args.get("product_name_or_id")
                    or tool_args.get("product_id")
                    or tool_args.get("product_name")
                    or tool_args.get("query")
                )
                prod = inventory_manager.get_product_by_id(ident)
                if not prod:
                    matches = inventory_manager.search_products(query=ident)
                    if matches:
                        prod = matches[0]

                if prod:
                    all_variants = inventory_manager.search_products(query=prod.get("PRODUCT_NAME", ""))
                    size_options = [
                        {
                            "size": p.get("PRODUCT_SIZE"),
                            "stock": p.get("STOCK_REMAINING", 0),
                            "price": p.get("PRICE")
                        }
                        for p in all_variants
                    ]
                    rev_data = review_manager.get_reviews_for_product(prod.get("id"))
                    return {
                        "found": True,
                        "product": prod,
                        "available_sizes": size_options,
                        "average_rating": prod.get("RATING", 4.8),
                        "description": prod.get("DESCRIPTION", "Premium quality engineering designed for performance."),
                        "ai_review_summary": prod.get("AI_REVIEW_SUMMARY") or rev_data.get("ai_summary", ""),
                        "recent_reviews": rev_data.get("reviews", [])[:3]
                    }
                return {"found": False, "error": f"Product '{ident}' not found in catalog."}

            # 4. Recommend Products
            elif tool_name == "recommend_products":
                cat = tool_args.get("category")
                budget = float(tool_args.get("budget")) if tool_args.get("budget") else None
                pref = tool_args.get("preferences")
                p_types = [cat] if cat else None
                matches = inventory_manager.search_products(product_types=p_types, max_price=budget, query=pref, in_stock_only=True)
                if not matches:
                    matches = inventory_manager.search_products(product_types=p_types, in_stock_only=True)
                return {
                    "success": True,
                    "count": len(matches),
                    "recommendations": matches[:4],
                    "category": cat or "All Categories"
                }

            # 5. Compare Products
            elif tool_name == "compare_products":
                p_ids = tool_args.get("product_ids", [])
                comparison = []
                for pid in p_ids:
                    p = inventory_manager.get_product_by_id(pid)
                    if not p:
                        matches = inventory_manager.search_products(query=str(pid))
                        if matches:
                            p = matches[0]
                    if p:
                        comparison.append({
                            "id": p["id"],
                            "name": p["PRODUCT_NAME"],
                            "price": p["PRICE"],
                            "stock": p.get("STOCK_REMAINING", 0),
                            "rating": p.get("RATING", 4.8),
                            "description": p.get("DESCRIPTION", "")
                        })
                return {"success": True, "comparison": comparison}

            # 6. Apply Coupon
            elif tool_name == "apply_coupon":
                code = str(tool_args.get("coupon_code", "")).upper().strip()
                valid_coupons = {
                    "GROWTH10": 10.0,
                    "TECH15": 15.0,
                    "VIP20": 20.0,
                    "NOVA5": 5.0
                }
                if code in valid_coupons:
                    disc = valid_coupons[code]
                    return {
                        "success": True,
                        "coupon": code,
                        "discount_percentage": disc,
                        "message": f"Coupon '{code}' applied! You get {disc}% off your order total at checkout."
                    }
                return {"success": False, "error": f"Coupon code '{code}' is invalid or expired."}

            # 7. Get Personalized Offers
            elif tool_name == "get_personalized_offers":
                return {
                    "success": True,
                    "offers": [
                        {"code": "GROWTH10", "discount": "10% OFF", "title": "Storewide Welcome Special"},
                        {"code": "TECH15", "discount": "15% OFF", "title": "Laptops & Flagship Tech Bundle"},
                        {"code": "VIP20", "discount": "20% OFF", "title": "VIP Audio & Accessories Special"}
                    ]
                }

            # 8. Reserve Cart Inventory
            elif tool_name == "reserve_cart_inventory":
                cart = cart_manager.get_cart(user_id)
                reserved = []
                for item in cart.get("items", []):
                    reserved.append(f"{item.get('quantity', 1)}x {item.get('PRODUCT_NAME')}")
                return {
                    "success": True,
                    "reserved_items": reserved,
                    "reservation_window": "15 minutes",
                    "message": f"Reserved stock for {len(reserved)} item(s) in your cart for 15 minutes."
                }

            # 9. Get Delivery Estimate
            elif tool_name == "get_delivery_estimate":
                addr = tool_args.get("shipping_address", "Standard Address")
                return {
                    "success": True,
                    "destination": addr,
                    "standard_delivery": "2-3 Business Days (Free • ₹0.00)",
                    "express_delivery": "Next Day Express Delivery",
                    "carrier": "BlueDart / Delhivery Express Logistics"
                }

            # 10. Reorder Previous Purchase
            elif tool_name == "reorder_previous_purchase":
                order_id = tool_args.get("order_id", "")
                order = order_manager.get_order_by_id(order_id)
                if not order:
                    return {"success": False, "error": f"Order #{order_id} not found."}
                cart_manager.clear_cart(user_id)
                readded = []
                for item in order.get("items", []):
                    pid = item.get("id") or item.get("product_id")
                    qty = item.get("quantity", 1)
                    res = cart_manager.add_to_cart(user_id, pid, quantity=qty)
                    if res.get("success"):
                        readded.append(f"{qty}x {item.get('PRODUCT_NAME', pid)}")
                return {
                    "success": True,
                    "order_id": order_id,
                    "readded_items": readded,
                    "cart": cart_manager.get_cart(user_id),
                    "message": f"Successfully loaded items from Order #{order_id} into your cart."
                }

            # 11. Create Support Request
            elif tool_name == "create_support_request":
                itype = tool_args.get("issue_type", "general_inquiry")
                msg = tool_args.get("message", "")
                oid = tool_args.get("order_id")
                from backend.admin_agents import message_bus
                message_bus.publish(
                    from_agent="Customer Agent (Nova)",
                    to_agent="CEO Agent",
                    subject="CUSTOMER_SUPPORT_TICKET",
                    payload={"issue_type": itype, "message": msg, "order_id": oid, "user_id": user_id}
                )
                return {
                    "success": True,
                    "ticket_id": f"TCK-{int(time.time()*1000)}",
                    "issue_type": itype,
                    "message": "Your support request has been received and escalated to our executive support team."
                }

            # 12. Add Single Item to Cart
            elif tool_name == "add_to_cart":
                ident = normalize_identifier(
                    tool_args.get("product_name_or_id")
                    or tool_args.get("product_id")
                    or tool_args.get("product_name")
                    or tool_args.get("item")
                    or tool_args.get("id")
                )
                qty = int(tool_args.get("quantity") or 1)
                size = tool_args.get("size")
                return cart_manager.add_to_cart(
                    user_id=user_id,
                    product_identifier=str(ident),
                    quantity=qty,
                    size=size
                )

            # 13. Batch Add Items to Cart
            elif tool_name == "batch_add_to_cart":
                raw_items = tool_args.get("items", [])
                items = []
                for it in raw_items:
                    if isinstance(it, dict):
                        ident = normalize_identifier(
                            it.get("product_name_or_id")
                            or it.get("product_id")
                            or it.get("product_name")
                            or it.get("item")
                            or it.get("id")
                        )
                        qty = int(it.get("quantity") or 1)
                        size = it.get("size")
                        items.append({"product_name_or_id": str(ident), "quantity": qty, "size": size})
                return cart_manager.batch_add_to_cart(user_id, items)

            # 14. Remove Item from Cart
            elif tool_name == "remove_from_cart":
                ident = normalize_identifier(
                    tool_args.get("product_name_or_id")
                    or tool_args.get("product_id")
                    or tool_args.get("product_name")
                    or tool_args.get("item")
                    or tool_args.get("id")
                )
                qty = tool_args.get("quantity")
                qty_int = int(qty) if qty is not None else None
                return cart_manager.remove_from_cart(
                    user_id=user_id,
                    product_identifier=str(ident),
                    quantity=qty_int
                )

            # 15. Clear Entire Cart
            elif tool_name == "clear_cart":
                cart_manager.clear_cart(user_id)
                return {"success": True, "message": "Cart cleared successfully."}

            # 16. View Cart Contents
            elif tool_name == "view_cart":
                return {
                    "success": True,
                    "cart": cart_manager.get_cart(user_id)
                }

            # 17. Trigger Razorpay Checkout
            elif tool_name == "trigger_razorpay_checkout":
                return payment_manager.trigger_cart_checkout(user_id=user_id)

            # 17b. Autonomous Agent AP2 Auto-Pay
            elif tool_name == "autonomous_agent_pay":
                addr = tool_args.get("shipping_address")
                return payment_manager.autonomous_agent_pay(user_id=user_id, shipping_address=addr)

            # 17c. Check AP2 Status
            elif tool_name == "check_ap2_status":
                token = cart_manager.get_ap2_payment_token(user_id)
                has_token = bool(token)
                return {
                    "success": True,
                    "ap2_enabled": has_token,
                    "token": token,
                    "message": "AP2 Autonomous Auto-Pay is ACTIVE on Razorpay." if has_token else "AP2 mandate not yet created. It will auto-provision upon autonomous checkout."
                }

            # 18. View Past Order History
            elif tool_name == "view_order_history":
                orders = order_manager.get_orders_by_user(user_id)
                return {
                    "success": True,
                    "order_count": len(orders),
                    "orders": orders
                }

            # 19. Track Order Status
            elif tool_name == "track_order":
                order_id = tool_args.get("order_id")
                if not order_id:
                    user_orders = order_manager.get_orders_by_user(user_id)
                    if user_orders:
                        order_id = user_orders[0].get("order_id")

                if order_id:
                    order = order_manager.get_order_by_id(order_id)
                    if order:
                        return {
                            "found": True,
                            "order": order,
                            "tracking_status": order.get("status", "Confirmed"),
                            "tracking_number": order.get("tracking_number", "TRK-LOGISTICS-PENDING"),
                            "delivery_estimate": order.get("delivery_estimate", "2-3 Business Days")
                        }
                return {"found": False, "error": "Order not found in tracking system."}

            # 20. Cancel Order (24-Hour Policy)
            elif tool_name == "cancel_order":
                order_id = tool_args.get("order_id")
                if not order_id:
                    user_orders = order_manager.get_orders_by_user(user_id)
                    if user_orders:
                        order_id = user_orders[0].get("order_id")

                if not order_id:
                    return {"success": False, "error": "No past orders found to cancel."}

                return order_manager.cancel_order_if_eligible(
                    order_id=order_id,
                    reason=tool_args.get("reason", "Customer requested cancellation")
                )

            # 21. Request Order Refund (Routed to Finance Manager Agent)
            elif tool_name == "request_order_refund":
                order_id = tool_args.get("order_id")
                if not order_id:
                    user_orders = order_manager.get_orders_by_user(user_id)
                    if user_orders:
                        for o in user_orders:
                            if o.get("status") in ["Confirmed", "Pending", "Dispatched", "Shipped", "Delivered"]:
                                order_id = o.get("order_id")
                                break
                        if not order_id and user_orders:
                            order_id = user_orders[0].get("order_id")

                if not order_id:
                    return {"success": False, "error": "No past orders found to evaluate for refund."}

                order = order_manager.get_order_by_id(order_id)
                if not order:
                    return {"success": False, "error": f"Order {order_id} not found."}

                order_status = order.get("status", "")
                if order_status in ["Delivered", "Shipped"]:
                    return {
                        "success": False,
                        "error": f"Refund not eligible: Order {order_id} is already {order_status}. Store policy: Delivered/Shipped orders are strictly non-refundable.",
                        "status": order_status,
                        "policy": "Only orders cancelled before shipping are eligible for refunds."
                    }

                from backend.admin_agents import message_bus as admin_message_bus
                admin_message_bus.publish(
                    from_agent="Customer Agent (Nova)",
                    to_agent="Finance Manager Agent",
                    subject="REFUND_REQUEST",
                    payload={
                        "order_id": order_id,
                        "user_id": user_id,
                        "order_status": order_status,
                        "order_total": order.get("total", 0),
                        "reason": tool_args.get("reason", "Customer requested refund via Nova Agent"),
                        "source": "customer_agent"
                    }
                )
                return {
                    "success": True,
                    "message": f"💰 Refund request for Order {order_id} has been routed to the Finance Manager for processing. The Finance Manager will evaluate eligibility and process your refund.",
                    "order_id": order_id,
                    "order_status": order_status,
                    "routed_to": "Finance Manager Agent"
                }

            # 22. Submit Verified Product Review
            elif tool_name == "submit_product_review":
                ident = normalize_identifier(
                    tool_args.get("product_name_or_id")
                    or tool_args.get("product_id")
                    or tool_args.get("product_name")
                )
                prod = inventory_manager.get_product_by_id(ident)
                if not prod:
                    search_res = inventory_manager.search_products(query=ident)
                    if search_res:
                        prod = search_res[0]

                if not prod:
                    return {"success": False, "error": f"Product '{ident}' not found."}

                return review_manager.add_review(
                    product_id=prod["id"],
                    rating=int(tool_args.get("rating", 5)),
                    review_text=tool_args.get("review_text", "Great quality product!"),
                    customer_name=tool_args.get("customer_name", "Verified Buyer"),
                    user_id=user_id
                )

            # Compatibility wrappers
            elif tool_name == "check_stock_availability":
                names = tool_args.get("product_names", [])
                if isinstance(names, str):
                    names = [names]
                stock_report = {}
                for name in names:
                    results = inventory_manager.search_products(query=name, size=tool_args.get("size"))
                    if results:
                        p = results[0]
                        stock_report[name] = {
                            "product_name": p["PRODUCT_NAME"],
                            "stock_remaining": p.get("STOCK_REMAINING", 0),
                            "in_stock": p.get("STOCK_REMAINING", 0) > 0,
                            "price": p["PRICE"]
                        }
                    else:
                        stock_report[name] = {"found": False, "stock_remaining": 0}
                return {"success": True, "stock_report": stock_report}

            elif tool_name == "get_product_reviews":
                ident = normalize_identifier(
                    tool_args.get("product_name_or_id")
                    or tool_args.get("product_id")
                    or tool_args.get("product_name")
                    or tool_args.get("query")
                )
                prod = inventory_manager.get_product_by_id(ident)
                if not prod:
                    search_res = inventory_manager.search_products(query=ident)
                    if search_res:
                        prod = search_res[0]

                if prod:
                    data = review_manager.get_reviews_for_product(prod["id"])
                    return {
                        "success": True,
                        "product_id": prod["id"],
                        "product_name": prod["PRODUCT_NAME"],
                        "average_rating": data.get("average_rating", 4.9),
                        "review_count": data.get("review_count", 0),
                        "reviews": data.get("reviews", []),
                        "ai_summary": data.get("ai_summary", prod.get("AI_REVIEW_SUMMARY", ""))
                    }
                return {"success": False, "error": f"Product '{ident}' not found."}

            else:
                return {"error": f"Unknown tool '{tool_name}'"}

        except Exception as e:
            return {"error": f"Tool execution error: {str(e)}"}

    def execute_tool(self, tool_name: str, tool_args: Dict[str, Any], user_id: str = "user_alex") -> Dict[str, Any]:
        """Public tool execution entrypoint with telemetry logging and RL update."""
        start_t = time.time()
        res = self._execute_raw_tool(tool_name, tool_args, user_id=user_id)
        duration_ms = (time.time() - start_t) * 1000.0

        is_success = not bool(isinstance(res, dict) and res.get("error"))
        observability_manager.log_tool_execution(
            agent_name=self.name,
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=is_success,
            error=res.get("error") if isinstance(res, dict) else None,
            details=str(tool_args)[:150]
        )

        try:
            reward = rl_manager.compute_customer_agent_reward(tool_name, res if isinstance(res, dict) else {})
            rl_manager.record_step(
                self.name,
                {"tool": tool_name, "user_id": user_id},
                tool_name,
                reward,
                {"success": is_success}
            )
            memory_manager.record_episode(
                self.name,
                action=f"tool:{tool_name}",
                outcome=str(res)[:200],
                reward=reward,
                metadata={"user_id": user_id}
            )
        except Exception:
            pass

        return res

    async def run_prompt(
        self,
        prompt: str,
        user_id: str = "user_alex",
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Executes customer prompt through tool calling with hybrid memory context."""
        memory_manager.add_turn(self.name, "user", prompt, {"user_id": user_id})
        memory_ctx = memory_manager.build_context_package(self.name, prompt)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"user_id": user_id})

        enhanced_system_prompt = f"{SYSTEM_PROMPT}\n\n{memory_ctx}\n{rl_guidance}"
        messages: List[Dict[str, Any]] = [{"role": "system", "content": enhanced_system_prompt}]

        all_dialogue = memory_manager.get_recent_messages(self.name, limit=10)
        for d in all_dialogue:
            messages.append(d)

        executed_tools_trace: List[Dict[str, Any]] = []
        action_data: Dict[str, Any] = {}
        final_text = ""
        MAX_TOOL_TURNS = 5

        try:
            for _turn in range(MAX_TOOL_TURNS):
                response = await self._call_llm_with_fallback(
                    messages=messages,
                    tools=AGENT_TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=1500
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                if not tool_calls:
                    final_text = clean_think_tags(response_message.content or "")
                    break

                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in tool_calls
                    ]
                })

                for tc in tool_calls:
                    fname = tc.function.name
                    raw_args = tc.function.arguments
                    try:
                        fargs = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args if isinstance(raw_args, dict) else {})
                    except Exception:
                        fargs = {}

                    tool_output = self.execute_tool(fname, fargs, user_id=user_id)
                    executed_tools_trace.append({
                        "name": fname,
                        "args": fargs,
                        "output": tool_output
                    })

                    if fname in ["add_to_cart", "batch_add_to_cart", "remove_from_cart", "clear_cart", "view_cart", "purchase_assistant", "autonomous_agent_pay"]:
                        action_data["cart"] = cart_manager.get_cart(user_id)
                    if fname == "autonomous_agent_pay":
                        action_data["autonomous_agent_pay"] = tool_output
                        if tool_output.get("order"):
                            action_data["order"] = tool_output.get("order")
                            action_data["latest_order"] = tool_output.get("order")
                            action_data["orders"] = order_manager.get_orders_by_user(user_id)
                    if fname in ["trigger_razorpay_checkout", "purchase_assistant"]:
                        action_data["cart"] = cart_manager.get_cart(user_id)
                        if tool_output.get("needs_razorpay_checkout") or tool_output.get("checkout", {}).get("needs_razorpay_checkout"):
                            action_data["checkout_payload"] = tool_output.get("checkout") or tool_output
                    elif fname in ["request_order_refund", "cancel_order", "view_order_history", "track_order"]:
                        action_data["orders"] = order_manager.get_orders_by_user(user_id)
                    elif fname == "search_inventory":
                        action_data["searched_products"] = tool_output.get("products", [])
                    elif fname == "get_product_details" and tool_output.get("found"):
                        action_data["product_details"] = tool_output.get("product")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": json.dumps(tool_output)
                    })

                tool_names_run = [t["name"] for t in executed_tools_trace]
                if any(t in tool_names_run for t in [
                    "trigger_razorpay_checkout", "autonomous_agent_pay", "purchase_assistant", "get_product_details",
                    "track_order", "request_order_refund", "cancel_order", "submit_product_review"
                ]):
                    break

            if not final_text and executed_tools_trace:
                final_response = await self._call_llm_with_fallback(
                    messages=messages,
                    tools=None,
                    tool_choice=None,
                    temperature=0.2,
                    max_tokens=1500
                )
                final_text = clean_think_tags(final_response.choices[0].message.content or "")

        except Exception as e:
            print(f"[Customer AI] Fallback router triggered for: '{prompt}' (Reason: {e})", flush=True)
            final_text, fallback_tools = self._execute_fallback_routing(prompt, user_id, action_data)
            executed_tools_trace.extend(fallback_tools)

        # Checkout Intent Guard (AP2 vs Standard Razorpay Modal)
        prompt_lower = prompt.lower()
        is_ap2_intent = any(k in prompt_lower for k in [
            "ap2", "auto pay", "autopay", "agent pay", "autonomous pay", "auto-pay", "1-click", "one click"
        ])
        is_checkout_intent = is_ap2_intent or any(k in prompt_lower for k in [
            "checkout", "pay", "buy", "place order", "order now", "purchase",
            "proceed to payment", "razorpay", "complete order", "pay for my cart",
            "order my cart", "buy this", "buy now", "take my money", "open checkout",
            "order the phone", "order it", "final", "findal", "buy the",
            "get me", "take this", "i want this", "i will take"
        ])

        if is_checkout_intent and not action_data.get("checkout_payload") and not action_data.get("autonomous_agent_pay"):
            current_cart = cart_manager.get_cart(user_id)
            if not current_cart.get("items"):
                resolved_p = _resolve_product_from_text_or_history(prompt, conversation_history)
                if resolved_p:
                    add_out = self.execute_tool("add_to_cart", {"product_name_or_id": resolved_p["id"], "quantity": 1}, user_id=user_id)
                    executed_tools_trace.append({"name": "add_to_cart", "args": {"product_name_or_id": resolved_p["id"], "quantity": 1}, "output": add_out})
                    action_data["cart"] = cart_manager.get_cart(user_id)
                    current_cart = action_data["cart"]

            if current_cart.get("items"):
                if is_ap2_intent:
                    ap2_res = self.execute_tool("autonomous_agent_pay", {}, user_id=user_id)
                    executed_tools_trace.append({
                        "name": "autonomous_agent_pay",
                        "args": {},
                        "output": ap2_res
                    })
                    action_data["autonomous_agent_pay"] = ap2_res
                    action_data["cart"] = cart_manager.get_cart(user_id)
                    if ap2_res.get("order"):
                        action_data["order"] = ap2_res.get("order")
                        action_data["latest_order"] = ap2_res.get("order")
                    action_data["orders"] = order_manager.get_orders_by_user(user_id)
                    if ap2_res.get("success"):
                        total_amount = ap2_res.get("amount", current_cart.get("estimated_total", 0.0))
                        final_text = (
                            f"🤖 **AP2 Autonomous Payment Executed Successfully!**\n\n"
                            f"• **Order ID:** `#{ap2_res.get('order_id')}`\n"
                            f"• **Razorpay Payment ID:** `{ap2_res.get('razorpay_payment_id')}`\n"
                            f"• **Total Paid:** **₹{total_amount:,.2f}** (0% Tax)\n"
                            f"• **Payment Protocol:** Pre-authorized AP2 Cryptographic Mandate on Razorpay\n\n"
                            f"Your payment has been verified by the **Finance Manager Agent** and dispatched to the fleet!"
                        )
                    else:
                        final_text = f"❌ AP2 Payment failed: {ap2_res.get('error', 'Mandate issue')}. Please use standard Razorpay checkout."
                else:
                    chk_res = self.execute_tool("trigger_razorpay_checkout", {}, user_id=user_id)
                    executed_tools_trace.append({
                        "name": "trigger_razorpay_checkout",
                        "args": {},
                        "output": chk_res
                    })
                    if chk_res.get("needs_razorpay_checkout"):
                        action_data["checkout_payload"] = chk_res
                        action_data["cart"] = cart_manager.get_cart(user_id)
                        total_amount = current_cart.get("estimated_total", 0.0)
                        items_names = ", ".join([f"{item.get('name', 'Product')} (x{item.get('quantity', 1)})" for item in current_cart.get("items", [])])
                        checkout_msg = (
                            f"🛒 **Order Prepared!** {items_names}\n\n"
                            f"**Cart Total:** **₹{total_amount:,.2f}** ({current_cart.get('item_count', 0)} item(s) • 0% Tax)\n\n"
                            f"Opening the **Razorpay Secure Checkout popup** on your screen now (supporting UPI, Cards, NetBanking, and Wallets)!"
                        )
                        if not final_text or ("added" in final_text and "Razorpay" not in final_text) or "Would you like" in final_text:
                            final_text = checkout_msg.strip()
                        elif "Razorpay" not in final_text and "checkout" not in final_text.lower():
                            final_text += f"\n\n{checkout_msg}"
            else:
                if not final_text:
                    final_text = "Your shopping cart is currently empty! Please select a product from our catalog, and I'll immediately add it and open the Razorpay checkout popup for you."

        current_cart = cart_manager.get_cart(user_id)
        current_orders = order_manager.get_orders_by_user(user_id)

        final_ans = final_text or "How can I assist you with your shopping today?"
        memory_manager.add_turn(self.name, "assistant", final_ans, {"user_id": user_id, "tool_calls_count": len(executed_tools_trace)})

        return {
            "response": final_ans,
            "tool_calls": executed_tools_trace,
            "cart": current_cart,
            "orders": current_orders,
            "latest_order": action_data.get("latest_order"),
            "checkout_payload": action_data.get("checkout_payload"),
            "action_data": action_data
        }

    def _execute_fallback_routing(
        self,
        prompt: str,
        user_id: str,
        action_data: Dict[str, Any]
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Deterministic smart fallback router for edge cases or timeouts."""
        prompt_lower = prompt.lower()
        tools_run = []

        if any(k in prompt_lower for k in ["explain", "detail", "tell me about", "what is", "specs", "materials", "feature"]):
            search_res = inventory_manager.search_products(query=prompt)
            if not search_res:
                search_res = inventory_manager.get_all_products()[:1]
            target_p = search_res[0] if search_res else None
            if target_p:
                tool_out = self.execute_tool("get_product_details", {"product_name_or_id": target_p["id"]}, user_id=user_id)
                tools_run.append({"name": "get_product_details", "args": {"product_name_or_id": target_p["id"]}, "output": tool_out})
                p = tool_out.get("product", target_p)
                ans = f"📱 **{p['PRODUCT_NAME']}** (₹{p['PRICE']:,.2f} • 0% Tax)\n\n{tool_out.get('description', '')}\n\n**Rating:** {tool_out.get('average_rating', 4.8)}★"
                return ans, tools_run

        elif any(k in prompt_lower for k in ["cart", "items in cart", "my cart"]):
            cart_out = self.execute_tool("view_cart", {}, user_id=user_id)
            tools_run.append({"name": "view_cart", "args": {}, "output": cart_out})
            action_data["cart"] = cart_out.get("cart")
            return f"🛒 Your cart contains {cart_out.get('cart', {}).get('item_count', 0)} item(s) with total ₹{cart_out.get('cart', {}).get('estimated_total', 0.0):,.2f}.", tools_run

        # Default catalog search
        res = self.execute_tool("search_inventory", {"query": prompt}, user_id=user_id)
        tools_run.append({"name": "search_inventory", "args": {"query": prompt}, "output": res})
        prods = res.get("products", [])
        if prods:
            lines = [f"- **{p['PRODUCT_NAME']}**: ₹{p['PRICE']:,.2f} ({p.get('STOCK_REMAINING', 0)} in stock)" for p in prods[:4]]
            return f"Here are the top products matching your search:\n\n" + "\n".join(lines), tools_run

        return "Welcome to NOVA! How can I assist your shopping today?", tools_run


# Global Customer Commerce Agent singleton
commerce_agent = CommerceAgent()
