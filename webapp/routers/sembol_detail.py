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


@router.get("/sembol/{symbol}", response_class=HTMLResponse)
async def sembol_detail(request: Request, symbol: str, portfolio: str = Query(None), tab: str = Query("all")):
    symbol = symbol.upper()
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)
    pf_sql, pf_params = pf_clause(portfolio)
    pf_sql_fr, pf_params_fr = pf_clause(portfolio, alias="fr")
    active_tab = tab if tab in ("all", "realized", "unrealized") else "all"

    if not portfolio:
        return templates.TemplateResponse("sembol_detail.html", {
            "request": request,
            "symbol": symbol,
            "all_tx": [],
            "realized": [],
            "lot_matches": {},
            "open_pos": [],
            "open_pos_js": [],
            "total_open_cost": 0,
            "total_open_qty": 0,
            "summary": [],
            "overall": None,
            "active": "semboller",
            "portfolios": portfolios,
            "current_portfolio": None,
            "active_tab": active_tab,
            "today": date.today().isoformat(),
            "target": {},
            "target_list": [],
            "sym_tag": "",
            "distinct_tags": [],
            "is_super": False,
        })

    with database.db() as conn:
        # All raw transactions for this symbol (süperde portföy etiketiyle)
        all_tx = conn.execute(f"""
            SELECT id, tx_date, direction, quantity, price, total, source_year, portfolio
            FROM raw_transactions
            WHERE user_id = ? AND upper(symbol) = ? {pf_sql}
            ORDER BY tx_date, id
        """, tuple([user_id, symbol] + pf_params)).fetchall()

        # Realized P&L (all years) — yeniden eskiye sırala
        realized = conn.execute(f"""
            SELECT fr.id, fr.tx_date, fr.quantity, fr.sale_price, fr.sale_proceeds,
                   fr.cost_basis, fr.pnl, fr.pnl_pct, fr.status, fr.eksik_lot,
                   fr.tax_year, fr.portfolio
            FROM fifo_results fr
            WHERE fr.user_id = ? AND upper(fr.symbol) = ? {pf_sql_fr}
            ORDER BY fr.tx_date DESC, fr.rowid DESC
        """, tuple([user_id, symbol] + pf_params_fr)).fetchall()

        # FIFO lot match details for each sale
        lot_matches = {}
        for r in realized:
            matches = conn.execute("""
                SELECT lm.buy_date, lm.buy_price, lm.consumed_qty,
                       lm.consumed_cost, lm.is_carry_lot
                FROM fifo_lot_matches lm
                WHERE lm.fifo_result_id = ?
                ORDER BY lm.id
            """, (r["id"],)).fetchall()
            lot_matches[r["id"]] = matches

        # Open positions for this symbol (süperde portföy etiketiyle)
        open_pos = conn.execute(f"""
            SELECT lot_seq, buy_date, quantity, buy_price, cost_basis, is_carry_lot, portfolio
            FROM open_positions
            WHERE user_id = ? AND upper(symbol) = ? {pf_sql}
            ORDER BY lot_seq
        """, tuple([user_id, symbol] + pf_params)).fetchall()

        # Summary per year — GROUP BY tax_year (süperde portföyler arası toplanır,
        # normal portföyde tek satır olduğu için aynı sonucu verir)
        summary = conn.execute(f"""
            SELECT tax_year,
                   SUM(total_trades)    AS total_trades,
                   SUM(winning_trades)  AS winning_trades,
                   SUM(losing_trades)   AS losing_trades,
                   SUM(total_quantity)  AS total_quantity,
                   SUM(total_proceeds)  AS total_proceeds,
                   SUM(total_cost)      AS total_cost,
                   SUM(net_pnl)         AS net_pnl,
                   SUM(total_profit)    AS total_profit,
                   SUM(total_loss)      AS total_loss,
                   SUM(eksik_lot_count) AS eksik_lot_count,
                   MAX(last_sale_date)  AS last_sale_date,
                   MAX(last_sale_price) AS last_sale_price,
                   CASE WHEN SUM(total_trades) > 0
                        THEN CAST(SUM(winning_trades) AS REAL) / SUM(total_trades)
                        ELSE 0 END AS success_rate,
                   CASE WHEN SUM(total_cost) > 0.001
                        THEN SUM(net_pnl) / SUM(total_cost)
                        ELSE NULL END AS pnl_pct
            FROM symbol_summary
            WHERE user_id = ? AND upper(symbol) = ? {pf_sql}
            GROUP BY tax_year
            ORDER BY tax_year
        """, tuple([user_id, symbol] + pf_params)).fetchall()

        # Totals across all years
        overall = conn.execute(f"""
            SELECT
                SUM(total_proceeds) AS total_proceeds,
                SUM(total_cost)     AS total_cost,
                SUM(net_pnl)        AS net_pnl,
                SUM(total_profit)   AS total_profit,
                SUM(total_loss)     AS total_loss,
                SUM(total_trades)   AS total_trades,
                SUM(winning_trades) AS winning_trades
            FROM symbol_summary WHERE user_id = ? AND upper(symbol) = ? {pf_sql}
        """, tuple([user_id, symbol] + pf_params)).fetchone()

    # Prepare open position data for JS unrealized calc
    open_pos_js = [
        {
            "lot_seq": r["lot_seq"],
            "buy_date": r["buy_date"],
            "quantity": r["quantity"],
            "buy_price": r["buy_price"],
            "cost_basis": r["cost_basis"],
            "is_carry": bool(r["is_carry_lot"]),
        }
        for r in open_pos
    ]

    total_open_cost = sum(r["cost_basis"] for r in open_pos)
    total_open_qty = sum(r["quantity"] for r in open_pos)

    # Hedef/taban fiyat bilgisi
    if super_mode:
        # Süperde: tüm portföylerdeki hedefleri etiketli liste olarak göster (read-only)
        target = {}
        target_list = database.get_symbol_targets_all_portfolios(user_id).get(symbol, [])
    else:
        target = database.get_symbol_target(user_id, portfolio, symbol) or {}
        target_list = []

    # Sembol tag (sektör/klasman) — user-scoped, portfolyodan bağımsız
    sym_tag = database.get_symbol_tag(user_id, symbol) or ""
    distinct_tags = database.get_distinct_tags(user_id)

    return templates.TemplateResponse("sembol_detail.html", {
        "request": request,
        "symbol": symbol,
        "all_tx": all_tx,
        "realized": realized,
        "lot_matches": lot_matches,
        "open_pos": open_pos,
        "open_pos_js": open_pos_js,
        "total_open_cost": total_open_cost,
        "total_open_qty": total_open_qty,
        "summary": summary,
        "overall": overall,
        "target": target,
        "target_list": target_list,
        "sym_tag": sym_tag,
        "distinct_tags": distinct_tags,
        "active": "semboller",
        "portfolios": portfolios,
        "current_portfolio": portfolio,
        "active_tab": active_tab,
        "today": date.today().isoformat(),
        "is_super": super_mode,
    })


@router.post("/sembol/{symbol}/ekle-alis")
async def ekle_alis(
    request: Request,
    symbol: str,
    tx_date: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    portfolio: str = Form(""),
):
    """Add a buy transaction for a symbol."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_portfolios(user_id)
    if portfolio not in portfolios:
        return RedirectResponse(
            url=f"/sembol/{symbol.upper()}?portfolio={portfolio}&msg=Geçersiz%20portföy",
            status_code=303,
        )

    symbol = symbol.upper()
    total = round(quantity * price, 2)
    year = int(tx_date[:4])

    row = {
        "tx_date": tx_date,
        "symbol": symbol,
        "direction": "Alış",
        "quantity": quantity,
        "price": price,
        "total": total,
        "source_type": "MANUAL",
        "source_file": "manuel_alış",
        "source_year": year,
        "portfolio": portfolio,
        "user_id": user_id,
    }

    with database.db() as conn:
        inserted, skipped = insert_rows([row], conn)

    if inserted > 0:
        database.recompute_fifo()
        msg = f"{symbol} Alış {quantity}@${price} eklendi"
    else:
        msg = f"Mükerrer işlem"

    return RedirectResponse(
        url=f"/sembol/{symbol}?portfolio={portfolio}&msg={msg}",
        status_code=303,
    )


@router.post("/sembol/{symbol}/ekle-satis")
async def ekle_satis(
    request: Request,
    symbol: str,
    tx_date: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    portfolio: str = Form(""),
):
    """Add a sell transaction for a symbol."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_portfolios(user_id)
    if portfolio not in portfolios:
        return RedirectResponse(
            url=f"/sembol/{symbol.upper()}?portfolio={portfolio}&msg=Geçersiz%20portföy",
            status_code=303,
        )

    symbol = symbol.upper()
    total = round(quantity * price, 2)
    year = int(tx_date[:4])

    row = {
        "tx_date": tx_date,
        "symbol": symbol,
        "direction": "Satış",
        "quantity": quantity,
        "price": price,
        "total": total,
        "source_type": "MANUAL",
        "source_file": "manuel_satış",
        "source_year": year,
        "portfolio": portfolio,
        "user_id": user_id,
    }

    with database.db() as conn:
        inserted, skipped = insert_rows([row], conn)

    if inserted > 0:
        database.recompute_fifo()
        msg = f"{symbol} Satış {quantity}@${price} eklendi"
    else:
        msg = f"Mükerrer işlem"

    return RedirectResponse(
        url=f"/sembol/{symbol}?portfolio={portfolio}&msg={msg}",
        status_code=303,
    )


@router.post("/sembol/{symbol}/duzenle/{tx_id}")
async def duzenle_islem_sembol(
    request: Request,
    symbol: str,
    tx_id: int,
    tx_date: str = Form(...),
    direction: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    portfolio: str = Form(""),
):
    """Edit an existing transaction and recompute FIFO."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    symbol = symbol.upper()
    if is_super(portfolio):
        return RedirectResponse(
            url=f"/sembol/{symbol}?msg=Süper%20portföyde%20düzenleme%20yapılamaz",
            status_code=303,
        )
    total = round(quantity * price, 2)
    year = int(tx_date[:4])

    with database.db() as conn:
        tx = conn.execute(
            "SELECT id FROM raw_transactions WHERE id=? AND user_id=? AND portfolio=?",
            (tx_id, user_id, portfolio)
        ).fetchone()
        if not tx:
            return RedirectResponse(
                url=f"/sembol/{symbol}?portfolio={portfolio}&msg=İşlem%20bulunamadı",
                status_code=303,
            )

        # Delete computed tables first (full recompute needed anyway)
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        # Update transaction
        conn.execute(
            """UPDATE raw_transactions
               SET tx_date=?, direction=?, quantity=?, price=?, total=?, source_year=?
               WHERE id=? AND user_id=?""",
            (tx_date, direction, quantity, price, total, year, tx_id, user_id),
        )

    database.recompute_fifo()

    msg = f"İşlem güncellendi ve FIFO yeniden hesaplandı"
    return RedirectResponse(
        url=f"/sembol/{symbol}?portfolio={portfolio}&msg={msg}",
        status_code=303,
    )


@router.post("/sembol/{symbol}/sil/{tx_id}")
async def sil_islem_sembol(request: Request, symbol: str, tx_id: int, portfolio: str = Query("")):
    """Delete a transaction (buy or sell) for a symbol."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    symbol = symbol.upper()
    if is_super(portfolio) or is_super(request.session.get("portfolio")):
        return RedirectResponse(
            url=f"/sembol/{symbol}?msg=Süper%20portföyde%20silme%20yapılamaz",
            status_code=303,
        )

    with database.db() as conn:
        # Get transaction info
        tx = conn.execute(
            "SELECT tx_date FROM raw_transactions WHERE id=? AND user_id=?",
            (tx_id, user_id),
        ).fetchone()

        if not tx:
            return RedirectResponse(
                url=f"/sembol/{symbol}?portfolio={portfolio}&msg=İşlem%20bulunamadı",
                status_code=303,
            )

        # Delete computed tables first
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        # Delete transaction
        conn.execute("DELETE FROM raw_transactions WHERE id=? AND user_id=?", (tx_id, user_id))

    # Recalculate FIFO
    database.recompute_fifo()

    msg = f"İşlem silindi"
    return RedirectResponse(
        url=f"/sembol/{symbol}?portfolio={portfolio}&msg={msg}",
        status_code=303,
    )
