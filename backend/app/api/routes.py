"""FastAPI routes for the Software Product Launcher backend."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import settings
from ..llm.factory import get_provider
from ..registry import sites as registry
from . import services

router = APIRouter(prefix="/api")


# -- request bodies ---------------------------------------------------------
class ScanRequest(BaseModel):
    url: str
    force: bool = False


class GenerateRequest(BaseModel):
    url: str
    site_ids: list[str] | None = None
    force_scan: bool = False
    regenerate: bool = True  # False = keep persisted edits/revisions


class EditRequest(BaseModel):
    url: str
    site_id: str
    question_id: str
    value: str


class ChatRequest(BaseModel):
    url: str
    instruction: str
    site_ids: list[str] | None = None  # None/empty = all drafts


# -- meta -------------------------------------------------------------------
@router.get("/health")
def health():
    return {
        "status": "ok",
        "provider": get_provider().name,
        "model": settings.llm_model,
        "sites": len(registry.all_sites()),
    }


# -- launch-site registry ---------------------------------------------------
@router.get("/sites")
def list_sites():
    out = []
    for s in registry.all_sites():
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "description": s.description,
                "tags": s.tags,
                "fee": s.fee,
                "do_follow": s.do_follow,
                "auth_type": s.auth.type,
                "question_count": len(s.questions),
            }
        )
    return {"sites": out, "count": len(out)}


@router.get("/sites/{site_id}")
def get_site(site_id: str):
    site = registry.get_site(site_id)
    if site is None:
        raise HTTPException(404, f"Unknown site '{site_id}'")
    return site.model_dump()


# -- products ---------------------------------------------------------------
@router.post("/scan")
def scan(req: ScanRequest):
    if not req.url.strip():
        raise HTTPException(400, "url is required")
    try:
        product = services.scan(req.url, force=req.force)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return product.public_dict()


@router.get("/products")
def products():
    return {"products": services.list_products()}


@router.get("/product")
def product(url: str = Query(...), full: bool = False):
    p = services.get_product(url)
    if p is None:
        raise HTTPException(404, "Product not found; scan it first")
    return p.model_dump() if full else p.public_dict()


@router.delete("/product")
def delete_product(url: str = Query(...)):
    ok = services.delete_product(url)
    if not ok:
        raise HTTPException(404, "Product not found")
    return {"deleted": True, "url": url}


# -- answer / fill-plan generation -----------------------------------------
@router.post("/generate")
def generate(req: GenerateRequest):
    if not req.url.strip():
        raise HTTPException(400, "url is required")
    try:
        sets = services.generate(
            req.url, req.site_ids, force_scan=req.force_scan, regenerate=req.regenerate
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"answer_sets": [s.model_dump() for s in sets], "count": len(sets)}


@router.get("/drafts")
def drafts(url: str = Query(...)):
    """All persisted drafts + chat history for a product (for the web UI)."""
    bundle = services.get_drafts(url)
    return bundle.model_dump()


@router.patch("/draft/answer")
def edit_answer(req: EditRequest):
    """Apply an inline edit to one field and rebuild its fill step."""
    try:
        aset = services.update_answer(req.url, req.site_id, req.question_id, req.value)
    except KeyError:
        raise HTTPException(404, f"Unknown site '{req.site_id}'")
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return aset.model_dump()


@router.post("/chat")
def chat(req: ChatRequest):
    """Agent-chat: revise drafts across the selected sites per an instruction."""
    if not req.instruction.strip():
        raise HTTPException(400, "instruction is required")
    try:
        result = services.chat_revise(req.url, req.instruction, req.site_ids)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return result


@router.get("/chat/history")
def chat_history(url: str = Query(...)):
    return {"chat": [m.model_dump() for m in services.get_drafts(url).chat]}


@router.get("/answers/{site_id}")
def answers(site_id: str, url: str = Query(...)):
    """Single answer set for one site — the endpoint the extension calls to fill."""
    try:
        aset = services.generate_one(url, site_id)
    except KeyError:
        raise HTTPException(404, f"Unknown site '{site_id}'")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return aset.model_dump()
