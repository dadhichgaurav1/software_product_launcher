"""Service layer used by the API routes.

Kept separate from FastAPI so it can be unit-tested directly and so the analyzer
construction can be overridden in tests (offline fetcher) via the factory hooks.
"""
from __future__ import annotations

import hashlib
import logging
import re

from ..analyzer.product_analyzer import ProductAnalyzer, default_asset_downloader
from ..answers.best_practices import get_best_practices, live_researcher
from ..answers.generator import AnswerGenerator, fill_step_for
from ..answers.fit import fit_text
from ..config import settings
from ..llm.factory import get_provider
from ..memory.factory import get_memory
from ..models import (
    Answer,
    AnswerSet,
    ChatMessage,
    CopySnapshot,
    DraftBundle,
    Launch,
    LaunchBook,
    LaunchOutcome,
    Learning,
    Product,
)
from ..registry import sites as registry
from ..store.draft_store import DraftStore
from ..store.launch_store import LaunchStore
from ..store.product_store import ProductStore

log = logging.getLogger(__name__)

_store: ProductStore | None = None
_drafts: DraftStore | None = None
_launches: LaunchStore | None = None


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


def launches() -> LaunchStore:
    global _launches
    if _launches is None:
        _launches = LaunchStore()
    return _launches


# -- factory hooks (overridable in tests) -----------------------------------
def get_analyzer() -> ProductAnalyzer:
    return ProductAnalyzer(asset_downloader=default_asset_downloader)


def get_generator() -> AnswerGenerator:
    provider = get_provider()
    # Live best-practice research only makes sense with a real LLM/network.
    researcher = None
    if provider.name == "openai":
        researcher = live_researcher(provider)
    return AnswerGenerator(
        provider=provider,
        researcher=researcher,
        memory=get_memory(),
        learnings=learnings_for_site,
    )


def learnings_for_site(site_id: str, limit: int = 5) -> list[str]:
    """Post-launch learnings (global + this site's) fed forward into generation."""
    return [ln.text for ln in launches().learnings_for(site_id)][:limit]


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
    saved = st.save(product, force=force)
    get_memory().remember_product(saved)
    return saved


def get_product(url: str) -> Product | None:
    return store().load(url)


def delete_product(url: str) -> bool:
    drafts().delete(url)
    launches().delete(url)  # the product's launch book; never the shared global file
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
    get_memory().remember_edit(url, site_id, answer.label, value)
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

# Field aliases: a user phrase -> the field(s) it targets. "Specific" groups win
# over the generic website/url group, so "demo URL" targets the demo field rather
# than every URL field.
_SPECIFIC_GROUPS = (
    ("tagline", "one-liner", "one liner", "slogan", "headline", "pitch"),
    ("description", "desc", "summary", "about", "blurb", "overview", "elevator"),
    ("product name", "startup name", "tool name", "app name", " name"),
    ("demo", "video", "gif", "screencast", "walkthrough"),
    ("pricing", "price", "plan", "cost"),
    ("logo", "icon", "thumbnail", "screenshot"),
    ("github", "repo", "repository", "source code"),
    ("twitter", "x handle", "x.com"),
    ("category", "categories", "topics", "tags"),
    (" title",),
)
_GENERIC_URL = ("website", "url", "link", "homepage", " site")

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{2,})[\"“”']")


def detect_focus(instruction: str) -> list[str]:
    """Return field-matcher words the instruction targets. Specific groups take
    precedence; otherwise the generic website/url group; otherwise empty (= all)."""
    ins = " " + instruction.lower() + " "
    words: list[str] = []
    for group in _SPECIFIC_GROUPS:
        if any(w.strip() in ins for w in group):
            words.extend(w.strip() for w in group)
    if words:
        return list(dict.fromkeys(words))
    if any(w.strip() in ins for w in _GENERIC_URL):
        return [w.strip() for w in _GENERIC_URL]
    return []


def extract_literal_value(instruction: str) -> str | None:
    """Pull an explicit value the user wants set (a URL or a quoted string)."""
    m = _URL_RE.search(instruction)
    if m:
        return m.group(0).rstrip(".,);")
    m = _QUOTED_RE.search(instruction)
    if m:
        return m.group(1).strip()
    return None


def _matches_focus(answer: Answer, question, focus: list[str]) -> bool:
    hay = f"{answer.question_id} {answer.label} {question.maps_to or ''}".lower()
    return any(w in hay for w in focus)


def _apply_change(aset: AnswerSet, ans: Answer, question, new: str, truncated: bool, source: str) -> None:
    ans.value, ans.truncated, ans.source = new, truncated, source
    ans.edited = source == "edited"
    aset.fill_plan = [s for s in aset.fill_plan if s.question_id != ans.question_id]
    step = fill_step_for(question, new)
    if step is not None:
        aset.fill_plan.append(step)


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
    focus = detect_focus(instruction)
    literal = extract_literal_value(instruction)

    changed: list[tuple[str, str]] = []  # (site_id, field label)
    not_found: list[str] = []            # sites lacking a focus-matched field

    for sid in targets:
        site = registry.get_site(sid)
        if site is None:
            continue
        aset = bundle.answer_sets[sid]
        qmap = {q.id: q for q in site.questions}
        practices = get_best_practices(site)
        site_matched = False
        for ans in aset.answers:
            q = qmap.get(ans.question_id)
            if q is None:
                continue
            in_focus = (not focus) or _matches_focus(ans, q, focus)
            if focus and in_focus:
                site_matched = True

            # 1) Direct value-set: user named a field AND supplied a literal value.
            #    Works for ANY field type (incl. url/file), bypassing the LLM.
            if literal and focus and in_focus:
                new, truncated = fit_text(literal, q.max_length)
                if new != ans.value:
                    _apply_change(aset, ans, q, new, truncated, "edited")
                    changed.append((sid, ans.label))
                continue

            # 2) Revision via the LLM/heuristic — only revisable text fields,
            #    restricted to the focus when one was detected.
            if not in_focus or (literal and not focus):
                continue
            if ans.type not in _REVISABLE_TYPES or not ans.value:
                continue
            new = provider.revise_answer(
                question=q, product=product, site=site,
                current_value=ans.value, instruction=instruction, best_practices=practices,
            )
            new, truncated = fit_text(new, q.max_length)
            if new and new != ans.value:
                _apply_change(aset, ans, q, new, truncated, "llm")
                changed.append((sid, ans.label))
        if focus and not site_matched:
            not_found.append(sid)
        bundle.answer_sets[sid] = aset

    summary = _chat_summary(provider.name, focus, literal, changed, not_found, targets)
    scope = "all drafts" if not site_ids else _names(targets)
    changed_sites = list(dict.fromkeys(s for s, _ in changed))
    bundle.chat.append(ChatMessage(role="user", content=instruction, scope=scope))
    bundle.chat.append(
        ChatMessage(role="assistant", content=summary, scope=scope, affected_sites=changed_sites)
    )
    drafts().save(bundle)
    get_memory().remember_instruction(url, instruction, scope, summary)
    return {
        "assistant": summary,
        "changed_fields": len(changed),
        "updated_site_ids": changed_sites,
        "answer_sets": [bundle.answer_sets[s].model_dump() for s in targets],
        "chat": [m.model_dump() for m in bundle.chat],
    }


def _names(site_ids) -> str:
    names = [registry.get_site(s).name for s in site_ids if registry.get_site(s)]
    return ", ".join(names)


def _short(value: str, n: int = 50) -> str:
    return value if len(value) <= n else value[: n - 1] + "…"


def _chat_summary(provider_name, focus, literal, changed, not_found, targets) -> str:
    changed_sites = list(dict.fromkeys(s for s, _ in changed))
    if literal and focus:
        if changed:
            s = f"Set {len(changed)} field(s) to “{_short(literal)}” on: {_names(changed_sites)}."
        else:
            s = f"That field already had that value, or I couldn't find it on {_names(targets)}."
        if not_found:
            s += f" No matching field on: {_names(not_found)}."
        return s
    if literal and not focus:
        return (
            "Tell me which field to set — e.g. “set the demo URL to <link>” or "
            "“set the website to <link>”. I didn't change anything to avoid guessing."
        )
    if changed:
        s = f"Updated {len(changed)} field(s) across {len(changed_sites)} site(s): {_names(changed_sites)}."
        if not_found:
            s += f" (No matching field on: {_names(not_found)}.)"
        return s
    if focus:
        return f"I couldn't find a field matching that on {_names(targets)}, so nothing changed."
    if provider_name == "mock":
        return (
            "No changes applied. The offline assistant handles edits like “shorten”, "
            "“make it more professional”, “add an emoji”, “lead with the benefit”, "
            "“add keywords”, or setting a named field to a value you give (e.g. “set the "
            "demo URL to <link>”). Set OPENAI_API_KEY for free-form rewriting."
        )
    return "No changes were necessary for that instruction."


# -- post-launch learning loop ---------------------------------------------
def record_launch(url: str, site_id: str) -> Launch:
    """Snapshot the copy we're submitting to a site (so outcomes attribute to it)."""
    product = store().load(url)
    if product is None:
        raise LookupError("Scan the product first")
    site = registry.get_site(site_id)
    if site is None:
        raise KeyError(site_id)
    copy = _copy_snapshot(url, site, product)
    launch = launches().record_launch(url, site_id, site.name, copy)
    get_memory().remember_outcome(url, site_id, f"Submitted launch: {copy.tagline}", {"status": "submitted"})
    return launch


def record_outcome(url: str, site_id: str, **fields) -> dict:
    """Append a measured/user-reported outcome and reflect to derive learnings."""
    site = registry.get_site(site_id)
    if site is None:
        raise KeyError(site_id)
    if store().load(url) is None:
        raise LookupError("Scan the product first")
    clean = {k: v for k, v in fields.items() if v not in (None, "")}
    outcome = LaunchOutcome(site_id=site_id, **clean)
    launch = launches().add_outcome(url, site_id, outcome)
    get_memory().remember_outcome(url, site_id, _outcome_summary(outcome), outcome.model_dump())
    learnings = reflect(url, site_id)
    return {"launch": launch.model_dump(), "learnings": [ln.text for ln in learnings]}


def reflect(url: str, site_id: str) -> list[Learning]:
    """Run after-action reasoning over a launch's copy + outcomes → learnings."""
    product = store().load(url)
    site = registry.get_site(site_id)
    launch = launches().load(url).launches.get(site_id)
    if product is None or site is None or launch is None:
        return []
    texts = get_provider().extract_learnings(
        product=product, site=site, copy=launch.submitted_copy, outcomes=launch.outcomes
    )
    learnings = [
        Learning(id=_learning_id(site_id, t), scope="site", site_id=site_id, text=t.strip())
        for t in texts
        if t and t.strip()
    ]
    if learnings:
        launches().add_learnings(url, learnings)
        get_memory().remember_learnings(url, site_id, [ln.text for ln in learnings])
    return learnings


def get_launches(url: str) -> LaunchBook:
    return launches().load(url)


def learnings_payload(url: str, site_id: str = "") -> dict:
    book = launches().load(url)
    feed = launches().learnings_for(site_id) if site_id else []
    return {
        "product": [ln.model_dump() for ln in book.learnings],
        "feed_forward": [ln.model_dump() for ln in feed],
    }


def _learning_id(site_id: str, text: str) -> str:
    return f"{site_id}-{hashlib.sha1(text.encode()).hexdigest()[:8]}"


def _outcome_summary(o: LaunchOutcome) -> str:
    bits: list[str] = [o.status]
    if o.rank:
        bits.append(f"rank #{o.rank}")
    if o.points:
        bits.append(f"{o.points} points")
    if o.comments:
        bits.append(f"{o.comments} comments")
    if o.signups:
        bits.append(f"{o.signups} signups")
    if o.sentiment:
        bits.append(f"{o.sentiment} sentiment")
    if o.notes:
        bits.append(o.notes)
    return ", ".join(str(b) for b in bits if b)


def _copy_snapshot(url: str, site, product: Product) -> CopySnapshot:
    """Capture the copy submitted to a site — the edited draft where present,
    otherwise the product's understanding."""
    snap = CopySnapshot(
        tagline=product.tagline,
        description_short=product.description_short,
        description_long=product.description_long,
        category=(product.categories[0] if product.categories else ""),
        website=product.canonical_url or product.url,
    )
    aset = drafts().get_set(url, site.id)
    if aset is not None:
        for a in aset.answers:
            if not a.value:
                continue
            hay = f"{a.question_id} {a.label}".lower()
            if any(k in hay for k in ("tagline", "headline", "pitch", "one-liner", "one liner", "slogan")):
                snap.tagline = a.value
            elif any(k in hay for k in ("description", "desc", "summary", "about", "overview")):
                if a.type == "textarea" or len(a.value) > len(snap.description_short):
                    snap.description_long = a.value
                else:
                    snap.description_short = a.value
            elif any(k in hay for k in ("categor", "topic")):
                snap.category = a.value
            snap.key_fields[a.question_id] = a.value[:200]
    return snap
