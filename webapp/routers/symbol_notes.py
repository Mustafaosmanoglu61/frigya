"""Notes API — append/edit/delete kullanıcı notları.
Sembol bazlı (/api/notes) ve portfolyo bazlı (/api/pf-notes) iki scope destekler."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from portfolio_helper import get_portfolios, is_super

router = APIRouter(prefix="/api/notes", tags=["notes"])
pf_router = APIRouter(prefix="/api/pf-notes", tags=["pf-notes"])


@router.get("/counts")
async def notes_counts(request: Request):
    """Returns {SYMBOL: count} for badge rendering on semboller list."""
    user = auth_service.require_current_user(request)
    counts = database.get_symbol_note_counts(int(user["id"]))
    return JSONResponse({"counts": counts})


@router.get("/{symbol}")
async def list_notes(request: Request, symbol: str):
    user = auth_service.require_current_user(request)
    notes = database.list_symbol_notes(int(user["id"]), symbol)
    return JSONResponse({"symbol": symbol.upper(), "notes": notes})


@router.post("/{symbol}")
async def add_note(request: Request, symbol: str):
    user = auth_service.require_current_user(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Not metni boş olamaz"}, status_code=400)
    if len(text) > 5000:
        return JSONResponse({"error": "Not metni 5000 karakteri aşamaz"}, status_code=400)
    note_id = database.insert_symbol_note(int(user["id"]), symbol, text)
    return JSONResponse({"ok": True, "id": note_id})


@router.put("/{note_id}")
async def edit_note(request: Request, note_id: int):
    user = auth_service.require_current_user(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Not metni boş olamaz"}, status_code=400)
    if len(text) > 5000:
        return JSONResponse({"error": "Not metni 5000 karakteri aşamaz"}, status_code=400)
    ok = database.update_symbol_note(int(user["id"]), note_id, text)
    if not ok:
        return JSONResponse({"error": "Not bulunamadı"}, status_code=404)
    return JSONResponse({"ok": True})


@router.delete("/{note_id}")
async def delete_note(request: Request, note_id: int):
    user = auth_service.require_current_user(request)
    ok = database.delete_symbol_note(int(user["id"]), note_id)
    if not ok:
        return JSONResponse({"error": "Not bulunamadı"}, status_code=404)
    return JSONResponse({"ok": True})


# ── Portfolyo notları ──────────────────────────────────────────────────────
def _validate_portfolio(user_id: int, portfolio: str) -> "str | None":
    """Returns error message if invalid, else None. Süper portföy yasak — notlar
    gerçek bir portfolyoya yazılır."""
    if not portfolio or not portfolio.strip():
        return "Portfolyo adı boş olamaz"
    if is_super(portfolio):
        return "Süper portföye not yazılamaz, gerçek bir portfolyo seçin"
    portfolios = get_portfolios(user_id)
    if portfolio not in portfolios:
        return "Bu portfolyo size ait değil"
    return None


@pf_router.get("/counts")
async def pf_notes_counts(request: Request):
    user = auth_service.require_current_user(request)
    counts = database.get_portfolio_note_counts(int(user["id"]))
    return JSONResponse({"counts": counts})


@pf_router.get("/{portfolio}")
async def pf_list_notes(request: Request, portfolio: str):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    err = _validate_portfolio(user_id, portfolio)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    notes = database.list_portfolio_notes(user_id, portfolio)
    return JSONResponse({"portfolio": portfolio, "notes": notes})


@pf_router.post("/{portfolio}")
async def pf_add_note(request: Request, portfolio: str):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    err = _validate_portfolio(user_id, portfolio)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Not metni boş olamaz"}, status_code=400)
    if len(text) > 5000:
        return JSONResponse({"error": "Not metni 5000 karakteri aşamaz"}, status_code=400)
    note_id = database.insert_portfolio_note(user_id, portfolio, text)
    return JSONResponse({"ok": True, "id": note_id})


@pf_router.put("/{note_id}")
async def pf_edit_note(request: Request, note_id: int):
    user = auth_service.require_current_user(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Not metni boş olamaz"}, status_code=400)
    if len(text) > 5000:
        return JSONResponse({"error": "Not metni 5000 karakteri aşamaz"}, status_code=400)
    ok = database.update_portfolio_note(int(user["id"]), note_id, text)
    if not ok:
        return JSONResponse({"error": "Not bulunamadı"}, status_code=404)
    return JSONResponse({"ok": True})


@pf_router.delete("/{note_id}")
async def pf_delete_note(request: Request, note_id: int):
    user = auth_service.require_current_user(request)
    ok = database.delete_portfolio_note(int(user["id"]), note_id)
    if not ok:
        return JSONResponse({"error": "Not bulunamadı"}, status_code=404)
    return JSONResponse({"ok": True})
