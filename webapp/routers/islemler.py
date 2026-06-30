from typing import Optional
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import date
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from ingestion import insert_rows
from portfolio_helper import (
    get_portfolios, resolve_portfolio, get_selectable_portfolios, is_super, pf_clause,
)

router = APIRouter()


@router.get("/islemler", response_class=HTMLResponse)
async def islemler(request: Request, yil: Optional[int] = Query(default=None), portfolio: str = Query(None),
                   tab: str = Query("tum"), msg: str = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)
    pf_sql, pf_params = pf_clause(portfolio)
    active_tab = tab if tab in ("tum", "satislar") else "tum"

    with database.db() as conn:
        # Year list: union of FIFO results + raw transactions so the dropdown
        # shows years that may only have buys (no sales).
        available_years = []
        if portfolio:
            available_years = [
                r["yil"] for r in
                conn.execute(
                    f"""
                    SELECT DISTINCT tax_year AS yil FROM fifo_results
                      WHERE user_id=? {pf_sql}
                    UNION
                    SELECT DISTINCT CAST(substr(tx_date, 1, 4) AS INTEGER) AS yil
                      FROM raw_transactions
                      WHERE user_id=? {pf_sql}
                    ORDER BY yil
                    """,
                    tuple([user_id] + pf_params + [user_id] + pf_params),
                ).fetchall()
            ]
        # First load (no explicit yil) → default to latest year
        if yil is None and available_years:
            yil = max(available_years)

        # Build year filters
        if yil:
            year_sql_fifo = "AND tax_year = ?"
            year_sql_raw  = "AND substr(tx_date, 1, 4) = ?"
            year_params   = [yil]
            year_params_raw = [str(yil)]
        else:
            year_sql_fifo = ""
            year_sql_raw  = ""
            year_params   = []
            year_params_raw = []

        rows = []
        totals = None
        all_rows = []

        if portfolio:
            # Sales (FIFO results) — süperde portföy kolonu da gelir
            rows = conn.execute(f"""
                SELECT raw_tx_id, tx_date, symbol, quantity, sale_price, sale_proceeds,
                       cost_basis, pnl, pnl_pct, status, eksik_lot, portfolio
                FROM fifo_results
                WHERE user_id = ? {pf_sql} {year_sql_fifo}
                ORDER BY tx_date, rowid
            """, [user_id] + pf_params + year_params).fetchall()

            totals = conn.execute(f"""
                SELECT
                    COUNT(*)           AS cnt,
                    SUM(sale_proceeds) AS total_proceeds,
                    SUM(cost_basis)    AS total_cost,
                    SUM(pnl)           AS net_pnl,
                    SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN pnl >= 0 THEN pnl ELSE 0 END) AS total_profit,
                    SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss
                FROM fifo_results WHERE user_id = ? {pf_sql} {year_sql_fifo}
            """, [user_id] + pf_params + year_params).fetchone()

            # All raw transactions (alış + satış) — süperde portföy kolonu da gelir
            all_rows = conn.execute(f"""
                SELECT id, tx_date, symbol, direction, quantity, price, total, portfolio
                FROM raw_transactions
                WHERE user_id = ? {pf_sql} {year_sql_raw}
                ORDER BY tx_date DESC, id DESC
            """, [user_id] + pf_params + year_params_raw).fetchall()

    return templates.TemplateResponse("islemler.html", {
        "request": request,
        "rows": rows,
        "all_rows": all_rows,
        "totals": totals,
        "yil": yil,
        "available_years": available_years,
        "active_tab": active_tab,
        "active": "islemler",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "msg": msg,
        "today": date.today().isoformat(),
        "is_super": super_mode,
    })


@router.post("/islemler/ekle")
async def islem_ekle(
    request: Request,
    tx_date: str = Form(...),
    symbol: str = Form(...),
    direction: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    portfolio: str = Form(""),
):
    """Manuel işlem girişi."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_portfolios(user_id)
    if portfolio not in portfolios:
        return RedirectResponse(
            url=f"/islemler?msg=Geçersiz%20portföy",
            status_code=303,
        )

    total = round(quantity * price, 2)
    year = int(tx_date[:4])

    row = {
        "tx_date": tx_date,
        "symbol": symbol.strip().upper(),
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "total": total,
        "source_type": "MANUAL",
        "source_file": "manuel_giris",
        "source_year": year,
        "portfolio": portfolio,
        "user_id": user_id,
    }

    with database.db() as conn:
        inserted, skipped = insert_rows([row], conn)

    if inserted > 0:
        # FIFO yeniden hesapla
        database.recompute_fifo()
        msg = f"{symbol.upper()} {direction} {quantity}@${price} eklendi ve FIFO hesaplandı"
    else:
        msg = f"Mükerrer işlem — zaten kayıtlı"

    return RedirectResponse(
        url=f"/islemler?yil={year}&portfolio={portfolio}&msg={msg}",
        status_code=303,
    )


@router.post("/islemler/duzenle/{tx_id}")
async def islem_duzenle(
    request: Request,
    tx_id: int,
    tx_date: str = Form(...),
    symbol: str = Form(...),
    direction: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    portfolio: str = Form(""),
):
    """Mevcut işlemi düzenle ve FIFO'yu yeniden hesapla."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    if is_super(portfolio) or is_super(request.session.get("portfolio")):
        return RedirectResponse(url="/islemler?msg=Süper%20portföyde%20düzenleme%20yapılamaz", status_code=303)

    total = round(quantity * price, 2)
    year = int(tx_date[:4])
    symbol_clean = symbol.strip().upper()

    with database.db() as conn:
        existing = conn.execute(
            "SELECT id, portfolio FROM raw_transactions WHERE id=? AND user_id=?",
            (tx_id, user_id),
        ).fetchone()
        if not existing:
            return RedirectResponse(url="/islemler?msg=İşlem%20bulunamadı", status_code=303)

        # FIFO sonuçları sıfırlanmalı; mevcut id'lere referans veriyor
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        conn.execute(
            """UPDATE raw_transactions
               SET tx_date=?, symbol=?, direction=?, quantity=?, price=?, total=?,
                   source_year=?, portfolio=COALESCE(NULLIF(?, ''), portfolio)
               WHERE id=? AND user_id=?""",
            (tx_date, symbol_clean, direction, quantity, price, total,
             year, portfolio, tx_id, user_id),
        )

    database.recompute_fifo()

    msg = f"{symbol_clean} {direction} {quantity}@${price} güncellendi"
    return RedirectResponse(
        url=f"/islemler?yil={year}&portfolio={portfolio}&msg={msg}",
        status_code=303,
    )


@router.post("/islemler/sil/{tx_id}")
async def islem_sil(request: Request, tx_id: int):
    """İşlem silme."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if is_super(portfolio):
        return RedirectResponse(url="/islemler?msg=Süper%20portföyde%20silme%20yapılamaz", status_code=303)

    with database.db() as conn:
        # Get transaction info before deletion (ownership check)
        tx = conn.execute(
            "SELECT tx_date, symbol FROM raw_transactions WHERE id=? AND user_id=?",
            (tx_id, user_id),
        ).fetchone()

        if not tx:
            return RedirectResponse(url="/islemler?msg=İşlem%20bulunamadı", status_code=303)

        year = int(tx["tx_date"][:4])
        symbol = tx["symbol"]

        # Delete computed tables first (they reference raw_transactions via foreign keys)
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        # Now delete transaction
        conn.execute("DELETE FROM raw_transactions WHERE id=? AND user_id=?", (tx_id, user_id))

    # Recalculate FIFO
    database.recompute_fifo()

    msg = f"{symbol} işlemi silindi ve FIFO yeniden hesaplandı"
    return RedirectResponse(
        url=f"/islemler?yil={year}&portfolio={portfolio or ''}&msg={msg}",
        status_code=303,
    )
