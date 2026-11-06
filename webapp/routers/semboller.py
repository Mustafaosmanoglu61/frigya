from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import i18n
import auth_service
import database
from templates_config import templates
from portfolio_helper import (
    get_portfolios, resolve_portfolio, get_selectable_portfolios, is_super, pf_clause,
)

router = APIRouter()


@router.get("/semboller", response_class=HTMLResponse)
async def semboller(request: Request, yil: Optional[int] = Query(default=None), portfolio: str = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)
    pf_sql, pf_params = pf_clause(portfolio)
    pf_sql_fr, pf_params_fr = pf_clause(portfolio, alias="fr")

    with database.db() as conn:
        # Use portfolio column directly on fifo_results
        available_years = []
        if portfolio:
            available_years = [
                r["tax_year"] for r in
                conn.execute(
                    f"SELECT DISTINCT tax_year FROM fifo_results WHERE user_id=? {pf_sql} ORDER BY tax_year",
                    tuple([user_id] + pf_params)
                ).fetchall()
            ]
        # yil=0 means "all years"; default to latest year on first load (no explicit choice)
        if yil is None and available_years:
            yil = max(available_years)

        # Build year filter clause
        if yil:
            year_sql = "AND tax_year = ?"
            year_params = [yil]
        else:
            year_sql = ""
            year_params = []

        if available_years:
            rows = conn.execute(f"""
                WITH symbol_agg AS (
                    SELECT symbol,
                           MAX(tx_date) AS last_sale_date,
                           COUNT(*) AS total_trades,
                           SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END) AS winning_trades,
                           SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losing_trades,
                           SUM(quantity) AS total_quantity,
                           SUM(sale_proceeds) AS total_proceeds,
                           SUM(cost_basis) AS total_cost,
                           SUM(pnl) AS net_pnl,
                           SUM(CASE WHEN pnl >= 0 THEN pnl ELSE 0 END) AS total_profit,
                           SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss,
                           SUM(eksik_lot) AS eksik_lot_count
                    FROM fifo_results
                    WHERE user_id = ? {pf_sql} {year_sql}
                    GROUP BY symbol
                )
                SELECT sa.symbol,
                       sa.last_sale_date,
                       MAX(CASE WHEN fr.tx_date = sa.last_sale_date THEN fr.sale_price END) AS last_sale_price,
                       MAX(CASE WHEN fr.tx_date = sa.last_sale_date THEN fr.raw_tx_id END) AS last_tx_id,
                       sa.total_trades,
                       sa.winning_trades,
                       sa.losing_trades,
                       sa.total_quantity,
                       sa.total_proceeds,
                       sa.total_cost,
                       sa.net_pnl,
                       sa.total_profit,
                       sa.total_loss,
                       sa.eksik_lot_count,
                       CASE WHEN sa.total_trades > 0
                            THEN CAST(sa.winning_trades AS REAL) / sa.total_trades
                            ELSE 0 END AS success_rate,
                       CASE WHEN sa.total_cost > 0.001
                            THEN sa.net_pnl / sa.total_cost
                            ELSE NULL END AS pnl_pct
                FROM symbol_agg sa
                LEFT JOIN fifo_results fr ON upper(fr.symbol) = upper(sa.symbol)
                                          AND fr.tx_date = sa.last_sale_date
                                          AND fr.user_id = ? {pf_sql_fr} {year_sql}
                GROUP BY sa.symbol, sa.last_sale_date, sa.total_trades, sa.winning_trades,
                         sa.losing_trades, sa.total_quantity, sa.total_proceeds, sa.total_cost,
                         sa.net_pnl, sa.total_profit, sa.total_loss, sa.eksik_lot_count
                HAVING sa.last_sale_date IS NOT NULL
                ORDER BY sa.net_pnl DESC
            """, [user_id] + pf_params + year_params + [user_id] + pf_params_fr + year_params).fetchall()

            totals = conn.execute(f"""
                SELECT
                    COUNT(DISTINCT symbol)  AS symbol_count,
                    COUNT(*)                AS total_trades,
                    SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END) AS winning_trades,
                    SUM(sale_proceeds)      AS total_proceeds,
                    SUM(cost_basis)         AS total_cost,
                    SUM(pnl)                AS net_pnl,
                    SUM(CASE WHEN pnl >= 0 THEN pnl ELSE 0 END) AS total_profit,
                    SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss
                FROM fifo_results WHERE user_id = ? {pf_sql} {year_sql}
            """, [user_id] + pf_params + year_params).fetchone()
        else:
            rows = []
            totals = None

    sym_tags = database.get_symbol_tags(user_id)
    distinct_tags = database.get_distinct_tags(user_id)

    return templates.TemplateResponse("semboller.html", {
        "request": request,
        "rows": rows,
        "totals": totals,
        "yil": yil,
        "available_years": available_years,
        "active": "semboller",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "sym_tags": sym_tags,
        "distinct_tags": distinct_tags,
        "is_super": super_mode,
    })


@router.post("/semboller/sil/{tx_id}")
async def sil_islem_semboller(request: Request, tx_id: int, yil: int = Query(default=0)):
    """Delete transaction from symbols page."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")

    # Süper portföy salt-okunur: silme reddedilir
    if is_super(portfolio):
        return RedirectResponse(
            url=f"/semboller?msg={i18n.tx_q(request, 'Süper portföyde silme yapılamaz')}", status_code=303
        )

    with database.db() as conn:
        # Get transaction info
        tx = conn.execute(
            "SELECT tx_date, symbol FROM raw_transactions WHERE id=? AND user_id=?",
            (tx_id, user_id)
        ).fetchone()

        if not tx:
            return RedirectResponse(url=f"/semboller?msg={i18n.tx_q(request, 'İşlem bulunamadı')}", status_code=303)

        year = int(tx["tx_date"][:4])

        # Delete computed tables first
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        # Delete transaction
        conn.execute("DELETE FROM raw_transactions WHERE id=? AND user_id=?", (tx_id, user_id))

    # Recalculate FIFO
    database.recompute_fifo()

    msg = i18n.tx(request, "{symbol} işlemi silindi", symbol=tx["symbol"])
    return RedirectResponse(
        url=f"/semboller?yil={year}&portfolio={portfolio or ''}&msg={msg}",
        status_code=303,
    )


# ─── GET /api/semboller/{symbol}/detay ────────────────────────────────────
# Semboller tablosunda satıra tıklayınca açılan inline detay için —
# tam sayfaya (/sembol/{symbol}) gitmeden özet + son işlemleri döndürür.
@router.get("/api/semboller/{symbol}/detay")
async def sembol_detay_inline(request: Request, symbol: str, yil: Optional[int] = Query(default=None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    # resolve_portfolio kullanmak süper sentinel'i doğru şekilde ele alır ve
    # /semboller sayfası ziyaret edildiyse session'daki portföye düşer.
    portfolio = resolve_portfolio(request, None, user_id)
    if not portfolio:
        return JSONResponse({"error": i18n.tx(request, "Portföy seçili değil")}, status_code=400)
    pf_sql, pf_params = pf_clause(portfolio)
    sym = symbol.upper().strip()

    year_sql = "AND tax_year=?" if yil else ""
    year_params = [yil] if yil else []

    with database.db() as conn:
        # Gerçekleşen satışlar (yıla filtreli)
        sells = conn.execute(
            f"""SELECT tx_date, quantity, sale_price, sale_proceeds, cost_basis, pnl,
                       pnl_pct, status, eksik_lot, portfolio
                FROM fifo_results
                WHERE user_id=? AND upper(symbol)=? {pf_sql} {year_sql}
                ORDER BY tx_date DESC, id DESC
                LIMIT 25""",
            tuple([user_id, sym] + pf_params + year_params),
        ).fetchall()

        # Açık pozisyon (yıla bakılmaz)
        open_rows = conn.execute(
            f"""SELECT buy_date, quantity, buy_price, cost_basis, portfolio
                FROM open_positions
                WHERE user_id=? AND upper(symbol)=? {pf_sql}
                ORDER BY buy_date DESC, id DESC""",
            tuple([user_id, sym] + pf_params),
        ).fetchall()

        # Son alışlar (referans — 10 kayıt)
        buys = conn.execute(
            f"""SELECT tx_date, quantity, price, total, portfolio
                FROM raw_transactions
                WHERE user_id=? AND upper(symbol)=? AND direction='Alış' {pf_sql}
                ORDER BY tx_date DESC, id DESC
                LIMIT 10""",
            tuple([user_id, sym] + pf_params),
        ).fetchall()

    return JSONResponse({
        "symbol": sym,
        "portfolio": portfolio,
        "yil": yil,
        "sells": [dict(r) for r in sells],
        "opens": [dict(r) for r in open_rows],
        "buys":  [dict(r) for r in buys],
    })
