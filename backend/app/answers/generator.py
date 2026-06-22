"""Answer generator.

Given an analyzed Product and a LaunchSite, produce an AnswerSet: a best-practice
answer for every question plus a concrete ``fill_plan`` the Chrome extension's
fill engine executes. File-upload fields resolve to the product's assets.
"""
from __future__ import annotations

import logging

from ..llm.base import LLMProvider
from ..llm.factory import get_provider
from ..models import Answer, AnswerSet, FillStep, LaunchSite, Product, Question
from .best_practices import get_best_practices
from .fit import fit_text

log = logging.getLogger(__name__)

_ACTION_BY_TYPE = {
    "select": "select",
    "checkbox": "check",
    "file": "upload",
}


def fill_step_for(question: Question, value: str) -> FillStep | None:
    """Build the extension fill step for a question+value (used on edit/revise)."""
    if not question.selectors:
        return None
    return FillStep(
        selectors=question.selectors,
        action=_ACTION_BY_TYPE.get(question.type, "fill"),
        value=value,
        question_id=question.id,
    )


class AnswerGenerator:
    def __init__(self, provider: LLMProvider | None = None, researcher=None, memory=None, learnings=None) -> None:
        self.provider = provider or get_provider()
        self.researcher = researcher
        self.memory = memory  # optional MemoryProvider for recall grounding
        # optional callable: (site_id) -> list[str] of post-launch learnings
        self.learnings = learnings

    def _practices_for(self, product: Product, site: LaunchSite) -> list[str]:
        """Curated best-practices + memory recall + post-launch learnings,
        de-duplicated on normalised text and capped so the prompt stays lean."""
        practices = get_best_practices(site, researcher=self.researcher)
        extra: list[str] = []
        if self.learnings is not None:
            try:
                extra.extend(self.learnings(site.id) or [])
            except Exception:  # noqa: BLE001
                pass
        if self.memory is not None:
            try:
                extra.extend(
                    self.memory.recall(
                        product.url, query=f"{site.name} {product.tagline}".strip(), site_id=site.id
                    )
                )
            except Exception:  # noqa: BLE001
                pass
        seen = {p.strip().lower() for p in practices}
        for e in extra:
            key = (e or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                practices.append(e)
        return practices

    def generate(self, product: Product, site: LaunchSite) -> AnswerSet:
        practices = self._practices_for(product, site)
        answers: list[Answer] = []
        fill_plan: list[FillStep] = []
        notes: list[str] = []

        for q in site.questions:
            if q.type == "file":
                answer, step, note = self._handle_file(q, product)
            else:
                answer, step, note = self._handle_field(q, product, site, practices)

            answers.append(answer)
            if step is not None:
                fill_plan.append(step)
            if note:
                notes.append(note)

        notes.extend(self._auth_notes(site, product))
        return AnswerSet(
            product_url=product.url,
            site_id=site.id,
            site_name=site.name,
            generated_by=self.provider.name,
            answers=answers,
            fill_plan=fill_plan,
            auth=site.auth,
            notes=notes,
        )

    # ------------------------------------------------------------------
    def _handle_field(self, q: Question, product: Product, site: LaunchSite, practices):
        raw = self.provider.generate_answer(
            question=q, product=product, site=site, best_practices=practices
        )
        # Length fitting is centralised here so the `truncated` flag is accurate
        # and shortening always happens at a natural boundary (not mid-word).
        value, truncated = fit_text(raw, q.max_length)
        source = "product" if q.maps_to else "best_practice"
        answer = Answer(
            question_id=q.id,
            label=q.label,
            value=value,
            type=q.type,
            source=source,
            truncated=truncated,
            max_length=q.max_length,
            help=q.help,
            selectors=q.selectors,
        )
        step = fill_step_for(q, value) if value else None
        note = None
        if q.required and not value:
            note = f"Required field '{q.label}' could not be auto-filled — please complete manually."
        return answer, step, note

    def _handle_file(self, q: Question, product: Product):
        asset = self._asset_for(q, product)
        value = ""
        note = None
        if asset:
            value = asset.local_path or asset.url
        else:
            note = f"No asset found for '{q.label}'. Please attach a file manually."
        answer = Answer(
            question_id=q.id,
            label=q.label,
            value=value,
            type="file",
            source="derived",
            help=q.help,
            selectors=q.selectors,
        )
        # Browsers do not allow scripted file selection; the extension opens the
        # picker / pre-fills a URL field and the user confirms the file.
        step = fill_step_for(q, value)
        if asset:
            note = (
                f"'{q.label}': suggested asset is {value}. File pickers require a manual "
                f"confirm click for security."
            )
        return answer, step, note

    @staticmethod
    def _asset_for(q: Question, product: Product):
        label = (q.label + " " + q.id).lower()
        if "logo" in label or "icon" in label:
            return product.assets.logo or product.assets.favicon
        if any(k in label for k in ("screenshot", "gallery", "image", "thumbnail", "media")):
            if product.assets.images:
                return product.assets.images[0]
            return product.assets.logo
        if "video" in label:
            return product.assets.videos[0] if product.assets.videos else None
        return product.assets.logo

    @staticmethod
    def _auth_notes(site: LaunchSite, product: Product) -> list[str]:
        notes: list[str] = []
        a = site.auth
        if a.type == "google":
            notes.append("Sign in with your Google account via the extension, or create one if needed.")
        elif a.type == "github":
            notes.append("This site uses GitHub sign-in (OAuth).")
        elif a.type == "email":
            email = product.maker_email or "your email"
            notes.append(f"Create/sign in with an email account ({email}).")
        elif a.type == "none":
            notes.append("No account required — public submission form.")
        return notes
