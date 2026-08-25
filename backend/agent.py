"""
Customer AI Commerce Agent ('Nova')
===================================
Autonomous customer-facing AI agent for the AI Growth Commerce Store.
Powered by Groq LLMs (GPT-OSS / open-source models) with native tool calling.

Capabilities:
  - Product Catalog Discovery & Multi-Factor Filtering
  - In-Depth Product Specs, Materials & Review Summaries
  - Shopping Cart Operations (Single & Batch Add, Remove, Clear, View)
  - Real-Time Razorpay Secure Checkout Popup Triggering
  - Order Tracking, 24-Hour Cancellations & Automated Refunds
  - Customer Review Lookup & Verified Review Submission
"""

import os
import re
import json
import asyncio
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from groq import AsyncGroq, Groq

# Backend Managers
from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager
from backend.review_manager import review_manager

load_dotenv()

# =====================================================================
# 1. MODEL & API CONFIGURATION
# =====================================================================

DEFAULT_GROQ_API_KEY = os.environ.get("CUSTOMER_GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))

# Dedicated Groq models (Qwen for Customer Agent with fast fallback)
DEFAULT_MODELS = [
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

DEFAULT_MODEL = os.environ.get("GROQ_CUSTOMER_MODEL", "qwen/qwen3.6-27b")


# =====================================================================
# 2. TOOL DEFINITIONS FOR GROQ FUNCTION CALLING
# =====================================================================

AGENT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": "Search the NOVA product catalog by keyword query, product categories (Mobiles, Laptops, Audio, Accessories), price budget range, or in-stock status. Always search broadly — don't limit results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": ["string", "null"],
                        "description": "Search keywords (e.g. 'flagship mobile', 'gaming laptop', 'wireless earphone', 'bluetooth speaker', 'smart watch', 'power bank')."
                    },
                    "product_types": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Categories to filter: ['Mobiles', 'Laptops', 'Audio', 'Accessories']. Use the exact category name."
                    },
                    "size": {
                        "type": ["string", "null"],
                        "description": "Specific size or variant to filter by (e.g. 'One Size', 'Standard')."
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
                        "description": "Pass true to filter only in-stock items with stock > 0."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Retrieve comprehensive product details including full description, technical specifications, materials, available size variants, live pricing, stock levels, customer ratings, and AI review summaries. Use whenever a customer asks to explain a product or learn about its features.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {
                        "type": ["string", "null"],
                        "description": "Product ID (e.g. 'prod_001') or name keyword (e.g. 'CyberFlex Apex Runner', 'Quantum Shield Parka')."
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
            "name": "check_stock_availability",
            "description": "Check real-time stock levels for one or multiple product names or IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product names or IDs to check stock for."
                    },
                    "size": {
                        "type": ["string", "null"],
                        "description": "Optional specific size variant to check."
                    }
                },
                "required": ["product_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a single product to the user's shopping cart with specified quantity and size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {
                        "type": ["string", "null"],
                        "description": "Product ID or product name to add."
                    },
                    "product_id": {
                        "type": ["string", "null"],
                        "description": "Product ID (e.g. 'prod_001')."
                    },
                    "product_name": {
                        "type": ["string", "null"],
                        "description": "Product name."
                    },
                    "quantity": {
                        "type": ["integer", "null"],
                        "description": "Quantity of units to add (default is 1)."
                    },
                    "size": {
                        "type": ["string", "null"],
                        "description": "Selected size variant (e.g. 'US 10', 'L', 'M', 'One Size')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_add_to_cart",
            "description": "Add multiple products to the shopping cart in a single batch operation. Use when the customer wants to add several items, all search results, or an entire category (e.g. 'add all accessories to my cart').",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name_or_id": {
                                    "type": ["string", "null"],
                                    "description": "Product ID or name."
                                },
                                "product_id": {
                                    "type": ["string", "null"],
                                    "description": "Product ID."
                                },
                                "quantity": {
                                    "type": ["integer", "null"],
                                    "description": "Quantity to add (default 1)."
                                },
                                "size": {
                                    "type": ["string", "null"],
                                    "description": "Size variant (optional)."
                                }
                            }
                        },
                        "description": "List of product items to add to the cart."
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
            "description": "Remove an item or decrease its quantity in the user's shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {
                        "type": ["string", "null"],
                        "description": "Product ID or name to remove."
                    },
                    "product_id": {
                        "type": ["string", "null"],
                        "description": "Product ID to remove."
                    },
                    "quantity": {
                        "type": ["integer", "null"],
                        "description": "Number of units to remove. If omitted, removes the item entirely."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_cart",
            "description": "Empty all items from the user's shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "View the user's current shopping cart contents, itemized prices, 0% tax free breakdown, and total in INR (₹).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_razorpay_checkout",
            "description": "Trigger and open the official Razorpay Secure Checkout popup modal directly on the customer's screen for their shopping cart. Use whenever the customer asks to checkout, pay, buy, or place their order.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_order_history",
            "description": "Retrieve past confirmed orders for the current user including status, tracking numbers, items, and totals.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_order",
            "description": "Track status, live delivery estimate, tracking number, and package details for a specific order ID (or user's most recent order).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": ["string", "null"],
                        "description": "The order ID (e.g. 'ORD-1001'). If omitted, tracks the user's latest order."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Evaluate and process an order cancellation under the 24-hour cancellation rule. Restocks inventory and initiates full refund on Razorpay Gateway if eligible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": ["string", "null"],
                        "description": "Order ID to cancel. If omitted, targets the latest order."
                    },
                    "reason": {
                        "type": ["string", "null"],
                        "description": "Reason for cancellation."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_order_refund",
            "description": "Process a refund for an order via Razorpay Gateway. Restocks inventory and marks the order as Refunded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": ["string", "null"],
                        "description": "The order ID to refund (e.g. 'ORD-1001'). If omitted, targets the latest eligible order."
                    },
                    "reason": {
                        "type": ["string", "null"],
                        "description": "Reason for the refund request."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_reviews",
            "description": "Get verified customer reviews, star ratings, and AI sentiment summaries for a product.",
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
            "name": "submit_product_review",
            "description": "Submit a verified customer review (1 to 5 star rating and comment) for a product, updating the catalog rating in real time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name_or_id": {
                        "type": "string",
                        "description": "Product ID or name being reviewed."
                    },
                    "rating": {
                        "type": "integer",
                        "description": "Star rating from 1 to 5."
                    },
                    "review_text": {
                        "type": "string",
                        "description": "Text review / feedback."
                    },
                    "customer_name": {
                        "type": ["string", "null"],
                        "description": "Customer display name (optional)."
                    }
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
- Tax Policy: **0% Tax** (Tax-free on all products)
- Categories: **Mobiles**, **Laptops**, **Audio** (earphones, headphones, speakers, mics), **Accessories** (smart watches, keyboards, mice, power banks, bags, chargers)

══════════════════════════════════════════════════════════════════════
🛠️ CORE REASONING & TOOL CALLING RULES
══════════════════════════════════════════════════════════════════════
1. ALWAYS use tools to fetch real data. NEVER guess prices, stock, specs, or order status.
2. Always format prices in INR (₹) with 0% Tax.
3. **QUANTITY RULE (CRITICAL):** Always honour the EXACT quantity the user asks for. If the user says "2 units" or "buy 3", pass that exact quantity to the tool. NEVER default to 1 if a quantity is specified.
4. **SUGGESTION RULE:** When a user asks for a product category (e.g. "show me audio"), always search and display ALL relevant products with specs, prices, and ratings. Don't stop at one result.
5. Multi-Step Execution: Execute all required tool calls in sequence in the same turn:
   - Find products → `search_inventory`
   - Add to cart → `add_to_cart` / `batch_add_to_cart`
   - Checkout → `trigger_razorpay_checkout`
6. After tool responses, summarize results with rich markdown tables, bullet points, price breakdowns in ₹, and emoji highlights.

══════════════════════════════════════════════════════════════════════
🔍 PRODUCT DISCOVERY & IN-DEPTH EXPLANATIONS
══════════════════════════════════════════════════════════════════════
- "Show me mobiles" → `search_inventory` with product_types=["Mobiles"]
- "Show me audio" → `search_inventory` with product_types=["Audio"]
- "Show me laptops" → `search_inventory` with product_types=["Laptops"]
- "Show me accessories" → `search_inventory` with product_types=["Accessories"]
- "Tell me about X" → Call `get_product_details` + `get_product_reviews`.
  Present a rich breakdown: specs, RAM/storage/battery, connectivity, price, rating, reviews.

══════════════════════════════════════════════════════════════════════
🛍️ SHOPPING CART WORKFLOWS
══════════════════════════════════════════════════════════════════════
- "Add 2 [product] to cart" → `add_to_cart` with quantity=2 (EXACTLY as specified)
- "Add all audio to cart" → `search_inventory` then `batch_add_to_cart`
- "View my cart" → `view_cart`
- "Remove X" → `remove_from_cart`
- "Clear cart" → `clear_cart`

══════════════════════════════════════════════════════════════════════
💳 CHECKOUT & RAZORPAY PAYMENT
══════════════════════════════════════════════════════════════════════
Whenever the customer wants to buy, pay, checkout, or place an order:
1. Ensure the cart has the requested items. If empty and user mentioned products, search and add them first.
2. Call `trigger_razorpay_checkout` — this creates a real Razorpay Order and signals the browser to open the official Razorpay popup.
3. Tell the user: "I've prepared your Razorpay checkout! The secure payment window is opening now — complete your payment using Card / UPI / NetBanking."
4. NEVER directly place an order without triggering Razorpay checkout first.

══════════════════════════════════════════════════════════════════════
📦 ORDERS, LOGISTICS, REFUNDS & REVIEWS
══════════════════════════════════════════════════════════════════════
- "Where is my order?" / "Track order" → `track_order` or `view_order_history`
- "Cancel my order" → `cancel_order` (evaluates 24-hour rule, restocks inventory, refunds payment)
- "Refund my order" → `request_order_refund`
- "Reviews for X" → `get_product_reviews`
- "Submit review for X" → `submit_product_review`
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


# =====================================================================
# 5. COMMERCE AGENT CLASS
# =====================================================================

class CommerceAgent:
    """
    Intelligent Customer AI Agent that interacts with users through natural language,
    executes tool calls with high precision, and maintains synced cart/order states.
    """

    def __init__(
        self,
        api_key: str = DEFAULT_GROQ_API_KEY,
        model: str = DEFAULT_MODEL,
        fallback_models: Optional[List[str]] = None
    ):
        self.api_key = api_key
        self.model = model
        self.fallback_models = fallback_models or DEFAULT_MODELS
        self.client: Optional[AsyncGroq] = None
        self.sync_client: Optional[Groq] = None
        self._init_client()

    def _init_client(self):
        """Initializes Groq async and sync clients."""
        try:
            if self.api_key:
                self.client = AsyncGroq(api_key=self.api_key)
                self.sync_client = Groq(api_key=self.api_key)
            else:
                self.client = None
                self.sync_client = None
        except Exception as e:
            print(f"[Customer AI] Groq client init warning: {e}", flush=True)
            self.client = None
            self.sync_client = None

    async def _call_llm_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ):
        """
        Asynchronously calls Groq LLM with automatic fallback across models.
        """
        models_to_try = [self.model] + [m for m in self.fallback_models if m != self.model]
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
                        "max_tokens": min(max_tokens, 2000),
                        "timeout": 18.0
                    }
                    if tools:
                        kwargs["tools"] = tools
                        if tool_choice:
                            kwargs["tool_choice"] = tool_choice

                    print(f"[Customer AI] Calling Groq model '{model_name}' (messages: {len(messages)})...", flush=True)
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(self.sync_client.chat.completions.create, **kwargs),
                        timeout=18.0
                    )
                    print(f"[Customer AI] Model '{model_name}' returned successfully.", flush=True)
                    return resp
                except Exception as e:
                    err_str = str(e)
                    print(f"[Customer AI Warning] {model_name} (attempt {attempt + 1}): {err_str}", flush=True)
                    last_error = e
                    # If daily token limit reached (TPD), immediately skip to next fallback model
                    if "tpd" in err_str.lower() or "tokens per day" in err_str.lower():
                        break
                    if "429" in err_str or "rate_limit" in err_str.lower():
                        # Immediately try fallback model on 429 rate limit
                        break
                    break

        raise last_error or Exception("All Customer Groq models exhausted.")

    def execute_tool(self, tool_name: str, tool_args: Dict[str, Any], user_id: str = "user_alex") -> Dict[str, Any]:
        """
        Dispatches and executes the specified backend tool with robust argument parsing.
        """
        try:
            # 1. Search Catalog Inventory
            if tool_name == "search_inventory":
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

            # 2. Get In-Depth Product Details
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
                    # Find all size variants for this product
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
                return {
                    "found": False,
                    "error": f"Product '{ident}' not found in catalog."
                }

            # 3. Check Live Stock Levels
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

            # 4. Add Single Item to Cart
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

            # 5. Batch Add Items to Cart
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

            # 6. Remove Item from Cart
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

            # 7. Clear Entire Cart
            elif tool_name == "clear_cart":
                cart_manager.clear_cart(user_id)
                return {"success": True, "message": "Cart cleared successfully."}

            # 8. View Cart Contents
            elif tool_name == "view_cart":
                return {
                    "success": True,
                    "cart": cart_manager.get_cart(user_id)
                }

            # 9. Trigger Razorpay Checkout Popup Modal (Primary & Only Checkout Path)
            elif tool_name == "trigger_razorpay_checkout":
                return payment_manager.trigger_cart_checkout(user_id=user_id)

            # 10. View Past Order History
            elif tool_name == "view_order_history":
                orders = order_manager.get_orders_by_user(user_id)
                return {
                    "success": True,
                    "order_count": len(orders),
                    "orders": orders
                }

            # 11. Track Order Status
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

            # 12. Cancel Order (24-Hour Policy)
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

            # 13. Request Razorpay Order Refund
            elif tool_name == "request_order_refund":
                order_id = tool_args.get("order_id")
                if not order_id:
                    user_orders = order_manager.get_orders_by_user(user_id)
                    if user_orders:
                        for o in user_orders:
                            if o.get("status") in ["Confirmed", "Dispatched", "Shipped"]:
                                order_id = o.get("order_id")
                                break
                        if not order_id and user_orders:
                            order_id = user_orders[0].get("order_id")

                if not order_id:
                    return {"success": False, "error": "No eligible orders found to refund."}

                return payment_manager.process_refund(
                    order_id=order_id,
                    reason=tool_args.get("reason", "Customer requested refund via Agent")
                )

            # 14. Get Product Reviews
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

            # 15. Submit Verified Product Review
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

            else:
                return {"error": f"Unknown tool '{tool_name}'"}

        except Exception as e:
            return {"error": f"Tool execution error: {str(e)}"}

    async def run_prompt(
        self,
        prompt: str,
        user_id: str = "user_alex",
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Executes a customer prompt through the ReAct loop using Groq Tool Calling,
        falling back seamlessly to deterministic tool execution if API limits occur.
        """
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject conversation history (last 6 turns)
        if conversation_history:
            for msg in conversation_history[-6:]:
                role = msg.get("role", "user")
                if role in ["user", "assistant"]:
                    messages.append({"role": role, "content": msg.get("content", "")})

        # Append current user prompt
        messages.append({"role": "user", "content": prompt})

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

                # If no tool calls, model provided conversational answer
                if not tool_calls:
                    final_text = clean_think_tags(response_message.content or "")
                    break

                # Add assistant message with tool calls to context
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

                # Execute each tool call
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

                    # Track state updates for frontend synchronization
                    if fname in ["add_to_cart", "batch_add_to_cart", "remove_from_cart", "clear_cart", "view_cart"]:
                        action_data["cart"] = cart_manager.get_cart(user_id)
                    elif fname == "trigger_razorpay_checkout":
                        action_data["cart"] = cart_manager.get_cart(user_id)
                        if tool_output.get("needs_razorpay_checkout"):
                            action_data["checkout_payload"] = tool_output
                    elif fname in ["request_order_refund", "cancel_order", "view_order_history", "track_order"]:
                        action_data["orders"] = order_manager.get_orders_by_user(user_id)
                    elif fname == "search_inventory":
                        action_data["searched_products"] = tool_output.get("products", [])
                    elif fname == "get_product_details" and tool_output.get("found"):
                        action_data["product_details"] = tool_output.get("product")

                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fname,
                        "content": json.dumps(tool_output)
                    })

                # If primary terminal tool ran, break to generate final answer
                tool_names_run = [t["name"] for t in executed_tools_trace]
                if any(t in tool_names_run for t in [
                    "trigger_razorpay_checkout", "get_product_details", "track_order",
                    "request_order_refund", "cancel_order", "submit_product_review"
                ]):
                    break

            # If loop finished without final text, generate final synthesis (no tools needed)
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

        # Refresh final state for response payload
        current_cart = cart_manager.get_cart(user_id)
        current_orders = order_manager.get_orders_by_user(user_id)

        return {
            "response": final_text or "How can I assist you with your shopping today?",
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
        """
        Deterministic smart fallback router for edge cases or network timeouts.
        """
        prompt_lower = prompt.lower()
        tools_run = []

        # 1. Product Explanation / Details Intent
        if any(k in prompt_lower for k in ["explain", "detail", "tell me about", "what is", "specs", "materials", "feature"]):
            search_res = inventory_manager.search_products(query=prompt)
            if not search_res:
                search_res = inventory_manager.get_all_products()[:1]
            target_p = search_res[0] if search_res else None
            if target_p:
                tool_out = self.execute_tool("get_product_details", {"product_name_or_id": target_p["id"]}, user_id=user_id)
                tools_run.append({"name": "get_product_details", "args": {"product_name_or_id": target_p["id"]}, "output": tool_out})
                p = tool_out.get("product", target_p)
                sizes_str = ", ".join([f"`{s['size']}`" for s in tool_out.get("available_sizes", [])]) or "Standard"
                text = (
                    f"✨ **{p['PRODUCT_NAME']}** ({p.get('PRODUCT_TYPE', 'Product')})\n\n"
                    f"**Price:** **${p.get('PRICE')}** | **Rating:** ⭐ **{p.get('RATING', 4.8)}/5.0** | **Stock:** {p.get('STOCK_REMAINING', 0)} in stock\n\n"
                    f"📝 **Overview & Engineering:**\n{p.get('DESCRIPTION', 'Premium quality engineering designed for performance.')}\n\n"
                    f"📏 **Available Sizes:** {sizes_str}\n\n"
                    f"⭐ **Customer Sentiment:**\n{p.get('AI_REVIEW_SUMMARY', 'Customers highly praise the durability, build quality, and comfort.')}\n\n"
                    f"Would you like me to add this to your shopping cart or open Razorpay checkout?"
                )
                action_data["product_details"] = p
                return text, tools_run
            return "I searched our catalog but couldn't find an exact match. Let me know what category or item you are looking for!", tools_run

        # 2. Reviews Intent
        elif any(k in prompt_lower for k in ["review", "rating", "feedback"]):
            tool_out = self.execute_tool("get_product_reviews", {"product_name_or_id": prompt}, user_id=user_id)
            tools_run.append({"name": "get_product_reviews", "args": {"product_name_or_id": prompt}, "output": tool_out})
            revs = tool_out.get("reviews", [])
            p_name = tool_out.get("product_name", "Product")
            avg = tool_out.get("average_rating", 4.9)
            rev_list = "\n".join([
                f"- ⭐ **{r.get('rating', 5)}/5** by *{r.get('customer_name', 'Verified Buyer')}*: \"{r.get('review_text', '')}\""
                for r in revs[:3]
            ]) or "No written reviews yet."
            text = f"⭐ **Customer Reviews for {p_name}** (Rating: **{avg} / 5.0**)\n\n{rev_list}\n\n*AI Summary:* {tool_out.get('ai_summary', '')}"
            return text, tools_run

        # 3. Refund / Cancel Intent
        elif any(k in prompt_lower for k in ["refund", "cancel"]):
            tool_out = self.execute_tool("request_order_refund", {"reason": "Customer request"}, user_id=user_id)
            tools_run.append({"name": "request_order_refund", "args": {"reason": "Customer request"}, "output": tool_out})
            if tool_out.get("success"):
                ord_obj = tool_out.get("order", {})
                ref_d = tool_out.get("refund_details", {})
                text = (
                    f"✅ **Refund Processed Successfully!**\n\n"
                    f"- **Order ID**: `#{ord_obj.get('order_id')}`\n"
                    f"- **Refund ID**: `{ref_d.get('refund_id')}`\n"
                    f"- **Amount**: **${ref_d.get('amount')}**\n"
                    f"- **Gateway**: `Razorpay Gateway`\n"
                    f"- **Inventory**: Restocked automatically."
                )
                action_data["orders"] = order_manager.get_orders_by_user(user_id)
            else:
                text = f"⚠️ Could not process refund: {tool_out.get('error', 'No eligible orders found')}"
            return text, tools_run

        # 4. Track Order Intent
        elif any(k in prompt_lower for k in ["track", "status", "where is my order"]):
            tool_out = self.execute_tool("track_order", {}, user_id=user_id)
            tools_run.append({"name": "track_order", "args": {}, "output": tool_out})
            if tool_out.get("found"):
                latest = tool_out["order"]
                trk = latest.get("tracking_number", "TRK-LOGISTICS-PENDING")
                text = (
                    f"📦 **Order #{latest['order_id']} Status:**\n\n"
                    f"- **Status**: `{latest.get('status', 'Confirmed')}`\n"
                    f"- **Tracking #**: `{trk}`\n"
                    f"- **Items**: {len(latest.get('items', []))} item(s)\n"
                    f"- **Estimated Delivery**: {latest.get('delivery_estimate', '2-3 Business Days')}\n"
                    f"- **Total**: ${latest.get('total')}"
                )
            else:
                text = "You do not have any past orders yet. Browse our catalog to place your first order!"
            return text, tools_run

        # 5. Clear Cart Intent
        elif "clear" in prompt_lower and "cart" in prompt_lower:
            tool_out = self.execute_tool("clear_cart", {}, user_id=user_id)
            tools_run.append({"name": "clear_cart", "args": {}, "output": tool_out})
            action_data["cart"] = cart_manager.get_cart(user_id)
            return "🗑️ Your shopping cart has been cleared.", tools_run

        # 6. Checkout / Buy / Order Intent -> Always Pop Razorpay Checkout Modal
        elif any(k in prompt_lower for k in ["order", "buy", "pay", "checkout"]):
            cart = cart_manager.get_cart(user_id)
            if not cart.get("items"):
                search_res = inventory_manager.search_products(query=prompt)
                if not search_res:
                    search_res = inventory_manager.get_all_products()[:2]
                items_to_add = [{"product_name_or_id": p["id"], "quantity": 1} for p in search_res]
                self.execute_tool("batch_add_to_cart", {"items": items_to_add}, user_id=user_id)
                tools_run.append({"name": "batch_add_to_cart", "args": {"items": items_to_add}, "output": {"success": True}})

            chk_res = self.execute_tool("trigger_razorpay_checkout", {}, user_id=user_id)
            tools_run.append({"name": "trigger_razorpay_checkout", "args": {}, "output": chk_res})
            action_data["checkout_payload"] = chk_res
            cart = cart_manager.get_cart(user_id)
            text = (
                f"🛒 **Order Prepared!** Cart Total: **${cart.get('estimated_total', 0.0):.2f}** ({cart.get('item_count', 0)} item(s)).\n\n"
                f"Opening the **Razorpay Secure Checkout popup** on your screen now (supporting UPI, Cards, NetBanking, and Wallets)!"
            )
            return text, tools_run

        # 7. Add to Cart Intent
        elif "add" in prompt_lower or "cart" in prompt_lower:
            search_res = inventory_manager.search_products(query=prompt)
            if not search_res:
                search_res = inventory_manager.get_all_products()[:2]
            items_to_add = [{"product_name_or_id": p["id"], "quantity": 1} for p in search_res]
            tool_out = self.execute_tool("batch_add_to_cart", {"items": items_to_add}, user_id=user_id)
            tools_run.append({"name": "batch_add_to_cart", "args": {"items": items_to_add}, "output": tool_out})
            action_data["cart"] = cart_manager.get_cart(user_id)
            text = f"🛒 Added **{len(items_to_add)} item(s)** to your shopping cart:\n" + "\n".join([f"- **{p['PRODUCT_NAME']}** (${p['PRICE']})" for p in search_res])
            return text, tools_run

        # 8. Default: Search Catalog
        else:
            search_res = inventory_manager.search_products(query=prompt)
            if not search_res:
                search_res = inventory_manager.get_all_products()[:4]
            tools_run.append({"name": "search_inventory", "args": {"query": prompt}, "output": {"count": len(search_res), "products": search_res}})
            action_data["searched_products"] = search_res
            items_table = "\n".join([f"| {p['PRODUCT_NAME']} | {p.get('PRODUCT_TYPE')} | **${p['PRICE']}** | Stock: {p.get('STOCK_REMAINING', 0)} |" for p in search_res[:5]])
            text = f"Here are the matching items found in our catalog:\n\n| Product | Category | Price | Stock |\n|---|---|---|---|\n{items_table}\n\nWould you like me to explain any product in detail, add items to your cart, or open Razorpay checkout?"
            return text, tools_run

    def run_prompt_sync(
        self,
        prompt: str,
        user_id: str = "user_alex",
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Synchronous wrapper for test environments or synchronous callers."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, self.run_prompt(prompt, user_id, conversation_history)).result()
            else:
                return loop.run_until_complete(self.run_prompt(prompt, user_id, conversation_history))
        except Exception:
            return asyncio.run(self.run_prompt(prompt, user_id, conversation_history))


# Global singleton Customer AI Agent
commerce_agent = CommerceAgent()
