from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.models.schemas import (
    ChatMode,
    ChatRequest,
    ChatResponse,
    ChatStatus,
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
from app.services.session_store import session_store
from app.services.shopassist_prompt import SHOPASSIST_SYSTEM_PROMPT


SERVICE_WORDS = (
    "bill", "billing", "account", "contract", "network", "signal", "outage",
    "not working", "technical support", "fault", "password", "login",
)
UNSUPPORTED_WORDS = (
    "poem", "write code", "coding", "recipe", "weather", "news", "joke",
    "hidden prompt", "system prompt", "ignore previous", "developer message",
    "bypass", "jailbreak",
)
SHOPPING_WORDS = (
    "phone", "iphone", "android", "pixel", "galaxy", "oneplus", "plan",
    "tablet", "data", "camera", "photography", "roaming", "travel", "budget",
    "compare", "recommend", "choose", "buy", "add", "compact", "charging",
)


@dataclass
class _State:
    need: NeedProfile = field(default_factory=NeedProfile)
    turns: list[dict[str, str]] = field(default_factory=list)
    clarification_asked: bool = False
    recommendations: list[ShopAssistRecommendation] = field(default_factory=list)


class ShopAssistService:
    def __init__(self) -> None:
        self._states: dict[str, _State] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key else None
        )

    @property
    def uses_llm(self) -> bool:
        return self._client is not None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._validate_context(request)
        sid = session_store.get_or_create(request.session_id or str(uuid.uuid4()))
        async with self._locks[sid]:
            return await self._chat_locked(sid, request)

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

        deterministic_intent = self._intent(lowered)
        if (
            deterministic_intent == "unsupported"
            and request.page_context
            and request.page_context.product_id
            and not any(word in lowered for word in UNSUPPORTED_WORDS)
        ):
            deterministic_intent = "shopping"
        if deterministic_intent != "shopping":
            return self._boundary_response(sid, state, text, deterministic_intent)

        patch = self._extract_need(text, request)
        mode = ChatMode.FALLBACK
        ai_result = await self._ai_parse(text)
        if ai_result is not None:
            ai_intent, ai_patch = ai_result
            if ai_intent in {"unsupported", "service"}:
                return self._boundary_response(sid, state, text, ai_intent)
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
            if not recs:
                response = self._response(
                    sid, state, ChatStatus.NO_MATCH,
                    "I couldn't find an exact catalog match for those constraints. I haven't relaxed any of them.",
                    [], [ShopAssistAction(type=ShopAssistActionType.REFINE, label="Refine constraints")], mode
                )
            else:
                actions = self._actions(recs, lowered, state)
                if any(a.type == ShopAssistActionType.PROPOSE_ADD_BUNDLE for a in actions):
                    message = self._proposal_message(actions[0].product_ids)
                else:
                    message = self._recommendation_message(recs)
                response = self._response(
                    sid, state, ChatStatus.RECOMMENDED, message, recs, actions, mode
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
        return "unsupported"

    async def _ai_parse(self, text: str) -> tuple[str, dict[str, Any]] | None:
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
        except (Exception, asyncio.TimeoutError, json.JSONDecodeError, ValidationError):
            return None

    def _extract_need(self, text: str, request: ChatRequest) -> dict[str, Any]:
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
        generic_under = re.search(r"(?:under|below|up to|max(?:imum)?)\s*\$?(\d[\d,]*)", lower)
        if device_match:
            patch["device_budget_max"] = float(device_match.group(1).replace(",", ""))
        if plan_match:
            patch["monthly_budget_max"] = float(plan_match.group(1).replace(",", ""))
        if len(amounts) >= 2 and {"phone", "plan"}.issubset(set(categories or [])):
            patch.setdefault("device_budget_max", amounts[0])
            patch.setdefault("monthly_budget_max", amounts[1])
        elif generic_under and len(categories) == 1:
            amount = float(generic_under.group(1).replace(",", ""))
            if categories == ["plan"]:
                patch.setdefault("monthly_budget_max", amount)
            elif "phone" in categories:
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

        # A requested bundle is only an exact match when each requested slot exists.
        if ("phone" in categories and not phones) or ("plan" in categories and not plans):
            return []

        phones.sort(key=lambda p: self._phone_score(p, need), reverse=True)
        plans.sort(key=lambda p: self._plan_score(p, need), reverse=True)
        mentioned_ids = self._mentioned_product_ids(request.message)
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
        self, recs: list[ShopAssistRecommendation], text: str, state: _State
    ) -> list[ShopAssistAction]:
        if any(x in text for x in ("add ", "put ", "bundle")):
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
            if phone and plan:
                return [ShopAssistAction(
                    type=ShopAssistActionType.PROPOSE_ADD_BUNDLE,
                    label=f"Review {phone.name} + {plan.name}",
                    product_ids=[phone.id, plan.id],
                )]
        actions: list[ShopAssistAction] = []
        phones = [r.product.id for r in recs if r.product.category == ProductCategory.PHONE]
        if len(phones) == 2:
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

    def _recommendation_message(self, recs: list[ShopAssistRecommendation]) -> str:
        return "I found exact in-stock catalog matches: " + ", ".join(
            f"{r.product.name} ({r.reason})" for r in recs
        )

    def _proposal_message(self, ids: list[str]) -> str:
        products = catalog.get_by_ids(ids)
        details = [
            f"{p.name}: ${p.price:.0f}{'/month' if p.billing_period == 'monthly' else ' one-time'}"
            for p in products
        ]
        return "Cart proposal only—your cart is unchanged. Review " + " + ".join(details) + "."

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
        )


shopassist = ShopAssistService()
