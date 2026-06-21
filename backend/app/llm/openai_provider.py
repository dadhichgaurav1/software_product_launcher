"""OpenAI-family LLM provider (per the product spec).

Uses the official ``openai`` SDK. To keep the product resilient, any API/network
failure transparently falls back to the deterministic MockProvider so a launch
pipeline never hard-fails midway.
"""
from __future__ import annotations

import json
import logging

from ..answers.fit import fit_text
from ..config import settings
from ..models import LaunchSite, Product, Question, ScannedPage
from .base import LLMProvider
from .mock_provider import MockProvider

log = logging.getLogger(__name__)

_ANALYZE_SYSTEM = (
    "You are a product marketing analyst. Given the scraped content of a software "
    "product's website, extract a precise, factual understanding of the product. "
    "Return STRICT JSON with keys: name, tagline, description_short (<=300 chars), "
    "description_long, positioning, icp (ideal customer profile), target_group, "
    "categories (array), topics_tags (array), features (array of {title, description}), "
    "benefits (array of strings), pricing, social_links (object). "
    "Do not invent facts that are not supported by the content."
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        kwargs: dict = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**kwargs)
        self.model = settings.llm_model
        self._fallback = MockProvider()

    # ---------------------------------------------------------------------
    def analyze_product(self, url: str, pages: list[ScannedPage]) -> dict:
        corpus = self._corpus(url, pages)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.2,
                messages=[
                    {"role": "system", "content": _ANALYZE_SYSTEM},
                    {"role": "user", "content": corpus},
                ],
            )
            data = json.loads(resp.choices[0].message.content)
            # Merge over heuristic defaults so missing keys are still populated.
            base = self._fallback.analyze_product(url, pages)
            base.update({k: v for k, v in data.items() if v})
            return base
        except Exception as exc:  # noqa: BLE001 - resilience by design
            log.warning("OpenAI analyze_product failed (%s); using mock fallback", exc)
            return self._fallback.analyze_product(url, pages)

    def generate_answer(
        self,
        *,
        question: Question,
        product: Product,
        site: LaunchSite,
        best_practices: list[str],
    ) -> str:
        bp = "\n".join(f"- {b}" for b in best_practices) or "- Be clear and specific."
        if question.max_length:
            limit = (
                f"HARD LIMIT: the answer MUST be at most {question.max_length} characters "
                f"(this is the '{site.name}' field limit). Write a COMPLETE phrase that fits "
                f"within the limit — do NOT exceed it and do NOT return a cut-off fragment."
            )
        else:
            limit = "Keep it appropriately concise for this field."
        system = (
            f"You are an expert at writing high-converting launch submissions for "
            f"{site.name} ({site.url}). Write the answer for ONE field, following the "
            f"platform best-practices and respecting the field's length limit exactly. "
            f"Output ONLY the answer text, no preamble, no quotes."
        )
        user = (
            f"PRODUCT JSON:\n{product.model_dump_json(exclude={'raw_pages'})}\n\n"
            f"FIELD: {question.label} (id={question.id}, type={question.type})\n"
            f"{limit}\n"
            f"FIELD HELP: {question.help}\n\n"
            f"BEST PRACTICES for {site.name}:\n{bp}\n"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0.5,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = (resp.choices[0].message.content or "").strip().strip('"')
            # Smart fit as a safety net; the generator also fits + flags truncation.
            text, _ = fit_text(text, question.max_length)
            return text or self._fallback.generate_answer(
                question=question, product=product, site=site, best_practices=best_practices
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI generate_answer failed (%s); using mock fallback", exc)
            return self._fallback.generate_answer(
                question=question, product=product, site=site, best_practices=best_practices
            )

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI complete failed (%s); using mock fallback", exc)
            return self._fallback.complete(system, user, max_tokens)

    # ---------------------------------------------------------------------
    @staticmethod
    def _corpus(url: str, pages: list[ScannedPage], limit: int = 12000) -> str:
        chunks = [f"PRODUCT URL: {url}"]
        for p in pages:
            chunks.append(
                f"\n## PAGE: {p.url}\nTITLE: {p.title}\nMETA: {p.meta_description}\n"
                f"OG: {json.dumps(p.og)[:500]}\nHEADINGS: {' | '.join(p.headings[:20])}\n"
                f"LIST ITEMS: {' | '.join(p.list_items[:30])}\nTEXT: {p.text[:2500]}"
            )
        return "\n".join(chunks)[:limit]
