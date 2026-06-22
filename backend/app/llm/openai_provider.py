"""OpenAI-family LLM provider (per the product spec).

Uses the official ``openai`` SDK. Highlights:
  * **Per-task model routing** — analysis, per-field generation, chat revision and
    after-action reasoning can each use a different model (see ``Settings``).
  * **Structured Outputs** — product analysis uses ``chat.completions.parse`` with
    a Pydantic schema when available, falling back to JSON mode, then to the
    deterministic mock, so a launch pipeline never hard-fails midway.
  * Optional ``service_tier`` / ``prompt_cache_key`` pass-through for cost control.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from ..answers.fit import fit_text
from ..config import settings
from ..models import LaunchSite, Product, Question, ScannedPage
from .base import LLMProvider
from .mock_provider import MockProvider

log = logging.getLogger(__name__)

_ANALYZE_SYSTEM = (
    "You are a product marketing analyst. Given the scraped content of a software "
    "product's website, extract a precise, factual understanding of the product. "
    "Populate every field. description_short must be <=300 chars. Do not invent "
    "facts that are not supported by the content; leave a field empty if unknown."
)


# -- Structured-output schema for analysis ----------------------------------
# NB: OpenAI strict Structured Outputs does NOT allow open-ended maps, so
# social_links is modelled as a list of {platform, url} and mapped back to the
# product's dict shape after parsing.
class _SocialLink(BaseModel):
    platform: str = ""
    url: str = ""


class _FeatureOut(BaseModel):
    title: str = ""
    description: str = ""


class ProductUnderstanding(BaseModel):
    name: str = ""
    tagline: str = ""
    description_short: str = ""
    description_long: str = ""
    positioning: str = ""
    icp: str = ""
    target_group: str = ""
    categories: list[str] = Field(default_factory=list)
    topics_tags: list[str] = Field(default_factory=list)
    features: list[_FeatureOut] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    pricing: str = ""
    social_links: list[_SocialLink] = Field(default_factory=list)


class _LearningsOut(BaseModel):
    learnings: list[str] = Field(default_factory=list)


def _understanding_to_dict(u: ProductUnderstanding) -> dict:
    """Map the structured-output model back onto the Product field shape."""
    data = u.model_dump()
    social: dict[str, str] = {}
    for item in data.get("social_links") or []:
        platform = (item.get("platform") or "").strip().lower()
        url = (item.get("url") or "").strip()
        if platform and url and platform not in social:
            social[platform] = url
    data["social_links"] = social
    # features already serialise to {title, description} dicts (matches Feature).
    return data


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        kwargs: dict = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**kwargs)
        # Back-compat: ``model`` is the analysis model (the historic default).
        self.model = settings.model_for("analyze")
        self._fallback = MockProvider()

    # -- low-level helpers -------------------------------------------------
    def _kwargs(self, model: str, messages: list[dict], **extra) -> dict:
        """Assemble create/parse kwargs, adding cost-control params only when set
        (an empty service_tier is an invalid enum value, so it must be omitted)."""
        kwargs: dict = {"model": model, "messages": messages, **extra}
        if settings.llm_service_tier:
            kwargs["service_tier"] = settings.llm_service_tier
        if settings.llm_prompt_cache_key:
            kwargs["prompt_cache_key"] = settings.llm_prompt_cache_key
        return kwargs

    def _text(self, model: str, messages: list[dict], **extra) -> str:
        resp = self.client.chat.completions.create(**self._kwargs(model, messages, **extra))
        return (resp.choices[0].message.content or "").strip()

    # ---------------------------------------------------------------------
    def analyze_product(self, url: str, pages: list[ScannedPage]) -> dict:
        corpus = self._corpus(url, pages)
        messages = [
            {"role": "system", "content": _ANALYZE_SYSTEM},
            {"role": "user", "content": corpus},
        ]
        # Merge over heuristic defaults so missing keys are still populated.
        base = self._fallback.analyze_product(url, pages)
        model = settings.model_for("analyze")

        # 1) Structured Outputs (most reliable JSON).
        if settings.llm_structured_outputs:
            parse = getattr(self.client.chat.completions, "parse", None)
            if parse is not None:
                try:
                    completion = parse(
                        **self._kwargs(model, messages, temperature=0.2),
                        response_format=ProductUnderstanding,
                    )
                    msg = completion.choices[0].message
                    if getattr(msg, "refusal", None):
                        raise RuntimeError(f"model refused: {msg.refusal}")
                    parsed = getattr(msg, "parsed", None)
                    if parsed is not None:
                        data = _understanding_to_dict(parsed)
                        base.update({k: v for k, v in data.items() if v})
                        return base
                except Exception as exc:  # noqa: BLE001 - fall through to JSON mode
                    log.warning("OpenAI structured analyze failed (%s); trying JSON mode", exc)

        # 2) JSON mode.
        try:
            resp = self.client.chat.completions.create(
                **self._kwargs(
                    model, messages, temperature=0.2,
                    response_format={"type": "json_object"},
                )
            )
            data = json.loads(resp.choices[0].message.content)
            base.update({k: v for k, v in data.items() if v})
            return base
        except Exception as exc:  # noqa: BLE001 - resilience by design
            log.warning("OpenAI analyze_product failed (%s); using mock fallback", exc)
            return base

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
        # Stable, cache-friendly prefix (product + best-practices) first; the
        # variable per-field spec goes last so the prefix can be prompt-cached.
        user = (
            f"PRODUCT JSON:\n{product.model_dump_json(exclude={'raw_pages'})}\n\n"
            f"BEST PRACTICES for {site.name}:\n{bp}\n\n"
            f"FIELD: {question.label} (id={question.id}, type={question.type})\n"
            f"FIELD HELP: {question.help}\n"
            f"{limit}\n"
        )
        try:
            text = self._text(
                settings.model_for("generate"),
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.5,
            ).strip('"')
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

    def revise_answer(
        self,
        *,
        question: Question,
        product: Product,
        site: LaunchSite,
        current_value: str,
        instruction: str,
        best_practices: list[str],
    ) -> str:
        limit = (
            f"The result MUST be at most {question.max_length} characters."
            if question.max_length
            else "Keep it appropriately concise."
        )
        system = (
            f"You revise a single launch-submission field for {site.name}. Apply the "
            f"user's instruction to the current value while keeping it accurate to the "
            f"product and following platform best-practices. {limit} "
            f"Output ONLY the revised field text, no preamble, no quotes."
        )
        user = (
            f"FIELD: {question.label} (type={question.type})\n"
            f"CURRENT VALUE: {current_value!r}\n"
            f"INSTRUCTION: {instruction}\n\n"
            f"PRODUCT (for grounding): {product.model_dump_json(exclude={'raw_pages', 'assets'})[:1500]}"
        )
        try:
            text = self._text(
                settings.model_for("revise"),
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.6,
            ).strip('"')
            text, _ = fit_text(text, question.max_length)
            return text or current_value
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI revise_answer failed (%s); using mock fallback", exc)
            return self._fallback.revise_answer(
                question=question, product=product, site=site,
                current_value=current_value, instruction=instruction,
                best_practices=best_practices,
            )

    def extract_learnings(
        self,
        *,
        product: Product,
        site: LaunchSite,
        copy: "object",
        outcomes: list,
    ) -> list[str]:
        """Reason over a launch's copy + measured outcomes to produce concise,
        reusable learnings for the next launch. Uses the 'reason' model."""
        try:
            from ..models import CopySnapshot, LaunchOutcome  # local import avoids cycle

            copy_json = copy.model_dump_json() if isinstance(copy, CopySnapshot) else json.dumps(copy)
            outcomes_json = json.dumps(
                [o.model_dump() if isinstance(o, LaunchOutcome) else o for o in outcomes],
                default=str,
            )
            system = (
                "You are a launch strategist. Given the copy we submitted to a launch "
                "directory and the measured outcome, produce 1-3 short, specific, reusable "
                "learnings to improve the NEXT launch on this kind of platform. Each learning "
                "is one sentence, actionable, and grounded in the outcome."
            )
            user = (
                f"PLATFORM: {site.name} ({site.url})\n"
                f"SUBMITTED COPY: {copy_json}\n"
                f"OUTCOME: {outcomes_json}\n"
                f"PRODUCT CATEGORY: {', '.join(product.categories[:3])}\n"
            )
            parse = getattr(self.client.chat.completions, "parse", None)
            if settings.llm_structured_outputs and parse is not None:
                completion = parse(
                    **self._kwargs(
                        settings.model_for("reason"),
                        [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        temperature=0.3,
                    ),
                    response_format=_LearningsOut,
                )
                msg = completion.choices[0].message
                if not getattr(msg, "refusal", None) and getattr(msg, "parsed", None) is not None:
                    return [s.strip() for s in msg.parsed.learnings if s.strip()][:3]
            text = self._text(
                settings.model_for("reason"),
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
            )
            return [line.strip("-• ").strip() for line in text.splitlines() if line.strip()][:3]
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI extract_learnings failed (%s); using mock fallback", exc)
            return self._fallback.extract_learnings(
                product=product, site=site, copy=copy, outcomes=outcomes
            )

    def complete(self, system: str, user: str, max_tokens: int = 512) -> str:
        try:
            return self._text(
                settings.model_for("generate"),
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=max_tokens,
            )
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
