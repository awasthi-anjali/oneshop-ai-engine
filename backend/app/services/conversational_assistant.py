import json
import re
from typing import Any

from openai import OpenAI

from app.config import settings
from app.models.schemas import ChatMessage, Product, ProductCategory, ProductSearchRequest
from app.services.customer_context import context_as_text
from app.services.conversation_store import conversation_store
from app.services.product_catalog import catalog
from app.services.session_store import session_store

SYSTEM_PROMPT = """You are ShopAssist, an AI shopping assistant for OneShop digital commerce.
Help customers discover, compare, and purchase phones, tablets, plans, and accessories.

You can take real actions using tools:
- Search and compare products
- Add items or bundles to the customer's cart
- View cart contents
- Check cart recovery offers for abandoned carts
- Prepare checkout when the customer is ready to buy

When the customer asks to add something, use add_to_cart or add_bundle_to_cart.
When they want to checkout or pay, use prepare_checkout.
Always confirm what you added or changed in your reply."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog by query, category, price range, brand, or tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in ProductCategory],
                        "description": "Filter by product category",
                    },
                    "max_price": {"type": "number", "description": "Maximum price in USD"},
                    "min_price": {"type": "number", "description": "Minimum price in USD"},
                    "brand": {"type": "string", "description": "Filter by brand name"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags like budget, premium, 5g, camera",
                    },
                    "limit": {"type": "integer", "description": "Max results to return", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Get full details for a specific product by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID from the catalog"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "Compare 2-4 products side by side by their IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of 2-4 product IDs to compare",
                    },
                },
                "required": ["product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List available product categories and counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a product to the customer's cart by product ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID from the catalog"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_bundle_to_cart",
            "description": "Add multiple products as a bundle to the cart (e.g. phone + plan).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Product IDs to add together",
                    },
                },
                "required": ["product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a product from the customer's cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart",
            "description": "Get current cart contents and subtotal for this customer session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recovery_offer",
            "description": "Check if customer has an abandoned cart recovery discount offer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_checkout",
            "description": "Open checkout for the customer when they are ready to pay. Use when they say checkout, pay, or complete order.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    session_id: str,
) -> tuple[str, list[Product], list[Product] | None, dict[str, bool]]:
    products: list[Product] = []
    comparison: list[Product] | None = None
    flags: dict[str, bool] = {"cart_updated": False, "open_checkout": False}

    if name == "search_products":
        category = arguments.get("category")
        req = ProductSearchRequest(
            query=arguments.get("query", ""),
            category=ProductCategory(category) if category else None,
            max_price=arguments.get("max_price"),
            min_price=arguments.get("min_price"),
            brand=arguments.get("brand"),
            tags=arguments.get("tags", []),
            limit=arguments.get("limit", 5),
        )
        products = catalog.search(req)
        payload = [
            {"id": p.id, "name": p.name, "price": p.price, "category": p.category.value, "brand": p.brand}
            for p in products
        ]
        return json.dumps(payload), products, None, flags

    if name == "get_product_details":
        product = catalog.get_by_id(arguments["product_id"])
        if not product:
            return json.dumps({"error": "Product not found"}), [], None, flags
        products = [product]
        return product.model_dump_json(), products, None, flags

    if name == "compare_products":
        comparison = catalog.compare(arguments["product_ids"])
        payload = [p.model_dump() for p in comparison]
        return json.dumps(payload), comparison, comparison, flags

    if name == "list_categories":
        return json.dumps({"categories": catalog.categories_summary(), "total": len(catalog.all)}), [], None, flags

    if name == "add_to_cart":
        pid = arguments.get("product_id", "")
        if not catalog.get_by_id(pid):
            return json.dumps({"error": f"Product not found: {pid}"}), [], None, flags
        session_store.add_to_cart(session_id, pid)
        flags["cart_updated"] = True
        cart = session_store.get_cart(session_id)
        products = cart
        payload = {
            "status": "added",
            "product_id": pid,
            "cart": [{"id": p.id, "name": p.name, "price": p.price} for p in cart],
            "cart_count": len(cart),
        }
        return json.dumps(payload), products, None, flags

    if name == "add_bundle_to_cart":
        pids = arguments.get("product_ids", [])
        added = []
        for pid in pids:
            if catalog.get_by_id(pid):
                session_store.add_to_cart(session_id, pid)
                added.append(pid)
        if not added:
            return json.dumps({"error": "No valid products in bundle"}), [], None, flags
        flags["cart_updated"] = True
        cart = session_store.get_cart(session_id)
        products = cart
        return json.dumps({
            "status": "bundle_added",
            "product_ids": added,
            "cart_count": len(cart),
        }), products, None, flags

    if name == "remove_from_cart":
        pid = arguments.get("product_id", "")
        session_store.remove_from_cart(session_id, pid)
        flags["cart_updated"] = True
        cart = session_store.get_cart(session_id)
        return json.dumps({"status": "removed", "cart_count": len(cart)}), cart, None, flags

    if name == "get_cart":
        cart = session_store.get_cart(session_id)
        products = cart
        subtotal = sum(p.price for p in cart)
        return json.dumps({
            "items": [{"id": p.id, "name": p.name, "price": p.price} for p in cart],
            "cart_count": len(cart),
            "subtotal": subtotal,
        }), cart, None, flags

    if name == "get_recovery_offer":
        status = session_store.get_abandonment_status(session_id)
        return json.dumps(status), [], None, flags

    if name == "prepare_checkout":
        cart = session_store.get_cart(session_id)
        if not cart:
            return json.dumps({"error": "Cart is empty"}), [], None, flags
        flags["open_checkout"] = True
        products = cart
        subtotal = sum(p.price for p in cart)
        return json.dumps({
            "status": "checkout_ready",
            "cart_count": len(cart),
            "subtotal": subtotal,
            "message": "Checkout opened for customer",
        }), cart, None, flags

    return json.dumps({"error": f"Unknown tool: {name}"}), [], None, flags


class ConversationalAssistant:
    def __init__(self) -> None:
        self._client: OpenAI | None = None
        if settings.openai_api_key:
            self._client = OpenAI(api_key=settings.openai_api_key)

    @property
    def uses_llm(self) -> bool:
        return self._client is not None

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        channel: str = "oneshop",
    ) -> tuple[str, ChatMessage, list[str], bool, bool]:
        sid, history = conversation_store.get_or_create(session_id)

        channel_note = f"[Channel: {channel}] "
        user_content = channel_note + message

        if self._client:
            ctx = context_as_text(sid)
            if ctx.strip():
                user_content += f"\n\n[Customer context — use this to personalize]\n{ctx}"

        history.append({"role": "user", "content": user_content})

        if self._client:
            return await self._chat_with_llm(sid, history)
        msg, chat_msg, suggested, _, _ = self._chat_fallback(sid, history, message)
        return msg, chat_msg, suggested, False, False

    async def _chat_with_llm(
        self,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> tuple[str, ChatMessage, list[str], bool, bool]:
        assert self._client is not None

        all_products: list[Product] = []
        comparison: list[Product] | None = None
        cart_updated = False
        open_checkout = False

        llm_history: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
        ]

        for _ in range(8):
            response = self._client.chat.completions.create(
                model=settings.openai_model,
                messages=llm_history,
                tools=TOOLS,
                tool_choice="auto",
            )
            choice = response.choices[0]
            assistant_msg = choice.message

            if assistant_msg.tool_calls:
                llm_history.append(assistant_msg.model_dump(exclude_none=True))
                for tool_call in assistant_msg.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    result, products, comp, flags = _execute_tool(
                        tool_call.function.name, args, session_id
                    )
                    if products:
                        all_products = products
                    if comp:
                        comparison = comp
                    if flags.get("cart_updated"):
                        cart_updated = True
                    if flags.get("open_checkout"):
                        open_checkout = True
                    llm_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue

            content = assistant_msg.content or "I'm here to help you shop!"
            history.append({"role": "assistant", "content": content})
            suggested = self._suggest_actions(content, all_products, comparison, cart_updated)
            chat_msg = ChatMessage(
                role="assistant",
                content=content,
                products=all_products[:5],
                comparison=comparison,
            )
            return session_id, chat_msg, suggested, cart_updated, open_checkout

        content = "Let me know if you'd like to search for something else!"
        chat_msg = ChatMessage(role="assistant", content=content, products=all_products[:5])
        return session_id, chat_msg, [], cart_updated, open_checkout

    def _chat_fallback(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        message: str,
    ) -> tuple[str, ChatMessage, list[str], bool, bool]:
        msg_lower = message.lower()
        products: list[Product] = []
        comparison: list[Product] | None = None
        content = ""

        if any(w in msg_lower for w in ["compare", "vs", "versus", "difference"]):
            ids = self._extract_product_ids(msg_lower)
            if len(ids) >= 2:
                comparison = catalog.compare(ids[:4])
                content = self._format_comparison(comparison)
            else:
                brand_pairs = self._guess_compare_brands(msg_lower)
                if brand_pairs:
                    found = catalog.search(ProductSearchRequest(query=brand_pairs[0], limit=1))
                    found += catalog.search(ProductSearchRequest(query=brand_pairs[1], limit=1))
                    if len(found) >= 2:
                        comparison = found[:2]
                        content = self._format_comparison(comparison)

        if not content:
            category = None
            if any(w in msg_lower for w in ["plan", "data", "unlimited"]):
                category = ProductCategory.PLAN
            elif any(w in msg_lower for w in ["phone", "smartphone", "iphone", "galaxy", "pixel"]):
                category = ProductCategory.PHONE
            elif any(w in msg_lower for w in ["tablet", "ipad"]):
                category = ProductCategory.TABLET
            elif any(w in msg_lower for w in ["accessory", "earbuds", "case", "charger", "airpods"]):
                category = ProductCategory.ACCESSORY

            max_price = None
            price_match = re.search(
                r"(?:under|below|less than|budget|max)\s*\$?(\d+)", msg_lower
            )
            if price_match:
                max_price = float(price_match.group(1))

            req = ProductSearchRequest(
                query=message,
                category=category,
                max_price=max_price,
                limit=5,
            )
            products = catalog.search(req)

            if products:
                content = self._format_recommendations(products, msg_lower)
            elif "hello" in msg_lower or "hi" in msg_lower:
                content = (
                    "Hello! I'm ShopAssist, your conversational shopping assistant. "
                    "I can help you discover phones, tablets, plans, and accessories. "
                    "Try asking something like:\n"
                    "• \"Show me phones under $500\"\n"
                    "• \"Compare iPhone 15 Pro vs Samsung S24 Ultra\"\n"
                    "• \"What's the best plan for a family?\""
                )
            else:
                content = (
                    "I couldn't find exact matches, but I can help you browse our catalog. "
                    "We have phones, tablets, mobile plans, accessories, and devices. "
                    "What are you looking for today?"
                )

        history.append({"role": "assistant", "content": content})
        suggested = self._suggest_actions(content, products, comparison, False)
        chat_msg = ChatMessage(
            role="assistant",
            content=content,
            products=products[:5] if not comparison else [],
            comparison=comparison,
        )
        return session_id, chat_msg, suggested, False, False

    def _extract_product_ids(self, text: str) -> list[str]:
        known_ids = [p.id for p in catalog.all]
        return [pid for pid in known_ids if pid.replace("-", " ") in text or pid in text]

    def _guess_compare_brands(self, text: str) -> tuple[str, str] | None:
        pairs = [
            ("iphone", "samsung"), ("iphone", "galaxy"), ("apple", "samsung"),
            ("pixel", "iphone"), ("oneplus", "samsung"),
        ]
        for a, b in pairs:
            if a in text and b in text:
                return (a, b)
        return None

    def _format_recommendations(self, products: list[Product], query: str) -> str:
        lines = [f"Here are my top picks based on your request:"]
        for i, p in enumerate(products[:5], 1):
            lines.append(f"{i}. **{p.name}** — ${p.price:.0f} ({p.brand})")
            lines.append(f"   {p.description[:100]}...")
        lines.append("\nWould you like details on any of these, or should I compare a few?")
        return "\n".join(lines)

    def _format_comparison(self, products: list[Product]) -> str:
        if len(products) < 2:
            return "I need at least two products to compare. Which ones interest you?"

        names = " vs ".join(p.name for p in products)
        lines = [f"Here's a comparison of **{names}**:\n"]

        lines.append("| Feature | " + " | ".join(p.name for p in products) + " |")
        lines.append("|" + "---|" * (len(products) + 1))

        rows = [
            ("Price", [f"${p.price:.0f}" for p in products]),
            ("Brand", [p.brand for p in products]),
            ("Rating", [f"{p.rating}/5" for p in products]),
            ("Category", [p.category.value for p in products]),
        ]
        for label, values in rows:
            lines.append(f"| {label} | " + " | ".join(values) + " |")

        lines.append("\n**Key differences:**")
        cheapest = min(products, key=lambda p: p.price)
        best_rated = max(products, key=lambda p: p.rating)
        lines.append(f"• Most affordable: {cheapest.name} at ${cheapest.price:.0f}")
        lines.append(f"• Highest rated: {best_rated.name} ({best_rated.rating}/5)")

        return "\n".join(lines)

    def _suggest_actions(
        self,
        content: str,
        products: list[Product],
        comparison: list[Product] | None,
        cart_updated: bool = False,
    ) -> list[str]:
        actions = []
        if cart_updated:
            actions.append("Proceed to checkout")
            actions.append("Show my cart")
        if products and not comparison:
            if len(products) >= 2:
                actions.append(f"Compare {products[0].name} and {products[1].name}")
            actions.append("Show me cheaper options")
            actions.append("What's included in the box?")
        if comparison:
            actions.append("Which one has better battery life?")
            actions.append("Add the best value to my cart")
        if not products and not comparison:
            actions.extend([
                "Show me phones under $500",
                "Compare iPhone vs Samsung",
                "Best family plan",
            ])
        return actions[:3]


assistant = ConversationalAssistant()
