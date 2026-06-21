"""Service layer used by the API routes.

Kept separate from FastAPI so it can be unit-tested directly and so the analyzer
construction can be overridden in tests (offline fetcher) via the factory hooks.
"""
from __future__ import annotations

import logging

from ..analyzer.product_analyzer import ProductAnalyzer, default_asset_downloader
from ..answers.best_practices import get_best_practices, live_researcher
from ..answers.generator import AnswerGenerator, fill_step_for
from ..answers.fit import fit_text
from ..config import settings
from ..llm.factory import get_provider
from ..models import Answer, AnswerSet, ChatMessage, DraftBundle, Product
from ..registry import sites as registry
from ..store.draft_store import DraftStore
from ..store.product_store import ProductStore

log = logging.getLogger(__name__)

_store: ProductStore | None = None
_drafts: DraftStore | None = None


def store() -> ProductStore:
    global _store
    if _store is None:
        _store = ProductStore()
    return _store


def drafts() -> DraftStore:
    global _drafts
    if _drafts is None:
        _drafts = DraftStore()
    return _drafts


# -- factory hooks (overridable in tests) -----------------------------------
def get_analyzer() -> ProductAnalyzer:
    return ProductAnalyzer(asset_downloader=default_asset_downloader)


def get_generator() -> AnswerGenerator:
    provider = get_provider()
    # Live best-practice research only makes sense with a real LLM/network.
    researcher = None
    if provider.name == "openai":
        researcher = live_researcher(provider)
    return AnswerGenerator(provider=provider, researcher=researcher)


# -- operations -------------------------------------------------------------
def scan(url: str, force: bool = False) -> Product:
    """Return the stored product, re-analyzing when missing or force-refreshed."""
    st = store()
    if not force:
        existing = st.load(url)
        if existing is not None:
            log.info("Returning cached product for %s (v%s)", url, existing.version)
            return existing
    product = get_analyzer().analyze(url)
    return st.save(product, force=force)


def get_product(url: str) -> Product | None:
    return store().load(url)


def delete_product(url: str) -> bool:
    drafts().delete(url)
    return store().delete(url)


def list_products() -> list[dict]:
    return store().list_summaries()


def generate(
    url: str,
    site_ids: list[str] | None = None,
    force_scan: bool = False,
    regenerate: bool = True,
) -> list[AnswerSet]:
    """Generate (and persist) answer sets for the selected sites.

    When ``regenerate`` is False, an already-persisted draft is returned as-is so
    inline edits / chat revisions are not overwritten.
    """
    product = scan(url, force=force_scan)
    gen = get_generator()
    bundle = drafts().load(url)
    out: list[AnswerSet] = []
    for site in _resolve_sites(site_ids):
        if not regenerate and site.id in bundle.answer_sets:
            out.append(bundle.answer_sets[site.id])
        else:
            out.append(gen.generate(product, site))
    drafts().put_sets(url, out)
    return out


def generate_one(url: str, site_id: str, force_scan: bool = False) -> AnswerSet:
    """Return one site's draft, preferring the persisted (possibly edited) version."""
    site = registry.get_site(site_id)
    if site is None:
        raise KeyError(site_id)
    existing = drafts().get_set(url, site_id)
    if existing is not None and not force_scan:
        return existing
    product = scan(url, force=force_scan)
    aset = get_generator().generate(product, site)
    drafts().put_sets(url, [aset])
    return aset


# -- drafts: read + inline edit --------------------------------------------
def get_drafts(url: str) -> DraftBundle:
    return drafts().load(url)


def update_answer(url: str, site_id: str, question_id: str, value: str) -> AnswerSet:
    """Apply a user's inline edit and rebuild that field's fill step."""
    site = registry.get_site(site_id)
    if site is None:
        raise KeyError(site_id)
    bundle = drafts().load(url)
    aset = bundle.answer_sets.get(site_id)
    if aset is None:
        raise LookupError(f"No draft for site '{site_id}'; generate it first")
    question = next((q for q in site.questions if q.id == question_id), None)
    answer = next((a for a in aset.answers if a.question_id == question_id), None)
    if question is None or answer is None:
        raise LookupError(f"Unknown field '{question_id}'")

    answer.value = value
    answer.edited = True
    answer.source = "edited"
    answer.truncated = bool(question.max_length and len(value) > question.max_length)

    # Rebuild the matching fill step (add / update / remove).
    aset.fill_plan = [s for s in aset.fill_plan if s.question_id != question_id]
    step = fill_step_for(question, value) if value else None
    if step is not None:
        aset.fill_plan.append(step)

    bundle.answer_sets[site_id] = aset
    drafts().save(bundle)
    return aset


def _resolve_sites(site_ids: list[str] | None):
    if not site_ids:
        return registry.all_sites()
    out = []
    for sid in site_ids:
        site = registry.get_site(sid)
        if site is not None:
            out.append(site)
    return out


# -- agent chat: revise drafts across sites --------------------------------
_REVISABLE_TYPES = {"text", "textarea", "tags"}
_FIELD_HINT_WORDS = (
    "tagline", "one-liner", "one liner", "slogan", "headline", "pitch", "title",
    "description", "desc", "summary", "about", "blurb", "elevator", "name",
)


def _field_focus(instruction: str) -> list[str]:
    ins = instruction.lower()
    return [w for w in _FIELD_HINT_WORDS if w in ins]


def _matches_focus(answer: Answer, question, focus: list[str]) -> bool:
    hay = f"{answer.question_id} {answer.label} {question.maps_to or ''}".lower()
    return any(w in hay for w in focus)


def chat_revise(url: str, instruction: str, site_ids: list[str] | None = None) -> dict:
    product = store().load(url)
    if product is None:
        raise LookupError("Scan the product first")
    bundle = drafts().load(url)
    if not bundle.answer_sets:
        raise LookupError("Generate drafts before using the chat")
    targets = [s for s in (site_ids or list(bundle.answer_sets)) if s in bundle.answer_sets]
    if not targets:
        raise LookupError("No matching drafts to revise")

    provider = get_provider()
    focus = _field_focus(instruction)
    changed_fields = 0
    changed_sites: list[str] = []

    for sid in targets:
        site = registry.get_site(sid)
        if site is None:
            continue
        aset = bundle.answer_sets[sid]
        practices = get_best_practices(site)
        qmap = {q.id: q for q in site.questions}
        site_changed = False
        for ans in aset.answers:
            q = qmap.get(ans.question_id)
            if q is None or ans.type not in _REVISABLE_TYPES or not ans.value:
                continue
            if focus and not _matches_focus(ans, q, focus):
                continue
            new = provider.revise_answer(
                question=q, product=product, site=site,
                current_value=ans.value, instruction=instruction, best_practices=practices,
            )
            new, truncated = fit_text(new, q.max_length)
            if new and new != ans.value:
                ans.value, ans.truncated, ans.source, ans.edited = new, truncated, "llm", False
                aset.fill_plan = [s for s in aset.fill_plan if s.question_id != ans.question_id]
                step = fill_step_for(q, new)
                if step is not None:
                    aset.fill_plan.append(step)
                changed_fields += 1
                site_changed = True
        bundle.answer_sets[sid] = aset
        if site_changed:
            changed_sites.append(sid)

    scope = "all drafts" if not site_ids else _names(targets)
    summary = _chat_summary(provider.name, changed_fields, changed_sites)
    bundle.chat.append(ChatMessage(role="user", content=instruction, scope=scope))
    bundle.chat.append(
        ChatMessage(role="assistant", content=summary, scope=scope, affected_sites=changed_sites)
    )
    drafts().save(bundle)
    return {
        "assistant": summary,
        "changed_fields": changed_fields,
        "updated_site_ids": changed_sites,
        "answer_sets": [bundle.answer_sets[s].model_dump() for s in targets],
        "chat": [m.model_dump() for m in bundle.chat],
    }


def _names(site_ids: list[str]) -> str:
    names = [registry.get_site(s).name for s in site_ids if registry.get_site(s)]
    return ", ".join(names)


def _chat_summary(provider_name: str, changed_fields: int, changed_sites: list[str]) -> str:
    if changed_fields:
        return f"Updated {changed_fields} field(s) across {len(changed_sites)} site(s): {_names(changed_sites)}."
    if provider_name == "mock":
        return (
            "No changes applied. The offline assistant handles instructions like "
            "“shorten”, “make it more professional”, “add an emoji”, “lead with the "
            "benefit”, or “add keywords”. Set OPENAI_API_KEY for free-form rewriting, "
            "or edit any field inline."
        )
    return "No changes were necessary for that instruction."
