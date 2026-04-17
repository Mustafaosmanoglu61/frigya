from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from datetime import date, datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import get_portfolios, resolve_portfolio

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
    portfolios = get_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)

    with database.db() as conn:
        if portfolio:
            symbols_raw = conn.execute("""
                SELECT
                    symbol,
                    COUNT(*)        AS lot_count,
                    SUM(quantity)   AS total_qty,
                    SUM(cost_basis) AS total_cost,
                    MIN(buy_date)   AS earliest_buy,
                    MAX(buy_date)   AS latest_buy
                FROM open_positions
                WHERE user_id = ? AND portfolio = ?
                GROUP BY symbol
                ORDER BY total_cost DESC
            """, (user_id, portfolio)).fetchall()

            lots_raw = conn.execute("""
                SELECT symbol, lot_seq, buy_date, quantity, buy_price, cost_basis, is_carry_lot
                FROM open_positions
                WHERE user_id = ? AND portfolio = ?
                ORDER BY symbol, lot_seq
            """, (user_id, portfolio)).fetchall()

            total_cost = conn.execute(
                "SELECT COALESCE(SUM(cost_basis), 0) FROM open_positions WHERE user_id = ? AND portfolio = ?",
                (user_id, portfolio)
            ).fetchone()[0]

            # Realized K/Z per symbol
            realized_map = {}
            realized_rows = conn.execute("""
                SELECT symbol,
                       SUM(pnl) AS net_pnl,
                       SUM(CASE WHEN pnl >= 0 THEN pnl ELSE 0 END) AS total_profit,
                       SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss,
                       COUNT(*) AS trade_count
                FROM fifo_results
                WHERE user_id = ? AND portfolio = ?
                GROUP BY symbol
            """, (user_id, portfolio)).fetchall()
            for r in realized_rows:
                realized_map[r["symbol"]] = {
                    "net_pnl": r["net_pnl"] or 0,
                    "total_profit": r["total_profit"] or 0,
                    "total_loss": r["total_loss"] or 0,
                    "trade_count": r["trade_count"] or 0,
                }

            # Hedef fiyatlar
            targets = database.get_symbol_targets(user_id, portfolio)
        else:
            symbols_raw = []
            lots_raw = []
            total_cost = 0
            realized_map = {}
            targets = {}

    # Enrich symbols with avg_price and days info
    symbols = []
    for s in symbols_raw:
        sym = dict(s)
        sym["avg_price"] = s["total_cost"] / s["total_qty"] if s["total_qty"] > 0 else 0
        sym["days_open"] = _days_since(s["earliest_buy"])
        sym["realized"] = realized_map.get(s["symbol"], {})
        sym["target"] = targets.get(s["symbol"], {})
        symbols.append(sym)

    # Enrich lots with days_since
    lots = []
    for r in lots_raw:
        lot = dict(r)
        lot["days_since"] = _days_since(r["buy_date"])
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
    })
