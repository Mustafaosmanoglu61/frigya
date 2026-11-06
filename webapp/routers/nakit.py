from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import date
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import (
    get_portfolios, get_selectable_portfolios, resolve_portfolio, is_super,
)

router = APIRouter()

EMPTY_BALANCE = {"deposits": 0, "withdrawals": 0, "buys": 0, "sells": 0, "fees": 0, "balance": 0}


@router.get("/nakit", response_class=HTMLResponse)
async def nakit(request: Request, portfolio: str = Query(None), msg: str = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)

    if not portfolio:
        return templates.TemplateResponse("nakit.html", {
            "request": request,
            "balance": EMPTY_BALANCE,
            "rows": [],
            "active": "nakit",
            "portfolios": portfolios,
            "current_portfolio": None,
            "is_super": False,
            "msg": msg,
            "today": date.today().isoformat(),
        })

    pf_for_query = None if super_mode else portfolio
    balance = database.get_cash_balance(user_id, pf_for_query)
    rows = database.get_cash_transactions(user_id, pf_for_query)

    return templates.TemplateResponse("nakit.html", {
        "request": request,
        "balance": balance,
        "rows": rows,
        "active": "nakit",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "is_super": super_mode,
        "msg": msg,
        "today": date.today().isoformat(),
    })


@router.post("/nakit/ekle")
async def nakit_ekle(
    request: Request,
    tx_date: str = Form(...),
    tx_type: str = Form(...),
    amount: float = Form(...),
    note: str = Form(""),
    portfolio: str = Form(""),
):
    """Manuel nakit yatırma/çekme girişi."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_portfolios(user_id)

    if portfolio not in portfolios:
        return RedirectResponse(url="/nakit?msg=Geçersiz%20portföy", status_code=303)
    if tx_type not in ("yatırma", "çekme"):
        return RedirectResponse(url="/nakit?msg=Geçersiz%20işlem%20tipi", status_code=303)
    if amount <= 0:
        return RedirectResponse(url="/nakit?msg=Tutar%20sıfırdan%20büyük%20olmalı", status_code=303)

    database.add_cash_transaction(user_id, portfolio, tx_date, tx_type, amount, note.strip() or None)

    label = "Para yatırma" if tx_type == "yatırma" else "Para çekme"
    msg = f"{label} eklendi: ${amount:,.2f}"
    return RedirectResponse(url=f"/nakit?portfolio={portfolio}&msg={msg}", status_code=303)


@router.post("/nakit/sil/{cash_id}")
async def nakit_sil(request: Request, cash_id: int):
    """Nakit işlemi silme."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if is_super(portfolio):
        return RedirectResponse(url="/nakit?msg=Süper%20portföyde%20silme%20yapılamaz", status_code=303)

    ok = database.delete_cash_transaction(user_id, cash_id)
    msg = "Nakit işlemi silindi" if ok else "İşlem bulunamadı"
    return RedirectResponse(url=f"/nakit?portfolio={portfolio or ''}&msg={msg}", status_code=303)
