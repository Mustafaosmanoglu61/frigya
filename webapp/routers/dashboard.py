from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import (
    get_portfolios, resolve_portfolio, get_selectable_portfolios, is_super, pf_clause,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, portfolio: str = Query(None), year: int = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)

    if not portfolio:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "kpi": {"total_proceeds": 0, "net_pnl": 0, "total_trades": 0, "wins": 0, "total_loss": 0},
            "open_symbols": 0,
            "success_rate": None,
            "years": [],
            "months": [],
            "monthly_pnl": [],
            "weeks": [],
            "weekly_pnl": [],
            "cumulative": [],
            "top_syms": [],
            "distribution": [],
            "sym_tags": {},
            "realized_by_symbol": {},
            "realized_cost_by_symbol": {},
            "active": "dashboard",
            "portfolios": portfolios,
            "current_portfolio": None,
            "is_super": False,
        })

    # Süper-aware portföy filtresi parçası
    pf_sql, pf_params = pf_clause(portfolio)

    with database.db() as conn:
        # Mevcut yıllar
        available_years = [
            r["tax_year"] for r in conn.execute(
                f"SELECT DISTINCT tax_year FROM fifo_results WHERE user_id=? {pf_sql} ORDER BY tax_year",
                tuple([user_id] + pf_params)
            ).fetchall()
        ]

        year_filter = year if year in available_years else None
        base_filter = "user_id = ? " + pf_sql + (" AND tax_year = ?" if year_filter else "")
        base_params = tuple([user_id] + pf_params + ([year_filter] if year_filter else []))

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
            f"SELECT COUNT(DISTINCT symbol) AS cnt FROM open_positions WHERE user_id = ? {pf_sql}",
            tuple([user_id] + pf_params)
        ).fetchone()["cnt"]

        # Açık pozisyon dağılımı — sembol bazında qty + maliyet (portföyler arası SUM)
        # Pasta grafiği için: bir taraf maliyete göre (statik), diğer taraf
        # mevcut piyasa değerine göre (JS tarafında fiyat cache'i ile güncellenir).
        distribution_rows = conn.execute(f"""
            SELECT symbol,
                   SUM(quantity)   AS qty,
                   SUM(cost_basis) AS cost
            FROM open_positions
            WHERE user_id = ? {pf_sql}
            GROUP BY symbol
            HAVING qty > 0
            ORDER BY cost DESC
        """, tuple([user_id] + pf_params)).fetchall()
        distribution = [
            {
                "symbol": r["symbol"],
                "qty":    round(r["qty"], 6),
                "cost":   round(r["cost"], 2),
            }
            for r in distribution_rows
        ]

        monthly = conn.execute(f"""
            SELECT
                strftime('%Y-%m', tx_date) AS month,
                SUM(pnl) AS monthly_pnl
            FROM fifo_results WHERE {base_filter}
            GROUP BY month
            ORDER BY month
        """, base_params).fetchall()

        # Haftalık — pazartesi başlangıçlı hafta etiketi (YYYY-MM-DD)
        weekly = conn.execute(f"""
            SELECT
                date(tx_date, '-' || ((strftime('%w', tx_date) + 6) % 7) || ' days') AS week_start,
                SUM(pnl) AS weekly_pnl
            FROM fifo_results WHERE {base_filter}
            GROUP BY week_start
            ORDER BY week_start
        """, base_params).fetchall()

        top_syms = conn.execute(f"""
            SELECT symbol, SUM(pnl) AS sym_pnl
            FROM fifo_results WHERE {base_filter}
            GROUP BY symbol
            ORDER BY ABS(SUM(pnl)) DESC
            LIMIT 15
        """, base_params).fetchall()

        years = conn.execute(f"""
            SELECT
                tax_year,
                SUM(sale_proceeds)                              AS proceeds,
                SUM(pnl)                                        AS net_pnl,
                COUNT(*)                                        AS trades,
                SUM(CASE WHEN pnl >= 0 THEN 1 ELSE 0 END)      AS wins,
                SUM(CASE WHEN pnl >= 0 THEN pnl  ELSE 0 END)   AS total_profit,
                SUM(CASE WHEN pnl <  0 THEN ABS(pnl) ELSE 0 END) AS total_loss
            FROM fifo_results WHERE user_id = ? {pf_sql}
            GROUP BY tax_year
            ORDER BY tax_year
        """, tuple([user_id] + pf_params)).fetchall()

    months = [r["month"] for r in monthly]
    monthly_pnl = [round(r["monthly_pnl"], 2) for r in monthly]

    weeks = [r["week_start"] for r in weekly]
    weekly_pnl = [round(r["weekly_pnl"], 2) for r in weekly]

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

    sym_tags = database.get_symbol_tags(user_id)

    # Sembol bazında realized K/Z + realized maliyet bazı — seçili yıla göre filtrele
    rg_year_sql = " AND tax_year = ?" if year_filter else ""
    rg_params = tuple([user_id] + pf_params + ([year_filter] if year_filter else []))
    with database.db() as conn:
        rg_rows = conn.execute(
            f"""SELECT symbol, SUM(pnl) AS realized, SUM(cost_basis) AS realized_cost
                FROM fifo_results
                WHERE user_id = ? {pf_sql}{rg_year_sql}
                GROUP BY symbol""",
            rg_params,
        ).fetchall()
    realized_by_symbol = {r["symbol"].upper(): round(r["realized"] or 0, 2) for r in rg_rows}
    realized_cost_by_symbol = {r["symbol"].upper(): round(r["realized_cost"] or 0, 2) for r in rg_rows}

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
        "weeks": weeks,
        "weekly_pnl": weekly_pnl,
        "cumulative": cumulative,
        "top_syms": [{"symbol": r["symbol"], "pnl": round(r["sym_pnl"], 2)} for r in top_syms],
        "distribution": distribution,
        "sym_tags": sym_tags,
        "realized_by_symbol": realized_by_symbol,
        "realized_cost_by_symbol": realized_cost_by_symbol,
        "active": "dashboard",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "is_super": super_mode,
    })
