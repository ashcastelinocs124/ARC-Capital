"""LLM adoption-claim extractor over keyword-prefiltered filing passages."""

from __future__ import annotations

import re

from castelino.adoption.guard import keep_verified
from castelino.adoption.models import Claim, ExtractedClaims
from castelino.agents.base import StructuredAgent

# "AI" and "LLM" are case-sensitive so ordinary words never match; the long phrases are case-insensitive.
AI_PATTERN = re.compile(
    r"(?i:artificial intelligence|machine learning|generative ai|large language models?|deep learning)"
    r"|\bLLMs?\b|\bAI\b"
)


def ai_passages(text: str, *, max_passages: int, window: int) -> list[str]:
    """Text windows around AI keyword hits; nearby hits merge (up to 6 windows long), capped at max_passages."""
    spans: list[list[int]] = []
    for m in AI_PATTERN.finditer(text):
        s, e = max(0, m.start() - window), min(len(text), m.end() + window)
        if spans and s <= spans[-1][1] and e - spans[-1][0] <= 6 * window:
            spans[-1][1] = e
        else:
            spans.append([s, e])
    return [text[s:e].strip() for s, e in spans[:max_passages]]


class AdoptionExtractor(StructuredAgent[ExtractedClaims]):
    name = "adoption_extractor"
    output_schema = ExtractedClaims
    tier = "fast"
    # gpt-5.x reasoning tokens share this budget; the global 2048 truncates the parse (see deep_research)
    max_output_tokens = 16000

    def system_prompt(self) -> str:
        return (
            "You rate how far a company has adopted AI, using only passages from its own SEC filing. "
            "Return claims. Each claim has a quote copied VERBATIM from the passages (one sentence or "
            "clause, at most 300 characters) and a depth: "
            "1 = exploring, piloting, or planning AI; "
            "2 = AI deployed in operations or products today; "
            "3 = AI tied to revenue, cost savings, or customer results with a number or named outcome. "
            "Skip generic risk language that only says AI may affect the industry. "
            "Return at most 20 claims, strongest first. "
            "Never paraphrase. If nothing qualifies, return an empty list."
        )

    def user_prompt(self, *, ticker: str, passages: list[str]) -> str:
        return f"Company: {ticker}\n\nPassages:\n" + "\n---\n".join(passages)


def extract_claims(
    ticker: str,
    text: str,
    *,
    max_passages: int,
    window: int,
    agent: StructuredAgent | None = None,
) -> tuple[list[Claim], list[Claim]]:
    """(kept, dropped) claims for one filing. No AI passages means no LLM call and no claims."""
    passages = ai_passages(text, max_passages=max_passages, window=window)
    if not passages:
        return [], []
    result = (agent or AdoptionExtractor())(ticker=ticker, passages=passages)
    return keep_verified(result.claims, text)
