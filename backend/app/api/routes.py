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
        sets = services.generate(req.url, req.site_ids, force_scan=req.force_scan)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"answer_sets": [s.model_dump() for s in sets], "count": len(sets)}


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
