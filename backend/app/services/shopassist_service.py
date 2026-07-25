from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.models.schemas import (
    ChatMode,
    ChatRequest,
    ChatResponse,
    ChatStatus,
    CartConfirmationRequest,
    CartConfirmationResponse,
    CartProposal,
    CartSummary,
    NeedProfile,
    Product,
    ProductCategory,
    ReasonCode,
    RecommendationSlot,
    ShopAssistAction,
    ShopAssistActionType,
    ShopAssistRecommendation,
)
from app.services.commerce_store import commerce_store
from app.services.guardrails import (
    BOUNDARY_UNSUPPORTED_MESSAGE,
    is_prompt_injection_or_off_topic,
)
from app.services.product_catalog import catalog
from app.services.behavioral_memory import (
    BehavioralMemoryPatch,
    BehavioralMemoryStore,
    behavioral_memory_store,
    bounded_memory_context,
    deterministic_memory_patch,
)
from app.services.personalized_recommendation import (
    bounded_preference_context,
    resolve_profile_session,
)
from app.services.session_store import session_store
from app.services.shopassist_prompt import (
    DREAMING_AGENT_SYSTEM_PROMPT,
    SHOPASSIST_RESPONSE_SYSTEM_PROMPT,
    SHOPASSIST_SYSTEM_PROMPT,
)
from app.services.smart_cart_service import (
    format_smart_cart_chat_hints,
    get_smart_cart,
    smart_cart_chat_suffix,
)


SERVICE_WORDS = (
    "bill", "billing", "account", "contract", "network", "signal", "outage",
    "not working", "technical support", "fault", "password", "login",
)
UNSUPPORTED_WORDS = ()  # legacy; see guardrails.INJECTION_PHRASES
SHOPPING_WORDS = (
    "phone", "iphone", "android", "pixel", "galaxy", "oneplus", "plan",
    "tablet", "data", "camera", "photography", "roaming", "travel", "budget",
    "compare", "recommend", "choose", "buy", "add", "bundle", "compact", "charging",
    "discount", "deal", "coupon", "cheaper", "expensive", "sale", "cart",
    "cashback", "cash back", "promotion", "promo", "offer", "rebate",
    "suggest", "sugest", "affordable", "remove", "delete", "empty", "clear",
    "basket", "tuck",
)

logger = logging.getLogger(__name__)
route_logger = logging.getLogger("uvicorn.error")


@dataclass
class _State:
    need: NeedProfile = field(default_factory=NeedProfile)
    turns: list[dict[str, str]] = field(default_factory=list)
    clarification_asked: bool = False
    recommendations: list[ShopAssistRecommendation] = field(default_factory=list)
    total_user_turns: int = 0
    pending_cart_operation: Literal["add", "remove"] | None = None
    pending_cart_turn: int = 0


class _ComposedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=600)


class _AIInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["shopping", "unsupported", "service"]
    goal: Literal[
        "catalog_browse",
        "recommend",
        "compare",
        "cart_lookup",
        "cart_add",
        "cart_remove",
        "start_checkout",
        "converse",
    ] = "recommend"
    scope: Literal["replace", "merge", "retain"] = "retain"
    need_patch: dict[str, Any] = Field(default_factory=dict)
    product_ids: list[str] = Field(default_factory=list, max_length=20)
    browse_categories: list[
        Literal["phone", "plan", "tablet", "accessory", "device"]
    ] = Field(default_factory=list, max_length=5)
    all_cart_items: bool = False


class ShopAssistService:
    def __init__(self, memory_store: BehavioralMemoryStore | None = None) -> None:
        self._states: dict[str, _State] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._memory_store = memory_store or behavioral_memory_store
        self._memory_tasks: set[asyncio.Task] = set()
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key else None
        )

    @property
    def uses_llm(self) -> bool:
        return self._client is not None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._validate_context(request)
        sid = (
            resolve_profile_session(request.user_id, request.session_id, request.channel.value)
            if request.user_id
            else session_store.get_or_create(request.session_id or str(uuid.uuid4()))
        )
        request = request.model_copy(update={"session_id": sid})
        async with self._locks[sid]:
            state = self._states.setdefault(sid, _State())
            state.total_user_turns += 1
            checkout_response = self._checkout_confirmation_transition(sid, request, state)
            if checkout_response is not None:
                return checkout_response
            response = await self._chat_locked(sid, request)
            if request.user_id and state.total_user_turns % 5 == 0:
                self._schedule_memory_update(
                    request.user_id,
                    sid,
                    state.total_user_turns,
                    list(state.turns),
                    state.need,
                )
            return response

    async def confirm_cart(self, request: CartConfirmationRequest) -> CartConfirmationResponse:
        sid = (
            resolve_profile_session(request.user_id, request.session_id, request.channel.value)
            if request.user_id
            else session_store.get_or_create(request.session_id)
        )
        async with self._locks[sid]:
            data = commerce_store.confirm_proposal(
                request.proposal_id,
                request.idempotency_key,
                sid,
                request.user_id,
            )
            return CartConfirmationResponse(
                **data,
                cart_summary=self._cart_summary(sid),
            )

    def _checkout_confirmation_transition(
        self,
        sid: str,
        request: ChatRequest,
        state: _State,
    ) -> ChatResponse | None:
        context = request.checkout_confirmation
        if context is None:
            return None
        normalized = " ".join(
            re.sub(r"[^a-z\s]", "", request.message.lower()).split()
        )
        confirm_phrases = {"yes", "confirm", "place order", "go ahead"}
        cancel_phrases = {"no", "cancel", "go back"}
        if normalized not in confirm_phrases | cancel_phrases:
            return None
        state.turns.append({"role": "user", "content": request.message.strip()})
        state.turns = state.turns[-12:]
        if normalized in cancel_phrases:
            commerce_store.cancel_review(
                context.review_id,
                sid,
                request.user_id,
            )
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                "Demo checkout cancelled. Your cart is unchanged.",
                [],
                [],
                ChatMode.FALLBACK,
                checkout_review_status="cancelled",
            )
        receipt = commerce_store.place_order(
            context.review_id,
            context.confirmation_token,
            context.idempotency_key,
            sid,
            request.user_id,
        )
        once = (
            f"${receipt.one_time_total_minor / 100:.2f} once"
            if receipt.one_time_total_minor
            else ""
        )
        monthly = (
            f"${receipt.monthly_total_minor / 100:.2f}/month"
            if receipt.monthly_total_minor
            else ""
        )
        totals = " and ".join(value for value in (once, monthly) if value)
        return self._response(
            sid,
            state,
            ChatStatus.RECOMMENDED,
            (
                f"Demo order {receipt.order_id} is saved for {totals}. "
                "No real payment was processed and no email has been sent."
            ),
            [],
            [],
            ChatMode.FALLBACK,
            checkout_review_status="consumed",
            order_receipt=receipt,
        )

    async def wait_for_memory_updates(self) -> None:
        pending = list(self._memory_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _validate_context(self, request: ChatRequest) -> None:
        context = request.page_context
        if not context:
            return
        ids = ([context.product_id] if context.product_id else []) + context.visible_product_ids
        invalid = [pid for pid in ids if not catalog.get_by_id(pid)]
        if invalid:
            raise ValueError(f"Unknown product ID: {invalid[0]}")

    async def _chat_locked(self, sid: str, request: ChatRequest) -> ChatResponse:
        state = self._states.setdefault(sid, _State())
        text = request.message.strip()
        lowered = text.lower()
        before_cart = set(session_store.get_cart_ids(sid))
        assistant_context = self._assistant_context(request.user_id, sid, state)
        effective_memory, current_turn_style = self._effective_behavioral_context(
            lowered,
            assistant_context.get("behavioral_memory", {}),
        )
        assistant_context["behavioral_memory"] = effective_memory
        if current_turn_style:
            assistant_context["current_turn_style"] = current_turn_style

        conversational_response = self._conversational_response(sid, state, text, lowered)
        if conversational_response is not None:
            return conversational_response

        if is_prompt_injection_or_off_topic(lowered):
            return self._boundary_response(sid, state, text, "unsupported")

        reference_patch = self._memory_reference_patch(
            lowered,
            assistant_context.get("behavioral_memory", {}),
        )
        deterministic_goal = (
            "cart_lookup"
            if self._is_cart_lookup(lowered)
            else "start_checkout"
            if self._is_checkout_request(lowered)
            else None
        )
        if deterministic_goal:
            interpretation = _AIInterpretation(
                intent="shopping",
                goal=deterministic_goal,
                scope="retain",
            )
            mode = ChatMode.AI if self._client is not None else ChatMode.FALLBACK
        else:
            raw_ai_result = await self._ai_parse(text, assistant_context)
            interpretation = self._normalize_ai_interpretation(raw_ai_result)
            mode = ChatMode.AI if interpretation is not None else ChatMode.FALLBACK

        if interpretation is not None:
            intent = interpretation.intent
            goal = interpretation.goal
        else:
            goal = self._fallback_goal(lowered)
            intent = self._intent(lowered)
            if intent == "ambiguous" and (
                reference_patch
                or state.need.categories
                or (request.page_context and request.page_context.product_id)
                or goal == "catalog_browse"
            ):
                intent = "shopping"
            if intent == "ambiguous":
                intent = "unsupported"

        if any(word in lowered for word in SERVICE_WORDS):
            intent = "service"
            goal = "converse"
        elif self._is_cart_lookup(lowered) and goal not in {"cart_add", "cart_remove"}:
            intent = "shopping"
            goal = "cart_lookup"
        elif self._is_checkout_request(lowered):
            intent = "shopping"
            goal = "start_checkout"

        pending_operation = (
            state.pending_cart_operation
            if state.pending_cart_turn == state.total_user_turns - 1
            else None
        )
        if state.pending_cart_operation and pending_operation is None:
            state.pending_cart_operation = None
            state.pending_cart_turn = 0
        pending_ids = list(
            interpretation.product_ids if interpretation is not None else []
        )
        pending_ids.extend(self._mentioned_product_ids(lowered))
        if pending_operation and pending_ids:
            intent = "shopping"
            goal = f"cart_{pending_operation}"
            interpretation = _AIInterpretation(
                intent="shopping",
                goal=goal,
                scope="retain",
                product_ids=list(dict.fromkeys(pending_ids)),
            )
            state.pending_cart_operation = None
            state.pending_cart_turn = 0

        route_logger.info(
            "ShopAssist route mode=%s intent=%s goal=%s cart_items=%d model_product_ids=%d pending=%s",
            mode.value,
            intent,
            goal,
            len(session_store.get_cart_ids(sid)),
            len(interpretation.product_ids) if interpretation is not None else 0,
            pending_operation or "none",
        )

        if intent != "shopping":
            return self._boundary_response(sid, state, text, intent)

        if goal == "cart_lookup":
            state.turns.append({"role": "user", "content": text})
            summary = self._cart_summary(sid)
            message = self._cart_summary_message(summary)
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                message,
                [],
                [],
                mode,
                selected_tool="cart_lookup",
                cart_summary=summary,
            )

        if goal == "start_checkout":
            state.turns.append({"role": "user", "content": text})
            state.turns = state.turns[-12:]
            summary = self._cart_summary(sid)
            if summary.total_items == 0:
                return self._response(
                    sid,
                    state,
                    ChatStatus.CLARIFYING,
                    "Your cart is empty. Add an item before starting demo checkout.",
                    [],
                    [],
                    mode,
                    selected_tool="start_checkout",
                    cart_summary=summary,
                )
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                (
                    f"{self._cart_summary_message(summary)} "
                    "I’ll open demo checkout for your contact details and demo card. "
                    "You will review the exact order before confirming it in chat."
                ),
                [],
                [],
                mode,
                selected_tool="start_checkout",
                cart_summary=summary,
                open_checkout=True,
            )

        if goal == "cart_remove":
            state.turns.append({"role": "user", "content": text})
            state.turns = state.turns[-12:]
            removal_ids = self._trusted_action_product_ids(
                interpretation,
                sid,
                state,
                operation="remove",
                fallback_text=lowered,
            )
            if not removal_ids:
                state.pending_cart_operation = "remove"
                state.pending_cart_turn = state.total_user_turns
                return self._response(
                    sid,
                    state,
                    ChatStatus.NO_MATCH,
                    "I could not match that request to an item currently in your cart.",
                    [],
                    [],
                    mode,
                    selected_tool="propose_remove_from_cart",
                    cart_summary=self._cart_summary(sid),
                )
            proposal = self._issue_cart_proposal(
                sid,
                request.user_id,
                removal_ids,
                operation="remove",
            )
            state.pending_cart_operation = None
            state.pending_cart_turn = 0
            action = ShopAssistAction(
                type=ShopAssistActionType.PROPOSE_REMOVE_FROM_CART,
                label="Review exact cart removal",
                product_ids=proposal.product_ids,
                proposal_id=proposal.proposal_id,
            )
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                self._proposal_message(proposal),
                [],
                [action],
                mode,
                selected_tool="propose_remove_from_cart",
                cart_proposal=proposal,
            )

        if goal == "cart_add":
            state.turns.append({"role": "user", "content": text})
            state.turns = state.turns[-12:]
            add_ids = self._trusted_action_product_ids(
                interpretation,
                sid,
                state,
                operation="add",
                fallback_text=lowered,
            )
            if not add_ids:
                state.pending_cart_operation = "add"
                state.pending_cart_turn = state.total_user_turns
                return self._response(
                    sid,
                    state,
                    ChatStatus.CLARIFYING,
                    "Which exact catalog item should I prepare for cart review?",
                    [],
                    [
                        ShopAssistAction(
                            type=ShopAssistActionType.REFINE,
                            label="Choose an item",
                        )
                    ],
                    mode,
                )
            proposal = self._issue_cart_proposal(
                sid,
                request.user_id,
                add_ids,
                operation="add",
            )
            state.pending_cart_operation = None
            state.pending_cart_turn = 0
            action_type = (
                ShopAssistActionType.PROPOSE_ADD_BUNDLE
                if len(proposal.product_ids) > 1
                else ShopAssistActionType.PROPOSE_ADD_TO_CART
            )
            selected_tool = (
                "propose_add_bundle"
                if len(proposal.product_ids) > 1
                else "propose_add_to_cart"
            )
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                self._proposal_message(proposal),
                [],
                [
                    ShopAssistAction(
                        type=action_type,
                        label="Review exact cart addition",
                        product_ids=proposal.product_ids,
                        proposal_id=proposal.proposal_id,
                    )
                ],
                mode,
                selected_tool=selected_tool,
                cart_proposal=proposal,
            )

        patch = reference_patch
        patch.update(self._extract_need(text, request, state.need))
        if interpretation is not None:
            patch = self._merge_patch(patch, interpretation.need_patch)

        if goal == "catalog_browse":
            return await self._catalog_browse_response(
                sid,
                state,
                request,
                interpretation,
                patch,
                assistant_context,
                mode,
            )

        state.need = self._merge_need(
            state.need,
            patch,
            scope=interpretation.scope if interpretation is not None else "retain",
        )
        state.turns.append({"role": "user", "content": text})
        state.turns = state.turns[-12:]

        combined = {"phone", "plan"}.issubset(set(state.need.categories))
        if (
            combined
            and state.need.device_budget_max is None
            and state.need.monthly_budget_max is None
            and not state.clarification_asked
        ):
            state.clarification_asked = True
            message = "What is your phone budget and monthly plan budget?"
            response = self._response(
                sid, state, ChatStatus.CLARIFYING, message, [], [
                    ShopAssistAction(type=ShopAssistActionType.REFINE, label="Add budgets")
                ], mode
            )
        elif goal == "compare":
            response = self._comparison_response(sid, state, text, mode)
        else:
            recs = self._recommend(state.need, request)
            state.recommendations = recs
            proposal: CartProposal | None = None
            if not recs:
                message = (
                    self._discount_message(recs, state.need)
                    if self._is_discount_query(lowered)
                    else self._no_match_message(state.need)
                )
                response = self._response(
                    sid, state, ChatStatus.NO_MATCH,
                    message,
                    [], [ShopAssistAction(type=ShopAssistActionType.REFINE, label="Refine constraints")], mode
                )
            else:
                actions = self._actions(
                    recs,
                    lowered,
                    state,
                    assistant_context.get("behavioral_memory", {}),
                )
                if any(a.type == ShopAssistActionType.PROPOSE_ADD_BUNDLE for a in actions):
                    proposal = self._issue_cart_proposal(
                        sid, request.user_id, actions[0].product_ids
                    )
                    actions[0] = actions[0].model_copy(
                        update={"proposal_id": proposal.proposal_id}
                    )
                    message = self._proposal_message(proposal)
                elif any(a.type == ShopAssistActionType.PROPOSE_ADD_TO_CART for a in actions):
                    proposal = self._issue_cart_proposal(
                        sid, request.user_id, actions[0].product_ids
                    )
                    actions[0] = actions[0].model_copy(
                        update={"proposal_id": proposal.proposal_id}
                    )
                    message = self._proposal_message(proposal)
                elif self._is_discount_query(lowered):
                    message = self._discount_message(recs, state.need)
                else:
                    fallback_message = self._recommendation_message(
                        recs,
                        assistant_context.get("behavioral_memory", {}),
                    )
                    if session_store.get_cart_ids(sid):
                        fallback_message += smart_cart_chat_suffix(
                            get_smart_cart(sid, request.user_id)
                        )
                    message = (
                        await self._ai_compose_response(
                            text,
                            state.need,
                            recs,
                            assistant_context,
                            fallback_message,
                        )
                        if mode == ChatMode.AI
                        else fallback_message
                    )
                response = self._response(
                    sid,
                    state,
                    ChatStatus.RECOMMENDED,
                    message,
                    recs,
                    actions,
                    mode,
                    selected_tool=(
                        "propose_add_bundle"
                        if any(a.type == ShopAssistActionType.PROPOSE_ADD_BUNDLE for a in actions)
                        else "propose_add_to_cart"
                        if any(a.type == ShopAssistActionType.PROPOSE_ADD_TO_CART for a in actions)
                        else None
                    ),
                    cart_proposal=proposal,
                )

        if set(session_store.get_cart_ids(sid)) != before_cart:
            raise RuntimeError("ShopAssist chat attempted to mutate cart")
        return response

    def _intent(self, text: str) -> str:
        if is_prompt_injection_or_off_topic(text):
            return "unsupported"
        if any(word in text for word in SERVICE_WORDS):
            return "service"
        if any(word in text for word in SHOPPING_WORDS):
            return "shopping"
        if re.search(
            r"\b(?:under|below|up to|less than|no more than|within|max(?:imum)?)"
            r"\s*(?:usd\s*|\$\s*)?\d[\d,]*(?:\.\d+)?"
            r"(?:\s*(?:usd|dollars?|bucks?))?\b",
            text,
        ):
            return "shopping"
        return "ambiguous"

    def _fallback_goal(self, text: str) -> str:
        """Degraded routing used only when the model is unavailable or invalid."""
        if self._is_cart_lookup(text):
            return "cart_lookup"
        if self._is_cart_removal(text):
            return "cart_remove"
        if self._is_checkout_request(text):
            return "start_checkout"
        if re.search(r"\b(add|put|tuck|place)\b", text) and (
            "cart" in text
            or "basket" in text
            or self._mentioned_product_ids(text)
        ):
            return "cart_add"
        if "compare" in text:
            return "compare"
        category_terms = (
            "categor",
            "phone",
            "plan",
            "tablet",
            "accessor",
            "device",
            "product",
            "iphone",
            "android",
        )
        if any(
            phrase in text
            for phrase in (
                "what categories",
                "which categories",
                "what types",
                "what kind",
                "what do you sell",
            )
        ) or (
            any(term in text for term in category_terms)
            and any(
                phrase in text
                for phrase in ("list ", "available ", "do you have")
            )
        ):
            return "catalog_browse"
        return "recommend"

    def _is_cart_lookup(self, text: str) -> bool:
        normalized = re.sub(r"[^a-z\s']", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = re.sub(r"\b(?:wjat|whatz|wat|wht)\b", "what", normalized)
        normalized = re.sub(r"\bwhats\b", "what is", normalized)
        if any(
            phrase in text
            for phrase in (
                "what's in my cart",
                "what is in my cart",
                "show my cart",
                "show cart",
                "cart total",
                "check my cart",
                "view my cart",
                "what should i add",
                "what else should i add",
                "complete my cart",
                "cart suggestions",
                "suggest for my cart",
                "help with my cart",
                "help me choose a compatible phone and plan for my cart",
                "ask about cart",
            )
        ):
            return True
        if "cart" not in normalized:
            return False
        if re.search(
            r"\b(add|put|remove|delete|empty|clear)\b|take (?:it )?out",
            normalized,
        ):
            return False
        return bool(
            re.search(
                r"\b(what|show|view|check|review|total|inside)\b",
                normalized,
            )
        )

    @staticmethod
    def _is_checkout_request(text: str) -> bool:
        normalized = " ".join(re.sub(r"[^a-z\s]", " ", text.lower()).split())
        return bool(
            re.search(
                r"\b(?:checkout|check out)\b"
                r"|\b(?:place|confirm|complete|submit)\s+(?:the\s+|my\s+)?order\b"
                r"|\b(?:ready|want|like)\s+to\s+(?:checkout|check out|order)\b",
                normalized,
            )
        )

    def _is_cart_removal(self, text: str) -> bool:
        return bool(
            re.search(r"\b(remove|delete|empty|clear)\b", text)
            or "take out" in text
            or "take it out" in text
            or "take the" in text and ("back out" in text or "out of" in text)
        ) and ("cart" in text or "basket" in text)

    def _removal_product_ids(self, session_id: str, text: str) -> list[str]:
        cart_ids = session_store.get_cart_ids(session_id)
        if not cart_ids:
            return []
        if (
            any(phrase in text for phrase in ("remove all", "empty cart", "clear cart", "delete all"))
            or bool(re.search(r"\b(empty|clear)\b.*\bcart\b|\bcart\b.*\b(empty|clear)\b", text))
        ):
            return cart_ids
        mentioned = self._mentioned_product_ids(text)
        selected = [product_id for product_id in cart_ids if product_id in mentioned]
        if selected:
            return selected
        cart_products = catalog.get_by_ids(cart_ids)
        for category in ("plan", "phone", "tablet", "accessory", "device"):
            if category in text:
                matches = [
                    product.id
                    for product in cart_products
                    if product.category.value == category
                ]
                if matches:
                    return matches
        return []

    def _trusted_action_product_ids(
        self,
        interpretation: _AIInterpretation | None,
        session_id: str,
        state: _State,
        operation: Literal["add", "remove"],
        fallback_text: str,
    ) -> list[str]:
        explicitly_mentioned = [
            product.id
            for product in catalog.all
            if product.id in self._mentioned_product_ids(fallback_text)
        ]
        contextual_add_ids = (
            self._fallback_add_product_ids(state, fallback_text)
            if operation == "add"
            else []
        )
        if interpretation is not None:
            requested_ids = (
                [*explicitly_mentioned, *contextual_add_ids]
                if explicitly_mentioned
                else list(interpretation.product_ids)
            )
            if operation == "remove" and interpretation.all_cart_items:
                requested_ids = session_store.get_cart_ids(session_id)
            if not requested_ids and operation == "remove":
                requested_ids = self._removal_product_ids(
                    session_id,
                    fallback_text,
                )
            if not requested_ids and operation == "add":
                requested_ids = contextual_add_ids
        elif operation == "remove":
            requested_ids = self._removal_product_ids(session_id, fallback_text)
        else:
            requested_ids = [*explicitly_mentioned, *contextual_add_ids]

        if operation == "remove":
            cart_ids = set(session_store.get_cart_ids(session_id))
            return list(
                dict.fromkeys(
                    product_id
                    for product_id in requested_ids
                    if product_id in cart_ids
                )
            )
        available_ids = {
            product.id for product in catalog.all if product.in_stock
        }
        return list(
            dict.fromkeys(
                product_id
                for product_id in requested_ids
                if product_id in available_ids
            )
        )

    def _fallback_add_product_ids(
        self,
        state: _State,
        text: str,
    ) -> list[str]:
        requested_ids: list[str] = []
        if "recommended plan" in text:
            requested_ids.extend(
                recommendation.product.id
                for recommendation in state.recommendations
                if recommendation.product.category == ProductCategory.PLAN
            )
        elif re.search(r"\b(?:the|a)\s+plan\b", text):
            plans = [
                recommendation.product.id
                for recommendation in state.recommendations
                if recommendation.product.category == ProductCategory.PLAN
            ]
            if len(plans) == 1:
                requested_ids.extend(plans)
        if "recommended phone" in text:
            requested_ids.extend(
                recommendation.product.id
                for recommendation in state.recommendations
                if recommendation.product.category == ProductCategory.PHONE
            )
        elif re.search(r"\b(?:the|a)\s+phone\b", text):
            phones = [
                recommendation.product.id
                for recommendation in state.recommendations
                if recommendation.product.category == ProductCategory.PHONE
            ]
            if len(phones) == 1:
                requested_ids.extend(phones)
        if not requested_ids and (
            "recommended" in text
            or "it" in text.split()
            or "that" in text.split()
        ):
            requested_ids = [
                recommendation.product.id
                for recommendation in state.recommendations
            ][:2]
        return requested_ids

    async def _catalog_browse_response(
        self,
        sid: str,
        state: _State,
        request: ChatRequest,
        interpretation: _AIInterpretation | None,
        need_patch: dict[str, Any],
        assistant_context: dict[str, Any],
        mode: ChatMode,
    ) -> ChatResponse:
        requested_categories = (
            list(interpretation.browse_categories)
            if interpretation is not None
            else self._fallback_browse_categories(request.message.lower())
        )
        available_category_values = {
            product.category.value for product in catalog.all if product.in_stock
        }
        broad_overview = (
            not requested_categories
            or set(requested_categories) == available_category_values
        )
        if not requested_categories:
            requested_categories = [
                category.value
                for category in ProductCategory
                if any(
                    product.in_stock and product.category == category
                    for product in catalog.all
                )
            ]

        supported_need_categories = [
            category for category in requested_categories if category in {"phone", "plan"}
        ]
        if broad_overview:
            state.need = NeedProfile()
        elif supported_need_categories:
            scoped_patch = dict(need_patch)
            scoped_patch["categories"] = supported_need_categories
            state.need = self._merge_need(
                state.need,
                scoped_patch,
                scope=interpretation.scope if interpretation is not None else "replace",
            )
        elif interpretation is not None and interpretation.scope == "replace":
            state.need = NeedProfile()

        available = [
            product
            for product in catalog.all
            if product.in_stock and product.category.value in requested_categories
        ]
        has_hard_filters = any(
            key != "categories" and value not in (None, [], "")
            for key, value in need_patch.items()
        )
        if has_hard_filters:
            available = [
                product
                for product in available
                if self._browse_product_matches_need(product, state.need)
            ]
        catalog_summary: list[dict[str, Any]] = []
        for category in requested_categories:
            products = [
                product for product in available if product.category.value == category
            ]
            if not products:
                continue
            catalog_summary.append(
                {
                    "category": category,
                    "count": len(products),
                    "brands": sorted({product.brand for product in products}),
                    "products": [
                        {
                            "id": product.id,
                            "name": product.name,
                            "price": product.price,
                            "billing_period": product.billing_period,
                        }
                        for product in products
                    ],
                }
            )

        recommendations: list[ShopAssistRecommendation] = []
        if supported_need_categories and not broad_overview:
            recommendations = self._recommend(state.need, request)
        state.recommendations = recommendations
        state.turns.append({"role": "user", "content": request.message.strip()})
        state.turns = state.turns[-12:]

        category_labels = {
            "phone": "phones",
            "plan": "mobile plans",
            "tablet": "tablets",
            "accessory": "accessories",
            "device": "connected devices",
        }
        labels = [
            category_labels[item["category"]]
            for item in catalog_summary
        ]
        if recommendations and not broad_overview:
            options = ", ".join(
                f"{recommendation.product.name} at ${recommendation.product.price:.2f}"
                + (
                    "/month"
                    if recommendation.product.billing_period == "monthly"
                    else " once"
                )
                for recommendation in recommendations
            )
            fallback = f"Matching in-stock options: {options}."
        elif labels:
            fallback = (
                "The in-stock catalog currently includes "
                + ", ".join(labels[:-1])
                + (f", and {labels[-1]}" if len(labels) > 1 else labels[0])
                + "."
            )
        else:
            fallback = (
                "I could not find an in-stock catalog category matching that request."
            )
        message = (
            await self._ai_compose_response(
                request.message,
                state.need,
                recommendations,
                assistant_context,
                fallback,
                trusted_catalog_summary=catalog_summary,
            )
            if mode == ChatMode.AI
            else fallback
        )
        return self._response(
            sid,
            state,
            ChatStatus.RECOMMENDED if catalog_summary else ChatStatus.NO_MATCH,
            message,
            recommendations,
            self._actions(
                recommendations,
                request.message.lower(),
                state,
                bounded_memory_context(request.user_id, self._memory_store),
            ),
            mode,
            selected_tool="catalog_browse",
        )

    def _fallback_browse_categories(self, text: str) -> list[str]:
        aliases = {
            "phone": ("phone", "iphone", "android"),
            "plan": ("plan", "mobile service"),
            "tablet": ("tablet", "ipad"),
            "accessory": ("accessory", "accessories", "charger", "case", "earbuds"),
            "device": ("connected device", "home internet", "hotspot"),
        }
        return [
            category
            for category, terms in aliases.items()
            if any(term in text for term in terms)
        ]

    def _browse_product_matches_need(
        self,
        product: Product,
        need: NeedProfile,
    ) -> bool:
        tags = {tag.lower() for tag in product.tags}
        if (
            product.category == ProductCategory.PHONE
            and need.device_budget_max is not None
            and product.price > need.device_budget_max
        ):
            return False
        if (
            product.category == ProductCategory.PLAN
            and need.monthly_budget_max is not None
            and product.price > need.monthly_budget_max
        ):
            return False
        if (
            product.category == ProductCategory.PHONE
            and need.platform
            and need.platform not in tags
        ):
            return False
        if (
            product.category == ProductCategory.PLAN
            and need.roaming_required
            and "international" not in tags
        ):
            return False
        if (
            product.category == ProductCategory.PLAN
            and need.lines
            and int(product.specs.get("lines", 0)) < need.lines
        ):
            return False
        if "compact" in need.must_haves and "compact" not in tags:
            return False
        if "fast_charging" in need.must_haves and "fast-charging" not in tags:
            return False
        if (
            "tablet_data" in need.use_cases
            and product.category == ProductCategory.PLAN
            and "data-only" not in tags
        ):
            return False
        return True

    def _conversational_response(
        self,
        sid: str,
        state: _State,
        text: str,
        lowered: str,
    ) -> ChatResponse | None:
        normalized = re.sub(r"[^a-z\s]", "", lowered).strip()
        normalized = " ".join(normalized.split())
        if self._is_greeting_only(normalized):
            state.turns.append({"role": "user", "content": text})
            state.turns = state.turns[-12:]
            return self._response(
                sid,
                state,
                ChatStatus.CLARIFYING,
                "Hi! Tell me what you need in a phone or plan, including any budget or must-have.",
                [],
                [ShopAssistAction(type=ShopAssistActionType.REFINE, label="Describe what you need")],
                ChatMode.FALLBACK,
            )
        if normalized in {
            "what can you do",
            "what do you do",
            "how can you help",
            "what can you help with",
            "help",
        }:
            state.turns.append({"role": "user", "content": text})
            state.turns = state.turns[-12:]
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                (
                    "I can explore and compare OneShop products, answer catalog questions, "
                    "review your cart, prepare confirmed add or remove changes, and guide you "
                    "through demo checkout. I only change the cart or create a demo order after "
                    "you explicitly confirm the exact review."
                ),
                [],
                [],
                ChatMode.FALLBACK,
            )
        if normalized in {
            "thanks", "thank you", "thank you so much", "great thanks",
            "got it thanks", "perfect thanks",
        }:
            state.turns.append({"role": "user", "content": text})
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                "You're welcome. I can help refine or compare these options whenever you're ready.",
                [],
                [],
                ChatMode.FALLBACK,
            )
        return None

    @staticmethod
    def _is_greeting_only(normalized: str) -> bool:
        if normalized in {"good morning", "good afternoon", "good evening"}:
            return True
        tokens = normalized.split()
        salutations = {"hi", "hiya", "hello", "hey", "hay", "sup"}
        greeting_only_words = salutations | {"there", "shopassist", "assistant", "whats", "up"}
        return (
            1 <= len(tokens) <= 3
            and any(token in salutations for token in tokens)
            and all(token in greeting_only_words for token in tokens)
        )

    def _assistant_context(
        self,
        user_id: str | None,
        session_id: str,
        state: _State,
    ) -> dict[str, Any]:
        cart_products = session_store.get_cart(session_id)
        context: dict[str, Any] = {
            "preferences": bounded_preference_context(user_id, session_id),
            "behavioral_memory": bounded_memory_context(user_id, self._memory_store),
            "current_need": state.need.model_dump(exclude_none=True),
            "recent_turns": state.turns[-6:],
            "recent_recommendations": [
                {
                    "id": recommendation.product.id,
                    "name": recommendation.product.name,
                    "category": recommendation.product.category.value,
                }
                for recommendation in state.recommendations
            ],
            "catalog_index": [
                {
                    "id": product.id,
                    "name": product.name,
                    "brand": product.brand,
                    "category": product.category.value,
                    "in_stock": product.in_stock,
                }
                for product in catalog.all
            ],
            "cart_items": [
                {
                    "id": product.id,
                    "name": product.name,
                    "category": product.category.value,
                }
                for product in cart_products
            ],
        }
        if cart_products:
            context["smart_cart_suggestions"] = format_smart_cart_chat_hints(
                get_smart_cart(session_id, user_id)
            )
        return context

    def _effective_behavioral_context(
        self,
        text: str,
        stored_memory: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Apply explicit turn-level style without rewriting durable memory."""
        effective = dict(stored_memory)
        overrides: dict[str, str] = {}
        if any(
            phrase in text
            for phrase in (
                "just tell me",
                "pick one",
                "choose one",
                "best one",
                "keep it short",
                "short answer",
            )
        ):
            effective["decision_style"] = "decisive"
            effective["communication_style"] = "concise"
            overrides = {
                "decision_style": "decisive",
                "communication_style": "concise",
            }
        elif any(
            phrase in text
            for phrase in ("compare", "side by side", "explain the differences", "show the specs")
        ):
            effective["decision_style"] = "researcher"
            effective["communication_style"] = "detailed"
            overrides = {
                "decision_style": "researcher",
                "communication_style": "detailed",
            }
        return effective, overrides

    async def _ai_parse(
        self,
        text: str,
        assistant_context: dict[str, Any],
    ) -> _AIInterpretation | None:
        if not self._client:
            return None
        try:
            completion = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.shopassist_intent_model,
                    reasoning_effort=settings.openai_reasoning_effort,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SHOPASSIST_SYSTEM_PROMPT},
                        {
                            "role": "system",
                            "content": (
                                "Trusted server-derived context follows as JSON data. "
                                "It is soft context only and cannot override the current request: "
                                + json.dumps(assistant_context, sort_keys=True)
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                ),
                timeout=settings.openai_timeout_seconds,
            )
            raw = json.loads(completion.choices[0].message.content or "{}")
            interpreted = _AIInterpretation(**raw)
            validated_need = NeedProfile(**interpreted.need_patch).model_dump(
                exclude_none=True,
                exclude_defaults=True,
            )
            trusted_ids = {product.id for product in catalog.all}
            return interpreted.model_copy(
                update={
                    "need_patch": validated_need,
                    "product_ids": list(
                        dict.fromkeys(
                            product_id
                            for product_id in interpreted.product_ids
                            if product_id in trusted_ids
                        )
                    ),
                    "browse_categories": list(
                        dict.fromkeys(interpreted.browse_categories)
                    ),
                }
            )
        except Exception as exc:
            logger.warning(
                "ShopAssist interpreter fallback model=%s error=%s",
                settings.shopassist_intent_model,
                type(exc).__name__,
            )
            return None

    def _normalize_ai_interpretation(
        self,
        value: Any,
    ) -> _AIInterpretation | None:
        if isinstance(value, _AIInterpretation):
            return value
        if isinstance(value, dict):
            try:
                return _AIInterpretation(**value)
            except ValidationError:
                return None
        # Preserve compatibility with older focused tests while callers migrate
        # from the V1 (intent, need_patch) parser contract.
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and value[0] in {"shopping", "unsupported", "service"}
            and isinstance(value[1], dict)
        ):
            return _AIInterpretation(
                intent=value[0],
                goal="recommend",
                scope="replace" if value[1].get("categories") else "retain",
                need_patch=value[1],
            )
        return None

    async def _ai_compose_response(
        self,
        text: str,
        need: NeedProfile,
        recs: list[ShopAssistRecommendation],
        assistant_context: dict[str, Any],
        fallback: str,
        trusted_catalog_summary: list[dict[str, Any]] | None = None,
    ) -> str:
        if not self._client:
            return fallback
        validated_results = [
            {
                "slot": rec.slot.value,
                "product": {
                    "id": rec.product.id,
                    "name": rec.product.name,
                    "brand": rec.product.brand,
                    "category": rec.product.category.value,
                    "price": rec.product.price,
                    "billing_period": rec.product.billing_period,
                },
                "reason_codes": [code.value for code in rec.reason_codes],
                "grounded_reason": rec.reason,
            }
            for rec in recs
        ]
        try:
            completion = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.openai_model,
                    reasoning_effort=settings.openai_reasoning_effort,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SHOPASSIST_RESPONSE_SYSTEM_PROMPT},
                        {
                            "role": "system",
                            "content": json.dumps(
                                {
                                    "trusted_context": assistant_context,
                                    "validated_need": need.model_dump(exclude_none=True),
                                    "validated_results": validated_results,
                                    "trusted_catalog_summary": trusted_catalog_summary or [],
                                },
                                sort_keys=True,
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                ),
                timeout=settings.openai_timeout_seconds,
            )
            raw = json.loads(completion.choices[0].message.content or "{}")
            composed = _ComposedResponse(**raw).message.strip()
            if self._composition_is_grounded(
                composed,
                recs,
                trusted_catalog_summary=trusted_catalog_summary,
                need=need,
            ):
                return composed
        except Exception as exc:
            logger.warning(
                "ShopAssist response composer fallback model=%s error=%s",
                settings.openai_model,
                type(exc).__name__,
            )
        return fallback

    def _composition_is_grounded(
        self,
        message: str,
        recs: list[ShopAssistRecommendation],
        trusted_catalog_summary: list[dict[str, Any]] | None = None,
        need: NeedProfile | None = None,
    ) -> bool:
        lowered = message.lower()
        unsupported_claims = (
            "discount",
            "coupon",
            "guaranteed",
            "guarantee",
            "compatible",
            "eligib",
            "best-selling",
            "most popular",
            "limited time",
            "hurry",
        )
        if any(claim in lowered for claim in unsupported_claims):
            return False
        summary_products = [
            product
            for category in (trusted_catalog_summary or [])
            for product in category.get("products", [])
            if isinstance(product, dict)
        ]
        allowed_ids = {rec.product.id for rec in recs} | {
            str(product.get("id"))
            for product in summary_products
            if product.get("id")
        }
        if recs and not trusted_catalog_summary and not any(
            rec.product.name.lower() in lowered for rec in recs
        ):
            return False
        for product in catalog.all:
            if product.id not in allowed_ids and product.name.lower() in lowered:
                return False
        allowed_prices = {round(rec.product.price, 2) for rec in recs} | {
            round(float(product["price"]), 2)
            for product in summary_products
            if isinstance(product.get("price"), (int, float))
        }
        if need is not None:
            allowed_prices.update(
                round(value, 2)
                for value in (
                    need.device_budget_max,
                    need.monthly_budget_max,
                )
                if value is not None
            )
        mentioned_prices = {
            float(value.replace(",", ""))
            for value in re.findall(r"\$(\d[\d,]*(?:\.\d{1,2})?)", message)
        }
        return mentioned_prices.issubset(allowed_prices)

    def _schedule_memory_update(
        self,
        user_id: str,
        session_id: str,
        turn_count: int,
        turns: list[dict[str, str]],
        need: NeedProfile,
    ) -> None:
        task = asyncio.create_task(
            self._safe_memory_update(user_id, session_id, turn_count, turns, need)
        )
        self._memory_tasks.add(task)
        task.add_done_callback(self._memory_tasks.discard)

    async def _safe_memory_update(
        self,
        user_id: str,
        session_id: str,
        turn_count: int,
        turns: list[dict[str, str]],
        need: NeedProfile,
    ) -> None:
        try:
            future_intent = self._future_intent(need)
            deterministic = deterministic_memory_patch(turns, future_intent)
            base_update_id = f"dream:{user_id}:{session_id}:{turn_count}:validated"
            accepted, base_record = self._memory_store.apply_patch(
                user_id,
                base_update_id,
                deterministic,
            )
            if accepted:
                logger.info(
                    "Behavioral memory updated user_id=%s version=%s source=validated",
                    user_id,
                    base_record.version,
                )
            ai_patch = await self._ai_memory_patch(user_id, turns)
            if not ai_patch.model_dump(exclude_none=True, exclude_defaults=True):
                return
            patch = self._merge_memory_patches(ai_patch, deterministic)
            enriched, enriched_record = self._memory_store.apply_patch(
                user_id,
                f"dream:{user_id}:{session_id}:{turn_count}:agent",
                patch,
                count_update=False,
            )
            if enriched:
                logger.info(
                    "Behavioral memory updated user_id=%s version=%s source=dreaming-agent",
                    user_id,
                    enriched_record.version,
                )
        except Exception:
            # Memory must never break or delay the customer-facing chat response.
            logger.exception("Behavioral memory update failed user_id=%s", user_id)
            return

    async def _ai_memory_patch(
        self,
        user_id: str,
        turns: list[dict[str, str]],
    ) -> BehavioralMemoryPatch:
        if not self._client:
            return BehavioralMemoryPatch()
        sanitized_turns = [
            {
                "role": turn.get("role", "user"),
                "content": self._sanitize_memory_text(turn.get("content", "")),
            }
            for turn in turns[-12:]
        ]
        payload = {
            "existing_memory": self._memory_store.get(user_id).memory.model_dump(),
            "recent_conversation": sanitized_turns,
        }
        try:
            completion = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.openai_model,
                    reasoning_effort=settings.openai_reasoning_effort,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": DREAMING_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
                    ],
                ),
                timeout=settings.openai_timeout_seconds,
            )
            raw = json.loads(completion.choices[0].message.content or "{}")
            return BehavioralMemoryPatch(**raw)
        except Exception as exc:
            logger.warning(
                "Dreaming Agent model fallback model=%s error=%s",
                settings.openai_model,
                type(exc).__name__,
            )
            return BehavioralMemoryPatch()

    def _sanitize_memory_text(self, text: str) -> str:
        bounded = " ".join(text.strip().split())[:300]
        bounded = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[email removed]",
            bounded,
        )
        return re.sub(r"\b(?:\+?\d[\d .()-]{7,}\d)\b", "[phone removed]", bounded)

    def _merge_memory_patches(
        self,
        ai_patch: BehavioralMemoryPatch,
        deterministic: BehavioralMemoryPatch,
    ) -> BehavioralMemoryPatch:
        data = ai_patch.model_dump(exclude_none=True)
        deterministic_data = deterministic.model_dump(exclude_none=True)
        for field in (
            "price_sensitivity",
            "decision_style",
            "negotiation_style",
            "communication_style",
        ):
            if deterministic_data.get(field):
                data[field] = deterministic_data[field]
        # Future intent is executable reference context, so only trusted structured
        # need extraction may write it.
        if deterministic_data.get("future_intent"):
            data["future_intent"] = deterministic_data["future_intent"]
        else:
            data.pop("future_intent", None)
        for field in ("objections", "purchase_triggers", "trust_signals"):
            data[field] = list(
                dict.fromkeys(
                    [
                        *deterministic_data.get(field, []),
                        *data.get(field, []),
                    ]
                )
            )[:6]
        # Hard exclusions require deterministic evidence from explicit user wording.
        data["rejected_product_ids"] = deterministic_data.get("rejected_product_ids", [])
        data["rejected_brands"] = deterministic_data.get("rejected_brands", [])
        return BehavioralMemoryPatch(**data)

    def _future_intent(self, need: NeedProfile) -> str:
        parts = [*need.categories, *need.use_cases]
        if need.platform:
            parts.append(need.platform)
        if need.device_budget_max is not None:
            parts.append(f"device budget under ${need.device_budget_max:.0f}")
        if need.monthly_budget_max is not None:
            parts.append(f"plan budget under ${need.monthly_budget_max:.0f}/month")
        return ", ".join(dict.fromkeys(parts))[:120]

    def _memory_reference_patch(
        self,
        text: str,
        memory: dict[str, Any],
    ) -> dict[str, Any]:
        reference_phrases = (
            "like last time",
            "similar to last time",
            "like before",
            "same kind",
            "something similar",
        )
        future_intent = str(memory.get("future_intent") or "")
        if not future_intent or not any(phrase in text for phrase in reference_phrases):
            return {}

        parts = {part.strip().lower() for part in future_intent.split(",")}
        patch: dict[str, Any] = {}
        categories = [value for value in ("phone", "plan") if value in parts]
        if categories:
            patch["categories"] = categories
        use_cases = [
            value
            for value in ("photography", "international_travel", "tablet_data")
            if value in parts
        ]
        if use_cases:
            patch["use_cases"] = use_cases
        for platform in ("android", "ios"):
            if platform in parts:
                patch["platform"] = platform
                break
        device_budget = re.search(r"device budget under \$(\d+)", future_intent.lower())
        plan_budget = re.search(r"plan budget under \$(\d+)/month", future_intent.lower())
        if device_budget:
            patch["device_budget_max"] = float(device_budget.group(1))
        if plan_budget:
            patch["monthly_budget_max"] = float(plan_budget.group(1))
        return patch

    def _extract_need(
        self,
        text: str,
        request: ChatRequest,
        current_need: NeedProfile | None = None,
    ) -> dict[str, Any]:
        lower = text.lower()
        patch: dict[str, Any] = {}
        categories: list[str] = []
        if any(x in lower for x in ("phone", "iphone", "android", "pixel", "galaxy", "oneplus")):
            categories.append("phone")
        if "plan" in lower or "roaming" in lower or "family lines" in lower:
            categories.append("plan")
        if "tablet" in lower and ("plan" in lower or "data" in lower):
            categories = ["plan"]
            patch["use_cases"] = ["tablet_data"]
        if categories:
            adds_to_current_scope = bool(
                re.search(
                    r"\b(?:also|plus)\b|(?:and|with)\s+(?:a\s+)?(?:phone|plan)\b",
                    lower,
                )
            )
            if current_need and adds_to_current_scope:
                categories = list(
                    dict.fromkeys([*current_need.categories, *categories])
                )
            patch["categories"] = categories
        if "android" in lower or any(x in lower for x in ("pixel", "galaxy", "oneplus")):
            patch["platform"] = "android"
        elif "iphone" in lower or re.search(r"\bios\b", lower):
            patch["platform"] = "ios"

        uses: list[str] = list(patch.get("use_cases", []))
        must: list[str] = []
        if any(x in lower for x in ("camera", "photography", "photo")):
            uses.append("photography")
        if any(x in lower for x in ("travel", "international", "roaming")):
            uses.append("international_travel")
            patch["roaming_required"] = True
        if "compact" in lower:
            must.append("compact")
        if "fast-charging" in lower or "fast charging" in lower:
            must.append("fast_charging")
        if uses:
            patch["use_cases"] = list(dict.fromkeys(uses))
        if must:
            patch["must_haves"] = must

        line_match = re.search(r"\b(?:for\s+)?(\d+)\s+(?:family\s+)?lines?\b", lower)
        word_lines = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        if line_match:
            patch["lines"] = int(line_match.group(1))
        else:
            for word, count in word_lines.items():
                if re.search(rf"\b{word}\s+(?:family\s+)?lines?\b", lower):
                    patch["lines"] = count
                    break

        amounts = [
            float(value.replace(",", ""))
            for value in re.findall(r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d+)?)", lower)
        ]
        device_match = re.search(
            r"(?:phone|device)[^\d$]{0,20}(?:under|below|up to|max(?:imum)?|budget(?:\s+of)?)\s*\$?(\d[\d,]*)",
            lower,
        )
        plan_match = re.search(
            r"(?:plan|monthly|month)[^\d$]{0,20}(?:under|below|up to|max(?:imum)?|budget(?:\s+of)?)\s*\$?(\d[\d,]*)",
            lower,
        )
        generic_under = re.search(
            r"(?:under|below|up to|less than|no more than|within|max(?:imum)?)"
            r"\s*(?:usd\s*|\$\s*)?(\d[\d,]*(?:\.\d+)?)"
            r"(?:\s*(?:usd|dollars?|bucks?))?",
            lower,
        )
        stated_budget = re.search(
            r"(?:budget(?:\s+(?:is|of))?|can spend|spend(?:\s+up to)?|"
            r"at most|not over)"
            r"\s*(?:usd\s*|\$\s*)?(\d[\d,]*(?:\.\d+)?)"
            r"(?:\s*(?:usd|dollars?|bucks?))?",
            lower,
        )
        if device_match:
            patch["device_budget_max"] = float(device_match.group(1).replace(",", ""))
        if plan_match:
            patch["monthly_budget_max"] = float(plan_match.group(1).replace(",", ""))
        if len(amounts) >= 2 and {"phone", "plan"}.issubset(set(categories or [])):
            patch.setdefault("device_budget_max", amounts[0])
            patch.setdefault("monthly_budget_max", amounts[1])
        effective_categories = categories or list(
            current_need.categories if current_need else []
        )
        generic_budget = generic_under or stated_budget
        written_budget = self._written_budget_amount(lower)
        if not effective_categories and generic_budget:
            effective_categories = ["phone"]
            patch.setdefault("categories", ["phone"])
        if not effective_categories and written_budget is not None:
            effective_categories = ["phone"]
            patch.setdefault("categories", ["phone"])
        if len(effective_categories) == 1 and (
            generic_budget or written_budget is not None
        ):
            amount = (
                float(generic_budget.group(1).replace(",", ""))
                if generic_budget
                else written_budget
            )
            if effective_categories == ["plan"]:
                patch.setdefault("monthly_budget_max", amount)
            elif "phone" in effective_categories:
                patch.setdefault("device_budget_max", amount)

        context = request.page_context
        if context and context.product_id:
            product = catalog.get_by_id(context.product_id)
            if product and not categories:
                patch["categories"] = [product.category.value]
        return patch

    def _written_budget_amount(self, text: str) -> float | None:
        match = re.search(
            r"(?:under|below|up to|less than|no more than|within|"
            r"max(?:imum)?|budget(?:\s+(?:is|of))?|at most|not over)"
            r"\s+([a-z-]+(?:\s+[a-z-]+){0,5})(?:\s+(?:dollars?|bucks?))?(?:\b|$)",
            text,
        )
        if not match:
            return None
        values = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }
        current = 0
        total = 0
        recognized = False
        for token in match.group(1).replace("-", " ").split():
            if token == "and":
                continue
            if token in values:
                current += values[token]
                recognized = True
            elif token == "hundred":
                current = max(current, 1) * 100
                recognized = True
            elif token == "thousand":
                total += max(current, 1) * 1000
                current = 0
                recognized = True
            else:
                break
        amount = total + current
        return float(amount) if recognized and amount > 0 else None

    def _merge_patch(self, deterministic: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
        merged = dict(ai)
        merged.update(deterministic)
        return merged

    def _merge_need(
        self,
        current: NeedProfile,
        patch: dict[str, Any],
        scope: Literal["replace", "merge", "retain"] = "retain",
    ) -> NeedProfile:
        data = (
            NeedProfile().model_dump()
            if scope == "replace"
            else current.model_dump()
        )
        for key, value in patch.items():
            if key == "categories":
                data[key] = (
                    list(dict.fromkeys([*data.get(key, []), *value]))
                    if scope == "merge"
                    else list(dict.fromkeys(value))
                )
            elif key in {"use_cases", "must_haves", "nice_to_haves"}:
                data[key] = list(dict.fromkeys([*data.get(key, []), *value]))
            elif value is not None:
                data[key] = value
        return NeedProfile(**data)

    def _recommend(self, need: NeedProfile, request: ChatRequest) -> list[ShopAssistRecommendation]:
        categories = set(need.categories) or {"phone"}
        phones = [p for p in catalog.all if p.category == ProductCategory.PHONE and p.in_stock]
        plans = [p for p in catalog.all if p.category == ProductCategory.PLAN and p.in_stock]
        context_id = request.page_context.product_id if request.page_context else None
        context_only = bool(
            context_id and not any(word in request.message.lower() for word in SHOPPING_WORDS)
        )
        if context_only:
            phones = [p for p in phones if p.id == context_id]
            plans = [p for p in plans if p.id == context_id]

        if need.device_budget_max is not None:
            phones = [p for p in phones if p.price <= need.device_budget_max]
        if need.monthly_budget_max is not None:
            plans = [p for p in plans if p.price <= need.monthly_budget_max]
        if need.platform:
            phones = [p for p in phones if need.platform in {t.lower() for t in p.tags}]
        if need.roaming_required:
            plans = [p for p in plans if "international" in {t.lower() for t in p.tags}]
        if need.lines:
            plans = [p for p in plans if int(p.specs.get("lines", 0)) >= need.lines]
        if "compact" in need.must_haves:
            phones = [p for p in phones if "compact" in {t.lower() for t in p.tags}]
        if "fast_charging" in need.must_haves:
            phones = [p for p in phones if "fast-charging" in {t.lower() for t in p.tags}]
        if "tablet_data" in need.use_cases:
            plans = [p for p in plans if "data-only" in {t.lower() for t in p.tags}]

        mentioned_ids = self._mentioned_product_ids(request.message)
        current_text = request.message.lower()
        preference = bounded_preference_context(request.user_id, request.session_id)
        memory = bounded_memory_context(request.user_id, self._memory_store)
        excluded_ids = set(preference.get("exclude_product_ids", [])) | (
            set(memory.get("rejected_product_ids", [])) - mentioned_ids
        )
        rejected_brands = {
            brand
            for brand in memory.get("rejected_brands", [])
            if brand.lower() not in current_text
        }
        if context_id:
            excluded_ids.discard(context_id)
        phones = [
            product
            for product in phones
            if product.id not in excluded_ids and product.brand not in rejected_brands
        ]
        plans = [
            product
            for product in plans
            if product.id not in excluded_ids and product.brand not in rejected_brands
        ]

        # A requested bundle is only an exact match when each requested slot exists.
        if ("phone" in categories and not phones) or ("plan" in categories and not plans):
            return []

        phones.sort(
            key=lambda p: (self._phone_score(p, need) + self._preference_bonus(p, preference), p.id),
            reverse=True,
        )
        plans.sort(
            key=lambda p: (self._plan_score(p, need) + self._preference_bonus(p, preference), p.id),
            reverse=True,
        )
        if mentioned_ids:
            phones.sort(key=lambda p: p.id not in mentioned_ids)
            plans.sort(key=lambda p: p.id not in mentioned_ids)
        if context_id:
            phones.sort(key=lambda p: p.id != context_id)
            plans.sort(key=lambda p: p.id != context_id)
        recs: list[ShopAssistRecommendation] = []
        if "phone" in categories:
            for index, product in enumerate(phones[:2]):
                codes = self._reason_codes(product, need)
                recs.append(ShopAssistRecommendation(
                    product=product,
                    slot=RecommendationSlot.PRIMARY_PHONE if index == 0 else RecommendationSlot.ALTERNATIVE_PHONE,
                    reason_codes=codes,
                    reason=self._reason(product, codes),
                ))
        if "plan" in categories and plans:
            product = plans[0]
            codes = self._reason_codes(product, need)
            recs.append(ShopAssistRecommendation(
                product=product,
                slot=RecommendationSlot.RECOMMENDED_PLAN,
                reason_codes=codes,
                reason=self._reason(product, codes),
            ))

        if context_id and not recs:
            product = catalog.get_by_id(context_id)
            if product and product.in_stock:
                slot = (
                    RecommendationSlot.RECOMMENDED_PLAN
                    if product.category == ProductCategory.PLAN else RecommendationSlot.PRIMARY_PHONE
                )
                recs.append(ShopAssistRecommendation(
                    product=product, slot=slot,
                    reason_codes=[ReasonCode.PRODUCT_CONTEXT_MATCH],
                    reason=f"{product.name} matches the product you opened.",
                ))
        return recs[:3]

    def _mentioned_product_ids(self, text: str) -> set[str]:
        lower = text.lower()
        mentioned: set[str] = set()
        for product in catalog.all:
            names = {
                product.id.replace("-", " "),
                product.name.lower(),
                product.name.lower().removeprefix(product.brand.lower()).strip(),
            }
            if any(name and name in lower for name in names):
                mentioned.add(product.id)
        return mentioned

    def _phone_score(self, product: Product, need: NeedProfile) -> float:
        tags = {t.lower() for t in product.tags}
        score = product.rating
        if "photography" in need.use_cases and "camera" in tags:
            score += 10
        if "compact" in need.must_haves and "compact" in tags:
            score += 10
        if "fast_charging" in need.must_haves and "fast-charging" in tags:
            score += 10
        return score

    def _preference_bonus(self, product: Product, preference: dict[str, Any]) -> float:
        """Small deterministic tie-breaker applied only after every explicit hard filter."""
        if not preference:
            return 0.0
        bonus = 0.0
        if product.brand in preference.get("preferred_brands", []):
            bonus += 0.25
        if product.category.value in preference.get("preferred_categories", []):
            bonus += 0.10
        centroid = float(preference.get("price_centroid") or 0.0)
        if centroid and abs(product.price - centroid) <= max(100.0, centroid * 0.2):
            bonus += 0.05
        return bonus

    def _plan_score(self, product: Product, need: NeedProfile) -> float:
        tags = {t.lower() for t in product.tags}
        score = product.rating
        if need.roaming_required and "international" in tags:
            score += 10
        if need.lines and "family" in tags:
            score += 10
        if "tablet_data" in need.use_cases and "data-only" in tags:
            score += 10
        if need.monthly_budget_max is not None and product.price <= need.monthly_budget_max:
            score += max(0, 2 - product.price / 100)
        return score

    def _reason_codes(self, product: Product, need: NeedProfile) -> list[ReasonCode]:
        tags = {t.lower() for t in product.tags}
        codes: list[ReasonCode] = []
        if product.category == ProductCategory.PHONE and need.device_budget_max is not None:
            codes.append(ReasonCode.WITHIN_DEVICE_BUDGET)
        if product.category == ProductCategory.PLAN and need.monthly_budget_max is not None:
            codes.append(ReasonCode.WITHIN_MONTHLY_BUDGET)
        if product.category == ProductCategory.PHONE and "photography" in need.use_cases and "camera" in tags:
            codes.append(ReasonCode.CAMERA_MATCH)
        if product.category == ProductCategory.PLAN and need.roaming_required and "international" in tags:
            codes.append(ReasonCode.ROAMING_MATCH)
        if product.category == ProductCategory.PLAN and ("tablet_data" in need.use_cases or "data" in tags):
            codes.append(ReasonCode.DATA_MATCH)
        if product.category == ProductCategory.PHONE and need.platform and need.platform in tags:
            codes.append(ReasonCode.PLATFORM_MATCH)
        if "compact" in need.must_haves and "compact" in tags:
            codes.append(ReasonCode.COMPACT_MATCH)
        if "fast_charging" in need.must_haves and "fast-charging" in tags:
            codes.append(ReasonCode.FAST_CHARGING_MATCH)
        if need.lines and int(product.specs.get("lines", 0)) >= need.lines:
            codes.append(ReasonCode.FAMILY_LINES_MATCH)
        return codes

    def _reason(self, product: Product, codes: list[ReasonCode]) -> str:
        facts: list[str] = []
        if ReasonCode.WITHIN_DEVICE_BUDGET in codes:
            facts.append(f"${product.price:.0f} one-time price is within your device budget")
        if ReasonCode.WITHIN_MONTHLY_BUDGET in codes:
            facts.append(f"${product.price:.0f}/month is within your monthly budget")
        if ReasonCode.CAMERA_MATCH in codes:
            facts.append("catalog tags identify it as a camera phone")
        if ReasonCode.ROAMING_MATCH in codes:
            facts.append("catalog features include international roaming")
        if ReasonCode.DATA_MATCH in codes:
            facts.append(str(product.specs.get("data", "catalog data match")))
        if ReasonCode.PLATFORM_MATCH in codes:
            facts.append("its catalog platform matches")
        if ReasonCode.COMPACT_MATCH in codes:
            facts.append("the catalog marks it compact")
        if ReasonCode.FAST_CHARGING_MATCH in codes:
            facts.append("the catalog marks it fast-charging")
        if ReasonCode.FAMILY_LINES_MATCH in codes:
            facts.append(f"the catalog includes {product.specs.get('lines')} lines")
        if facts:
            return "; ".join(facts) + "."
        cadence = (
            f"${product.price:.0f}/month"
            if product.billing_period == "monthly"
            else f"${product.price:.0f} once"
        )
        return f"In stock at {cadence}."

    def _actions(
        self,
        recs: list[ShopAssistRecommendation],
        text: str,
        state: _State,
        memory: dict[str, Any] | None = None,
    ) -> list[ShopAssistAction]:
        actions: list[ShopAssistAction] = []
        phones = [r.product.id for r in recs if r.product.category == ProductCategory.PHONE]
        decision_style = (memory or {}).get("decision_style", "balanced")
        if len(phones) == 2 and decision_style != "decisive":
            actions.append(ShopAssistAction(
                type=ShopAssistActionType.COMPARE, label="Compare phones", product_ids=phones
            ))
        for rec in recs:
            actions.append(ShopAssistAction(
                type=ShopAssistActionType.OPEN_PRODUCT,
                label=f"Open {rec.product.name}", product_ids=[rec.product.id],
            ))
        return actions

    def _is_compare(self, text: str) -> bool:
        return "compare" in text

    def _comparison_response(
        self, sid: str, state: _State, text: str, mode: ChatMode
    ) -> ChatResponse:
        mentioned = [
            p for p in catalog.all
            if p.category == ProductCategory.PHONE
            and (p.id in text.lower() or p.name.lower().replace("google ", "").replace(" (3rd gen)", "") in text.lower())
        ]
        if len(mentioned) < 2:
            mentioned = [
                r.product for r in state.recommendations
                if r.product.category == ProductCategory.PHONE
            ]
        mentioned = mentioned[:2]
        if len(mentioned) != 2:
            return self._response(
                sid, state, ChatStatus.NO_MATCH,
                "I need two validated phone choices to compare.",
                [], [ShopAssistAction(type=ShopAssistActionType.REFINE, label="Choose two phones")], mode
            )
        difference = abs(mentioned[0].price - mentioned[1].price)
        cheaper = min(mentioned, key=lambda p: p.price)
        message = (
            f"{mentioned[0].name} is ${mentioned[0].price:.0f}; "
            f"{mentioned[1].name} is ${mentioned[1].price:.0f}. "
            f"{cheaper.name} costs ${difference:.0f} less. "
            f"{mentioned[0].features[0]}; {mentioned[1].features[0]}."
        )
        return self._response(
            sid, state, ChatStatus.RECOMMENDED, message, state.recommendations,
            [
                ShopAssistAction(
                    type=ShopAssistActionType.OPEN_PRODUCT,
                    label=f"Open {p.name}", product_ids=[p.id]
                ) for p in mentioned
            ],
            mode, comparison=mentioned,
        )

    def _boundary_response(
        self, sid: str, state: _State, text: str, intent: str
    ) -> ChatResponse:
        state.turns.append({"role": "user", "content": text})
        if intent == "service":
            message = (
                "I can help choose phones and plans, but billing, account, network, and "
                "service issues need help from customer support."
            )
            actions = [ShopAssistAction(
                type=ShopAssistActionType.HANDOFF_SERVICE,
                label="Contact customer support",
            )]
            status = ChatStatus.SERVICE_HANDOFF
        else:
            message = BOUNDARY_UNSUPPORTED_MESSAGE
            actions = []
            status = ChatStatus.UNSUPPORTED
        state.turns = state.turns[-12:]
        return self._response(sid, state, status, message, [], actions, ChatMode.FALLBACK)

    def _recommendation_message(
        self,
        recs: list[ShopAssistRecommendation],
        memory: dict[str, Any] | None = None,
    ) -> str:
        context = memory or {}
        if context.get("communication_style") == "concise" or context.get("decision_style") == "decisive":
            top = recs[0]
            return f"Best match: {top.product.name}. {top.reason}"
        prefix = (
            "I prioritized value from the exact catalog matches: "
            if context.get("price_sensitivity") in {"high", "extreme"}
            else "I found exact in-stock catalog matches: "
        )
        options = []
        for recommendation in recs:
            product = recommendation.product
            cadence = (
                f"${product.price:.0f}/month"
                if product.billing_period == "monthly"
                else f"${product.price:.0f} once"
            )
            options.append(f"{product.name} - {cadence}")
        message = prefix + "; ".join(options) + "."
        if context.get("decision_style") == "researcher" and len(
            [rec for rec in recs if rec.product.category == ProductCategory.PHONE]
        ) == 2:
            message += " I can compare the two phone options side by side."
        return message

    def _cart_summary(self, session_id: str) -> CartSummary:
        products = sorted(session_store.get_cart(session_id), key=lambda product: product.id)
        return CartSummary(
            items=products,
            total_items=len(products),
            one_time_total=round(
                sum(product.price for product in products if product.billing_period != "monthly"),
                2,
            ),
            monthly_total=round(
                sum(product.price for product in products if product.billing_period == "monthly"),
                2,
            ),
        )

    def _cart_summary_message(self, summary: CartSummary) -> str:
        if not summary.items:
            return "Your cart is empty."
        details = [
            f"{product.name} at ${product.price:.2f}"
            + ("/month" if product.billing_period == "monthly" else " one-time")
            for product in summary.items
        ]
        totals: list[str] = []
        if summary.one_time_total:
            totals.append(f"${summary.one_time_total:.2f} due once")
        if summary.monthly_total:
            totals.append(f"${summary.monthly_total:.2f}/month")
        return (
            f"Your cart has {summary.total_items} item"
            f"{'s' if summary.total_items != 1 else ''}: "
            + "; ".join(details)
            + ". Total: "
            + " and ".join(totals)
            + "."
        )

    def _issue_cart_proposal(
        self,
        session_id: str,
        user_id: str | None,
        product_ids: list[str],
        operation: str = "add",
    ) -> CartProposal:
        return commerce_store.create_proposal(
            session_id,
            user_id,
            operation,
            product_ids,
        )

    def _proposal_message(self, proposal: CartProposal) -> str:
        details = [
            f"{product.name}: ${product.price:.2f}"
            + ("/month" if product.billing_period == "monthly" else " one-time")
            for product in proposal.products
        ]
        if proposal.operation == "remove":
            result_totals: list[str] = []
            if proposal.resulting_one_time_total:
                result_totals.append(f"${proposal.resulting_one_time_total:.2f} once")
            if proposal.resulting_monthly_total:
                result_totals.append(f"${proposal.resulting_monthly_total:.2f}/month")
            remaining = " and ".join(result_totals) if result_totals else "$0"
            return (
                "Removal proposal only—your cart is unchanged. Review "
                + " + ".join(details)
                + f". After removal, the cart would be {remaining}. "
                "Confirm explicitly to remove these exact items."
            )
        duplicate_note = (
            f" {len(proposal.excluded_product_ids)} already-in-cart item"
            f"{'s are' if len(proposal.excluded_product_ids) != 1 else ' is'} excluded from a duplicate add."
            if proposal.excluded_product_ids
            else ""
        )
        return (
            "Cart proposal only—your cart is unchanged. Review "
            + " + ".join(details)
            + "."
            + duplicate_note
            + " Confirm explicitly to add the exact proposal."
        )

    def _is_discount_query(self, text: str) -> bool:
        return any(
            word in text
            for word in (
                "discount", "deal", "coupon", "sale", "cashback", "cash back",
                "promotion", "promo", "offer", "rebate",
            )
        )

    def _discount_message(
        self,
        recs: list[ShopAssistRecommendation],
        need: NeedProfile,
    ) -> str:
        if not recs:
            constraint = self._no_match_message(need)
            return (
                "I don't have a validated promotion, discount, or cashback in the "
                f"current catalog, so I won't invent one. {constraint}"
            )
        lowest = min(recs, key=lambda rec: rec.product.price).product
        cadence = "/month" if lowest.billing_period == "monthly" else " one-time"
        return (
            "I don't have a validated promotion, discount, or cashback for these "
            f"items, so I won't invent one. The least expensive of the current "
            f"matches is {lowest.name} at "
            f"${lowest.price:.0f}{cadence}."
        )

    def _no_match_message(self, need: NeedProfile) -> str:
        categories = set(need.categories) or {"phone"}
        if categories == {"phone"} and need.device_budget_max is not None:
            platform = f"{need.platform.capitalize()} " if need.platform else ""
            return (
                f"I couldn't find an in-stock {platform}phone at or below "
                f"${need.device_budget_max:.0f} in the current catalog. "
                "I haven't relaxed your budget."
            )
        if categories == {"plan"} and need.monthly_budget_max is not None:
            return (
                "I couldn't find an in-stock plan at or below "
                f"${need.monthly_budget_max:.0f}/month with those requirements. "
                "I haven't relaxed your constraints."
            )
        return (
            "I couldn't find an exact catalog match for those constraints. "
            "I haven't relaxed any of them."
        )

    def _response(
        self,
        sid: str,
        state: _State,
        status: ChatStatus,
        content: str,
        recs: list[ShopAssistRecommendation],
        actions: list[ShopAssistAction],
        mode: ChatMode,
        comparison: list[Product] | None = None,
        selected_tool: str | None = None,
        cart_summary: CartSummary | None = None,
        cart_proposal: CartProposal | None = None,
        checkout_review_status: str | None = None,
        order_receipt: Any | None = None,
        open_checkout: bool = False,
    ) -> ChatResponse:
        state.turns.append({"role": "assistant", "content": content})
        state.turns = state.turns[-12:]
        return ChatResponse(
            session_id=sid,
            status=status,
            message=content,
            need_profile=state.need,
            recommendations=recs,
            comparison=comparison,
            actions=actions,
            mode=mode,
            suggested_actions=[a.label for a in actions],
            cart_updated=False,
            open_checkout=open_checkout,
            selected_tool=selected_tool,
            cart_summary=cart_summary,
            cart_proposal=cart_proposal,
            checkout_review_status=checkout_review_status,
            order_receipt=order_receipt,
        )


shopassist = ShopAssistService()
