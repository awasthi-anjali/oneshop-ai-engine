"""Commerce boundary and prompt-injection guardrails for ShopAssist."""

from __future__ import annotations

import re

# Phrase matches (substring, lowercase) — checked before shopping intent.
INJECTION_PHRASES: tuple[str, ...] = (
    # Creative / off-topic
    "write me a poem",
    "write a poem",
    "write me a joke",
    "write a joke",
    "tell me a joke",
    "tell me a story",
    "write python",
    "python code",
    "write code",
    "write me code",
    "write me python",
    "recipe for",
    "weather today",
    "latest news",
    # Prompt / instruction leak
    "system prompt",
    "hidden prompt",
    "developer message",
    "system message",
    "your instructions",
    "show me your instructions",
    "what are your instructions",
    "reveal prompt",
    "repeat your prompt",
    "forget system prompt",
    "forget the system prompt",
    "ignore previous instructions",
    "ignore all previous",
    "ignore previous",
    "act as system",
    "override instructions",
    "jailbreak",
    "bypass",
    # Tool / infrastructure leak
    "show me tools",
    "show your tools",
    "list your tools",
    "list tools",
    "what tools do you",
    "show database",
    "use database",
    "use datab",
    "query the database",
    "query database",
    "sql query",
    "run sql",
    "show me the db",
)

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"forget\s+(?:the\s+)?system\s+prompt", re.I),
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.I),
    re.compile(r"show\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?prompt", re.I),
    re.compile(r"(?:list|show)\s+(?:me\s+)?(?:your\s+)?tools\b", re.I),
    re.compile(r"(?:show|use|query)\s+(?:me\s+)?(?:the\s+)?(?:database|datab)\b", re.I),
    re.compile(r"\bwrite\s+(?:me\s+)?(?:some\s+)?python\b", re.I),
)

# Legacy single-token blocklist kept for deterministic fast path.
LEGACY_UNSUPPORTED_TOKENS: tuple[str, ...] = (
    "poem",
    "coding",
    "recipe",
    "weather",
    "joke",
)

BOUNDARY_UNSUPPORTED_MESSAGE = (
    "I can only help with OneShop phones, plans, comparisons, and a cart proposal."
)


def is_prompt_injection_or_off_topic(text: str) -> bool:
    """Return True when the message should hit the commerce boundary response."""
    lowered = " ".join(text.lower().split())
    if any(phrase in lowered for phrase in INJECTION_PHRASES):
        return True
    if any(pattern.search(lowered) for pattern in INJECTION_PATTERNS):
        return True
    if any(re.search(rf"\b{re.escape(token)}\b", lowered) for token in LEGACY_UNSUPPORTED_TOKENS):
        return True
    if "write code" in lowered or "write me code" in lowered:
        return True
    return False
