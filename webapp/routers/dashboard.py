from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import get_portfolios, resolve_portfolio

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, portfolio: str = Query(None), year: int = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)

    if not portfolio:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "kpi": {"total_proceeds": 0, "net_pnl": 0, "total_trades": 0, "wins": 0, "total_loss": 0},
            "open_symbols": 0,
            "success_rate": None,
            "years": [],
            "months": [],
            "monthly_pnl": [],
            "cumulative": [],
            "top_syms": [],
            "active": "dashboard",
            "portfolios": portfolios,
            "current_portfolio": None,
        })

    with database.db() as conn:
        # Mevcut yıllar
        available_years = [
            r["tax_year"] for r in conn.execute(
                "SELECT DISTINCT tax_year FROM fifo_results WHERE user_id=? AND portfolio=? ORDER BY tax_year",
                (user_id, portfolio)
            ).fetchall()
        ]

        year_filter = year if year in available_years else None
        base_filter = "user_id = ? AND portfolio = ?" + (" AND tax_year = ?" if year_filter else "")
        base_params = (user_id, portfolio, year_filter) if year_filter else (user_id, portfolio)

        kpi = conn.execute(f"""
            SELECT
                SUM(sale_proceeds) AS total_proceeds,
                SUM(pnl)           AS net_pnl,
                COUNT(*)           AS total_trades,
                SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) AS total_loss
            FROM fifo_results WHERE {base_filter}
        """, base_params).fetchone()

        open_symbols = conn.execute(
            "SELECT COUNT(DISTINCT symbol) AS cnt FROM open_positions WHERE user_id = ? AND portfolio = ?",
            (user_id, portfolio)
        ).fetchone()["cnt"]

        monthly = conn.execute(f"""
            SELECT
                strftime('%Y-%m', tx_date) AS month,
                SUM(pnl) AS monthly_pnl
            FROM fifo_results WHERE {base_filter}
            GROUP BY month
            ORDER BY month
        """, base_params).fetchall()

        top_syms = conn.execute(f"""
            SELECT symbol, SUM(pnl) AS sym_pnl
            FROM fifo_results WHERE {base_filter}
            GROUP BY symbol
            ORDER BY ABS(SUM(pnl)) DESC
            LIMIT 15
        """, base_params).fetchall()

        years = conn.execute("""
            SELECT
                tax_year,
                SUM(sale_proceeds)                              AS proceeds,
                SUM(pnl)                                        AS net_pnl,
                COUNT(*)                                        AS trades,
                SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END)      AS wins,
                SUM(CASE WHEN pnl >= 0 THEN pnl  ELSE 0 END)   AS total_profit,
                SUM(CASE WHEN pnl <  0 THEN ABS(pnl) ELSE 0 END) AS total_loss
            FROM fifo_results WHERE user_id = ? AND portfolio = ?
            GROUP BY tax_year
            ORDER BY tax_year
        """, (user_id, portfolio)).fetchall()

    months = [r["month"] for r in monthly]
    monthly_pnl = [round(r["monthly_pnl"], 2) for r in monthly]

    cumulative = []
    running = 0.0
    for v in monthly_pnl:
        running += v
        cumulative.append(round(running, 2))

    # Normalize kpi — SQL SUM() returns None for empty sets
    kpi_safe = {
        "total_proceeds": (kpi["total_proceeds"] or 0) if kpi else 0,
        "net_pnl":        (kpi["net_pnl"]        or 0) if kpi else 0,
        "total_trades":   (kpi["total_trades"]    or 0) if kpi else 0,
        "wins":           (kpi["wins"]            or 0) if kpi else 0,
        "total_loss":     (kpi["total_loss"]      or 0) if kpi else 0,
    }

    success_rate = None
    if kpi_safe["total_trades"]:
        success_rate = round(kpi_safe["wins"] / kpi_safe["total_trades"] * 100, 1)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "kpi": kpi_safe,
        "open_symbols": open_symbols,
        "success_rate": success_rate,
        "years": years,
        "available_years": available_years,
        "selected_year": year_filter,
        "months": months,
        "monthly_pnl": monthly_pnl,
        "cumulative": cumulative,
        "top_syms": [{"symbol": r["symbol"], "pnl": round(r["sym_pnl"], 2)} for r in top_syms],
        "active": "dashboard",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
    })
