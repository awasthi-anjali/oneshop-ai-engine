from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

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


SERVICE_WORDS = (
    "bill", "billing", "account", "contract", "network", "signal", "outage",
    "not working", "technical support", "fault", "password", "login",
)
UNSUPPORTED_WORDS = (
    "poem", "write code", "coding", "recipe", "weather", "news", "joke",
    "hidden prompt", "system prompt", "ignore previous", "developer message",
    "system message", "forget previous", "reveal prompt", "act as system",
    "override instructions", "bypass", "jailbreak",
)
SHOPPING_WORDS = (
    "phone", "iphone", "android", "pixel", "galaxy", "oneplus", "plan",
    "tablet", "data", "camera", "photography", "roaming", "travel", "budget",
    "compare", "recommend", "choose", "buy", "add", "bundle", "compact", "charging",
    "discount", "deal", "coupon", "cheaper", "expensive", "sale", "cart",
    "cashback", "cash back", "promotion", "promo", "offer", "rebate",
    "suggest", "sugest", "affordable",
)

logger = logging.getLogger(__name__)


@dataclass
class _State:
    need: NeedProfile = field(default_factory=NeedProfile)
    turns: list[dict[str, str]] = field(default_factory=list)
    clarification_asked: bool = False
    recommendations: list[ShopAssistRecommendation] = field(default_factory=list)
    total_user_turns: int = 0


class _ComposedResponse(BaseModel):
    message: str = Field(..., min_length=1, max_length=600)


@dataclass
class _CartProposalRecord:
    proposal: CartProposal
    session_id: str
    user_id: str | None
    created_at: float = field(default_factory=time.monotonic)
    consumed: bool = False
    result: CartConfirmationResponse | None = None


class ShopAssistService:
    def __init__(self, memory_store: BehavioralMemoryStore | None = None) -> None:
        self._states: dict[str, _State] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._memory_store = memory_store or behavioral_memory_store
        self._memory_tasks: set[asyncio.Task] = set()
        self._cart_proposals: dict[str, _CartProposalRecord] = {}
        self._confirmation_keys: dict[tuple[str, str], CartConfirmationResponse] = {}
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
            record = self._cart_proposals.get(request.proposal_id)
            if (
                not record
                or time.monotonic() - record.created_at > 900
                or record.session_id != sid
                or record.user_id != request.user_id
            ):
                raise ValueError("Cart proposal is missing, stale, or belongs to another user.")

            replay_key = (request.proposal_id, request.idempotency_key)
            replay = self._confirmation_keys.get(replay_key)
            if replay:
                return replay.model_copy(update={"idempotent_replay": True})
            if record.consumed and record.result:
                result = record.result.model_copy(update={"idempotent_replay": True})
                self._confirmation_keys[replay_key] = result
                return result

            products = catalog.get_by_ids(record.proposal.product_ids)
            if (
                len(products) != len(record.proposal.product_ids)
                or any(not product.in_stock for product in products)
            ):
                raise ValueError("One or more proposal items are no longer available. Nothing was added.")
            current_facts = self._cart_proposal(
                record.proposal.proposal_id,
                products,
                record.proposal.excluded_product_ids,
            )
            if current_facts != record.proposal:
                raise ValueError("Cart proposal pricing changed. Nothing was added; request a fresh proposal.")

            existing = set(session_store.get_cart_ids(sid))
            added_ids = [pid for pid in record.proposal.product_ids if pid not in existing]
            excluded_ids = [pid for pid in record.proposal.product_ids if pid in existing]
            if added_ids:
                session_store.add_bundle_to_cart(sid, added_ids)
            result = CartConfirmationResponse(
                session_id=sid,
                proposal_id=request.proposal_id,
                added_product_ids=added_ids,
                excluded_product_ids=excluded_ids,
                cart_summary=self._cart_summary(sid),
            )
            record.consumed = True
            record.result = result
            self._confirmation_keys[replay_key] = result
            return result

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
        assistant_context = self._assistant_context(request.user_id, sid)
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

        deterministic_intent = self._intent(lowered)
        reference_patch = self._memory_reference_patch(
            lowered,
            assistant_context.get("behavioral_memory", {}),
        )
        if deterministic_intent == "ambiguous" and reference_patch:
            deterministic_intent = "shopping"
        if (
            deterministic_intent == "ambiguous"
            and request.page_context
            and request.page_context.product_id
            and not any(word in lowered for word in UNSUPPORTED_WORDS)
        ):
            deterministic_intent = "shopping"
        if deterministic_intent == "ambiguous" and state.need.categories:
            deterministic_intent = "shopping"

        ai_result: tuple[str, dict[str, Any]] | None = None
        if deterministic_intent == "ambiguous":
            ai_result = await self._ai_parse(text, assistant_context)
            if ai_result is not None:
                deterministic_intent = ai_result[0]
            else:
                deterministic_intent = "unsupported"
        if deterministic_intent != "shopping":
            return self._boundary_response(sid, state, text, deterministic_intent)

        if self._is_cart_lookup(lowered):
            state.turns.append({"role": "user", "content": text})
            summary = self._cart_summary(sid)
            return self._response(
                sid,
                state,
                ChatStatus.RECOMMENDED,
                self._cart_summary_message(summary),
                [],
                [],
                ChatMode.FALLBACK,
                selected_tool="cart_lookup",
                cart_summary=summary,
            )

        patch = reference_patch
        patch.update(self._extract_need(text, request, state.need))
        mode = ChatMode.FALLBACK
        if ai_result is None:
            ai_result = await self._ai_parse(text, assistant_context)
        if ai_result is not None:
            ai_intent, ai_patch = ai_result
            if ai_intent == "shopping":
                patch = self._merge_patch(patch, ai_patch)
                mode = ChatMode.AI

        state.need = self._merge_need(state.need, patch)
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
        elif self._is_compare(lowered):
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
        if any(word in text for word in UNSUPPORTED_WORDS):
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

    def _is_cart_lookup(self, text: str) -> bool:
        return any(
            phrase in text
            for phrase in (
                "what's in my cart",
                "what is in my cart",
                "show my cart",
                "show cart",
                "cart total",
                "check my cart",
                "view my cart",
            )
        )

    def _conversational_response(
        self,
        sid: str,
        state: _State,
        text: str,
        lowered: str,
    ) -> ChatResponse | None:
        normalized = re.sub(r"[^a-z\s]", "", lowered).strip()
        normalized = " ".join(normalized.split())
        if normalized in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}:
            state.turns.append({"role": "user", "content": text})
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

    def _assistant_context(self, user_id: str | None, session_id: str) -> dict[str, Any]:
        return {
            "preferences": bounded_preference_context(user_id, session_id),
            "behavioral_memory": bounded_memory_context(user_id, self._memory_store),
        }

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
    ) -> tuple[str, dict[str, Any]] | None:
        if not self._client:
            return None
        try:
            completion = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=settings.openai_model,
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
            intent = raw.get("intent")
            patch = raw.get("need_patch", {})
            if intent not in {"shopping", "unsupported", "service"} or not isinstance(patch, dict):
                return None
            validated = NeedProfile(**patch).model_dump(exclude_none=True, exclude_defaults=True)
            return intent, validated
        except Exception as exc:
            logger.warning(
                "ShopAssist need parser fallback model=%s error=%s",
                settings.openai_model,
                type(exc).__name__,
            )
            return None

    async def _ai_compose_response(
        self,
        text: str,
        need: NeedProfile,
        recs: list[ShopAssistRecommendation],
        assistant_context: dict[str, Any],
        fallback: str,
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
            if self._composition_is_grounded(composed, recs):
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
        allowed_ids = {rec.product.id for rec in recs}
        if not any(rec.product.name.lower() in lowered for rec in recs):
            return False
        for product in catalog.all:
            if product.id not in allowed_ids and product.name.lower() in lowered:
                return False
        allowed_prices = {round(rec.product.price, 2) for rec in recs}
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
        if not effective_categories and generic_budget:
            effective_categories = ["phone"]
            patch.setdefault("categories", ["phone"])
        if generic_budget and len(effective_categories) == 1:
            amount = float(generic_budget.group(1).replace(",", ""))
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

    def _merge_patch(self, deterministic: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
        merged = dict(ai)
        merged.update(deterministic)
        return merged

    def _merge_need(self, current: NeedProfile, patch: dict[str, Any]) -> NeedProfile:
        data = current.model_dump()
        for key, value in patch.items():
            if key in {"categories", "use_cases", "must_haves", "nice_to_haves"}:
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
        return "; ".join(facts) + "." if facts else f"{product.name} is an in-stock catalog match."

    def _actions(
        self,
        recs: list[ShopAssistRecommendation],
        text: str,
        state: _State,
        memory: dict[str, Any] | None = None,
    ) -> list[ShopAssistAction]:
        if any(x in text for x in ("add ", "put ", "bundle")):
            mentioned_ids = [
                product.id
                for product in catalog.all
                if product.id in self._mentioned_product_ids(text)
            ]
            phone = next((r.product for r in recs if r.product.category == ProductCategory.PHONE), None)
            plan = next((r.product for r in recs if r.product.category == ProductCategory.PLAN), None)
            if not phone:
                phone = next(
                    (r.product for r in state.recommendations if r.product.category == ProductCategory.PHONE), None
                )
            if not plan:
                plan = next(
                    (r.product for r in state.recommendations if r.product.category == ProductCategory.PLAN), None
                )
            wants_bundle = "bundle" in text or "recommended plan" in text or (
                phone and plan and len(mentioned_ids) > 1
            )
            if wants_bundle and len(mentioned_ids) > 1:
                products = catalog.get_by_ids(mentioned_ids[:3])
                return [ShopAssistAction(
                    type=ShopAssistActionType.PROPOSE_ADD_BUNDLE,
                    label="Review " + " + ".join(product.name for product in products),
                    product_ids=[product.id for product in products],
                )]
            if phone and plan and wants_bundle:
                return [ShopAssistAction(
                    type=ShopAssistActionType.PROPOSE_ADD_BUNDLE,
                    label=f"Review {phone.name} + {plan.name}",
                    product_ids=[phone.id, plan.id],
                )]
            selected_ids = mentioned_ids[:3]
            if not selected_ids:
                top = next(iter(recs), None) or next(iter(state.recommendations), None)
                selected_ids = [top.product.id] if top else []
            if selected_ids:
                products = catalog.get_by_ids(selected_ids)
                return [ShopAssistAction(
                    type=(
                        ShopAssistActionType.PROPOSE_ADD_BUNDLE
                        if len(products) > 1
                        else ShopAssistActionType.PROPOSE_ADD_TO_CART
                    ),
                    label=(
                        "Review " + " + ".join(product.name for product in products)
                        if len(products) > 1
                        else f"Review {products[0].name}"
                    ),
                    product_ids=[product.id for product in products],
                )]
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
                "service issues need Frag Magenta support."
            )
            actions = [ShopAssistAction(
                type=ShopAssistActionType.HANDOFF_SERVICE,
                label="Contact Frag Magenta support",
            )]
            status = ChatStatus.SERVICE_HANDOFF
        else:
            message = (
                "I can only help with OneShop phones, plans, comparisons, and a cart proposal."
            )
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
        message = prefix + ", ".join(f"{r.product.name} ({r.reason})" for r in recs)
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

    def _cart_proposal(
        self,
        proposal_id: str,
        products: list[Product],
        excluded_product_ids: list[str],
    ) -> CartProposal:
        return CartProposal(
            proposal_id=proposal_id,
            products=[product.model_copy(deep=True) for product in products],
            product_ids=[product.id for product in products],
            excluded_product_ids=excluded_product_ids,
            one_time_total=round(
                sum(product.price for product in products if product.billing_period != "monthly"),
                2,
            ),
            monthly_total=round(
                sum(product.price for product in products if product.billing_period == "monthly"),
                2,
            ),
        )

    def _issue_cart_proposal(
        self,
        session_id: str,
        user_id: str | None,
        product_ids: list[str],
    ) -> CartProposal:
        products = catalog.get_by_ids(product_ids)
        if len(products) != len(product_ids) or any(not product.in_stock for product in products):
            raise ValueError("One or more requested items are unavailable.")
        existing = set(session_store.get_cart_ids(session_id))
        proposal_id = secrets.token_urlsafe(24)
        proposal = self._cart_proposal(
            proposal_id,
            products,
            [product.id for product in products if product.id in existing],
        )
        if len(self._cart_proposals) >= 500:
            oldest_id = next(iter(self._cart_proposals))
            self._cart_proposals.pop(oldest_id, None)
            stale_keys = [
                key for key in self._confirmation_keys if key[0] == oldest_id
            ]
            for key in stale_keys:
                self._confirmation_keys.pop(key, None)
        self._cart_proposals[proposal_id] = _CartProposalRecord(
            proposal=proposal,
            session_id=session_id,
            user_id=user_id,
        )
        return proposal

    def _proposal_message(self, proposal: CartProposal) -> str:
        details = [
            f"{product.name}: ${product.price:.2f}"
            + ("/month" if product.billing_period == "monthly" else " one-time")
            for product in proposal.products
        ]
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
            open_checkout=False,
            selected_tool=selected_tool,
            cart_summary=cart_summary,
            cart_proposal=cart_proposal,
        )


shopassist = ShopAssistService()
