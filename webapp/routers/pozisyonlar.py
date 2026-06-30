from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from datetime import date, datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import (
    get_portfolios, resolve_portfolio, get_selectable_portfolios, is_super, pf_clause,
)

router = APIRouter()


def _days_since(date_str: str) -> int:
    """Calculate days since a date string (YYYY-MM-DD)."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 0


@router.get("/pozisyonlar", response_class=HTMLResponse)
async def pozisyonlar(request: Request, portfolio: str = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)
    pf_sql, pf_params = pf_clause(portfolio)

    with database.db() as conn:
        if portfolio:
            symbols_raw = conn.execute(f"""
                SELECT
                    symbol,
                    COUNT(*)        AS lot_count,
                    SUM(quantity)   AS total_qty,
                    SUM(cost_basis) AS total_cost,
                    MIN(buy_date)   AS earliest_buy,
                    MAX(buy_date)   AS latest_buy
                FROM open_positions
                WHERE user_id = ? {pf_sql}
                GROUP BY symbol
                ORDER BY total_cost DESC
            """, tuple([user_id] + pf_params)).fetchall()

            # Süperde lot satırlarında portföy etiketi de göster
            lots_raw = conn.execute(f"""
                SELECT symbol, lot_seq, buy_date, quantity, buy_price, cost_basis, is_carry_lot, portfolio
                FROM open_positions
                WHERE user_id = ? {pf_sql}
                ORDER BY symbol, lot_seq
            """, tuple([user_id] + pf_params)).fetchall()

            total_cost = conn.execute(
                f"SELECT COALESCE(SUM(cost_basis), 0) FROM open_positions WHERE user_id = ? {pf_sql}",
                tuple([user_id] + pf_params)
            ).fetchone()[0]

            # Realized K/Z per symbol
            realized_map = {}
            realized_rows = conn.execute(f"""
                SELECT symbol,
                       SUM(pnl) AS net_pnl,
                       SUM(CASE WHEN pnl >= 0 THEN pnl ELSE 0 END) AS total_profit,
                       SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss,
                       COUNT(*) AS trade_count
                FROM fifo_results
                WHERE user_id = ? {pf_sql}
                GROUP BY symbol
            """, tuple([user_id] + pf_params)).fetchall()
            for r in realized_rows:
                realized_map[r["symbol"]] = {
                    "net_pnl": r["net_pnl"] or 0,
                    "total_profit": r["total_profit"] or 0,
                    "total_loss": r["total_loss"] or 0,
                    "trade_count": r["trade_count"] or 0,
                }

            # Hedef fiyatlar — süperde portföye özgü olduğu için boş geçilir
            targets = {} if super_mode else database.get_symbol_targets(user_id, portfolio)
        else:
            symbols_raw = []
            lots_raw = []
            total_cost = 0
            realized_map = {}
            targets = {}

    # Bugün alınan lotların sembol bazında adet/maliyet toplamı. Günlük K/Z'de
    # bugün alınan paylar dünkü kapanıştan değil ALIŞ fiyatından ölçülmeli
    # (dün o paya sahip değildin) — aksi halde alıştan önceki hareket fazladan
    # günlük kâr gibi sayılır.
    today_by_symbol: dict = {}
    for r in lots_raw:
        if _days_since(r["buy_date"]) == 0:
            agg = today_by_symbol.setdefault(r["symbol"], {"qty": 0.0, "cost": 0.0})
            agg["qty"] += r["quantity"] or 0
            agg["cost"] += r["cost_basis"] or 0

    # Enrich symbols with avg_price and days info
    symbols = []
    for s in symbols_raw:
        sym = dict(s)
        sym["avg_price"] = s["total_cost"] / s["total_qty"] if s["total_qty"] > 0 else 0
        sym["days_open"] = _days_since(s["earliest_buy"])
        sym["realized"] = realized_map.get(s["symbol"], {})
        sym["target"] = targets.get(s["symbol"], {})
        t = today_by_symbol.get(s["symbol"], {"qty": 0.0, "cost": 0.0})
        sym["today_qty"] = t["qty"]
        sym["today_cost"] = t["cost"]
        symbols.append(sym)

    # Enrich lots with days_since
    lots = []
    for r in lots_raw:
        lot = dict(r)
        lot["days_since"] = _days_since(r["buy_date"])
        lot["is_today"] = lot["days_since"] == 0
        lot["target"] = targets.get(r["symbol"], {})
        lots.append(lot)

    return templates.TemplateResponse("pozisyonlar.html", {
        "request": request,
        "symbols": symbols,
        "lots": lots,
        "total_cost": total_cost,
        "targets": targets,
        "active": "pozisyonlar",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "is_super": super_mode,
    })
