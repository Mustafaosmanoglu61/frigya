"""
frigya_core.db — DB okuma fonksiyonları (skill data/db_*.py'den port).

sembol_data(conn, user_id, symbol, portfolio=None) → bir sembolün komple özeti
portfoy_data(conn, user_id, portfolio=None)        → tüm açık pozisyonlar + watchlist
"""
from collections import defaultdict
from datetime import datetime

from .config import html_to_plain, html_short, parse_date


def sembol_data(conn, user_id, symbol, portfolio=None):
    sym = symbol.upper()
    pf_filter = ""
    pf_params = []
    if portfolio:
        pf_filter = " AND portfolio = ? "
        pf_params = [portfolio]

    # 1. Raw trades
    trades_rows = conn.execute(
        f"""SELECT id, tx_date, direction, quantity, price, total,
                   source_type, source_year, portfolio
            FROM raw_transactions
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}
            ORDER BY tx_date, id""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    trades = [
        {"id": r["id"], "date": parse_date(r["tx_date"]), "direction": r["direction"],
         "qty": r["quantity"], "price": r["price"], "total": r["total"],
         "source_type": r["source_type"], "source_year": r["source_year"],
         "portfolio": r["portfolio"]}
        for r in trades_rows
    ]

    # 2. Realized P&L (FIFO)
    pf_filter_fr = pf_filter.replace("portfolio", "fr.portfolio") if pf_filter else ""
    realized_rows = conn.execute(
        f"""SELECT fr.id, fr.tx_date, fr.quantity, fr.sale_price, fr.sale_proceeds,
                   fr.cost_basis, fr.pnl, fr.pnl_pct, fr.status, fr.eksik_lot,
                   fr.tax_year, fr.portfolio
            FROM fifo_results fr
            WHERE fr.user_id = ? AND upper(fr.symbol) = ? {pf_filter_fr}
            ORDER BY fr.tx_date""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    realized = []
    lot_matches = defaultdict(list)
    for r in realized_rows:
        realized.append({
            "id": r["id"], "date": parse_date(r["tx_date"]), "qty": r["quantity"],
            "sale_price": r["sale_price"], "sale_proceeds": r["sale_proceeds"],
            "cost_basis": r["cost_basis"], "pnl": r["pnl"], "pnl_pct": r["pnl_pct"],
            "status": r["status"], "eksik_lot": bool(r["eksik_lot"]),
            "tax_year": r["tax_year"], "portfolio": r["portfolio"],
        })
        mrows = conn.execute(
            """SELECT buy_date, buy_price, consumed_qty, consumed_cost, is_carry_lot
               FROM fifo_lot_matches WHERE fifo_result_id = ?
               ORDER BY buy_date, id""",
            (r["id"],),
        ).fetchall()
        for m in mrows:
            lot_matches[r["id"]].append({
                "buy_date": parse_date(m["buy_date"]), "buy_price": m["buy_price"],
                "consumed_qty": m["consumed_qty"], "consumed_cost": m["consumed_cost"],
                "is_carry_lot": bool(m["is_carry_lot"]),
            })

    # 3. Open positions
    open_rows = conn.execute(
        f"""SELECT lot_seq, buy_date, quantity, buy_price, cost_basis,
                   is_carry_lot, source_year, portfolio
            FROM open_positions
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}
            ORDER BY buy_date, lot_seq""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    open_lots = [
        {"lot_seq": r["lot_seq"], "buy_date": parse_date(r["buy_date"]), "qty": r["quantity"],
         "buy_price": r["buy_price"], "cost_basis": r["cost_basis"],
         "is_carry_lot": bool(r["is_carry_lot"]), "source_year": r["source_year"],
         "portfolio": r["portfolio"]}
        for r in open_rows
    ]
    total_open_qty = sum(l["qty"] for l in open_lots)
    total_open_cost = sum(l["cost_basis"] for l in open_lots)
    avg_cost = (total_open_cost / total_open_qty) if total_open_qty > 1e-9 else None

    # 4. Summary
    summary_rows = conn.execute(
        f"""SELECT tax_year, last_sale_date, last_sale_price,
                   total_trades, winning_trades, losing_trades,
                   total_quantity, total_proceeds, total_cost,
                   net_pnl, total_profit, total_loss, eksik_lot_count, portfolio
            FROM symbol_summary
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}
            ORDER BY tax_year""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    summary = [
        {"year": r["tax_year"], "portfolio": r["portfolio"],
         "last_sale_date": parse_date(r["last_sale_date"]) if r["last_sale_date"] else None,
         "last_sale_price": r["last_sale_price"], "total_trades": r["total_trades"],
         "wins": r["winning_trades"], "losses": r["losing_trades"],
         "win_rate_pct": (r["winning_trades"] * 100.0 / r["total_trades"]) if r["total_trades"] else 0,
         "total_proceeds": r["total_proceeds"], "total_cost": r["total_cost"],
         "net_pnl": r["net_pnl"], "total_profit": r["total_profit"], "total_loss": r["total_loss"]}
        for r in summary_rows
    ]

    # 5. Targets
    target_rows = conn.execute(
        f"""SELECT portfolio, hedef_fiyat, taban_fiyat, stop_fiyat, hedef_dolar_kazanci, updated_at
            FROM symbol_targets
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    targets = [
        {"portfolio": r["portfolio"], "hedef_fiyat": r["hedef_fiyat"], "taban_fiyat": r["taban_fiyat"],
         "stop_fiyat": r["stop_fiyat"], "hedef_dolar_kazanci": r["hedef_dolar_kazanci"],
         "updated_at": r["updated_at"]}
        for r in target_rows
    ]

    # 6a. symbol_notes
    sn_rows = conn.execute(
        """SELECT id, note_text, created_at, updated_at
           FROM symbol_notes WHERE user_id = ? AND upper(symbol) = ?
           ORDER BY created_at DESC, id DESC""",
        (user_id, sym),
    ).fetchall()
    symbol_notes = [
        {"id": r["id"], "created_at": r["created_at"], "updated_at": r["updated_at"], "note": r["note_text"]}
        for r in sn_rows
    ]

    # 6b. portfolio_notes (sembolün geçtiği portföyler)
    seen_pfs = set()
    for src in (trades, targets):
        for x in src:
            if x.get("portfolio"):
                seen_pfs.add(x["portfolio"])
    wl_pfs = conn.execute(
        f"""SELECT DISTINCT portfolio FROM watchlist
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    for r in wl_pfs:
        seen_pfs.add(r["portfolio"])
    if portfolio:
        seen_pfs = {portfolio} & seen_pfs if seen_pfs else {portfolio}

    portfolio_notes = []
    if seen_pfs:
        placeholders = ",".join("?" * len(seen_pfs))
        pn_rows = conn.execute(
            f"""SELECT portfolio, id, note_text, created_at, updated_at
                FROM portfolio_notes
                WHERE user_id = ? AND portfolio IN ({placeholders})
                ORDER BY created_at DESC, id DESC LIMIT 20""",
            tuple([user_id] + list(seen_pfs)),
        ).fetchall()
        portfolio_notes = [
            {"portfolio": r["portfolio"], "id": r["id"], "created_at": r["created_at"],
             "updated_at": r["updated_at"], "note": r["note_text"]}
            for r in pn_rows
        ]

    # 6c. watchlist.notes (legacy HTML)
    wl_notes_rows = conn.execute(
        f"""SELECT portfolio, notes, added_at, notes_migrated_at
            FROM watchlist
            WHERE user_id = ? AND upper(symbol) = ? {pf_filter}
              AND notes IS NOT NULL AND TRIM(notes) <> ''""",
        tuple([user_id, sym] + pf_params),
    ).fetchall()
    watchlist_notes = [
        {"portfolio": r["portfolio"], "added_at": r["added_at"],
         "migrated": bool(r["notes_migrated_at"]), "note_plain": html_to_plain(r["notes"]),
         "has_image": bool(r["notes"] and "<img" in (r["notes"] or "").lower())}
        for r in wl_notes_rows
    ]

    notes = symbol_notes + [
        {"created_at": w["added_at"], "note": w["note_plain"], "_source": "watchlist",
         "portfolio": w["portfolio"], "has_image": w["has_image"]}
        for w in watchlist_notes if w["note_plain"]
    ]

    # 7. Tag
    tag_row = conn.execute(
        "SELECT tag, updated_at FROM symbol_tags WHERE user_id = ? AND upper(symbol) = ?",
        (user_id, sym),
    ).fetchone()
    tag = {"tag": tag_row["tag"], "updated_at": tag_row["updated_at"]} if tag_row else None

    # 8. Behavior (this symbol)
    hold_days_list = []
    for r in realized:
        for m in lot_matches.get(r["id"], []):
            if m["buy_date"]:
                try:
                    sell_d = datetime.fromisoformat(r["date"])
                    buy_d = datetime.fromisoformat(m["buy_date"])
                    hold_days_list.append((sell_d - buy_d).days)
                except Exception:
                    pass

    if realized:
        wins = [r for r in realized if r["pnl"] >= 0]
        losses = [r for r in realized if r["pnl"] < 0]
        best = max(realized, key=lambda r: r["pnl"])
        worst = min(realized, key=lambda r: r["pnl"])
        behavior = {
            "total_realized_trades": len(realized),
            "wins": len(wins), "losses": len(losses),
            "win_rate_pct": (len(wins) * 100.0 / len(realized)) if realized else 0,
            "avg_hold_days": (sum(hold_days_list) / len(hold_days_list)) if hold_days_list else None,
            "avg_win_pnl": (sum(r["pnl"] for r in wins) / len(wins)) if wins else None,
            "avg_loss_pnl": (sum(r["pnl"] for r in losses) / len(losses)) if losses else None,
            "avg_win_pct": (sum((r["pnl_pct"] or 0) for r in wins) / len(wins)) if wins else None,
            "avg_loss_pct": (sum((r["pnl_pct"] or 0) for r in losses) / len(losses)) if losses else None,
            "best_trade": {"date": best["date"], "pnl": best["pnl"], "pnl_pct": best["pnl_pct"]},
            "worst_trade": {"date": worst["date"], "pnl": worst["pnl"], "pnl_pct": worst["pnl_pct"]},
            "total_net_pnl": sum(r["pnl"] for r in realized),
        }
    else:
        behavior = {"total_realized_trades": 0, "note": "Bu sembolde henüz satış (realized) yok."}

    return {
        "meta": {"symbol": sym, "user_id": user_id, "portfolio_filter": portfolio, "tag": tag},
        "trades": trades,
        "realized": realized,
        "lot_matches": {str(k): v for k, v in lot_matches.items()},
        "open_position": {"lots": open_lots, "total_qty": total_open_qty,
                          "total_cost_basis": total_open_cost, "avg_cost": avg_cost},
        "summary": summary,
        "targets": targets,
        "notes": notes,
        "symbol_notes": symbol_notes,
        "portfolio_notes": portfolio_notes,
        "watchlist_notes": watchlist_notes,
        "behavior": behavior,
    }


def portfoy_data(conn, user_id, portfolio=None):
    pf_filter = ""
    pf_params = []
    if portfolio:
        pf_filter = " AND portfolio = ? "
        pf_params = [portfolio]

    pos_rows = conn.execute(
        f"""SELECT upper(symbol) AS symbol, portfolio,
                   SUM(quantity) AS total_qty, SUM(cost_basis) AS total_cost
            FROM open_positions WHERE user_id = ? {pf_filter}
            GROUP BY upper(symbol), portfolio ORDER BY symbol, portfolio""",
        tuple([user_id] + pf_params),
    ).fetchall()

    positions = []
    for r in pos_rows:
        sym, pf = r["symbol"], r["portfolio"]
        qty = r["total_qty"] or 0
        cost = r["total_cost"] or 0
        avg = cost / qty if qty > 1e-9 else None
        target = conn.execute(
            """SELECT hedef_fiyat, taban_fiyat, stop_fiyat, hedef_dolar_kazanci
               FROM symbol_targets WHERE user_id = ? AND upper(symbol) = ? AND portfolio = ?""",
            (user_id, sym, pf),
        ).fetchone()
        note = conn.execute(
            "SELECT notes FROM watchlist WHERE user_id = ? AND upper(symbol) = ? AND portfolio = ?",
            (user_id, sym, pf),
        ).fetchone()
        tag = conn.execute(
            "SELECT tag FROM symbol_tags WHERE user_id = ? AND upper(symbol) = ?", (user_id, sym),
        ).fetchone()
        positions.append({
            "symbol": sym, "portfolio": pf, "total_qty": qty, "total_cost_basis": cost,
            "avg_cost": avg, "tag": tag["tag"] if tag else None,
            "targets": {
                "hedef_fiyat": target["hedef_fiyat"] if target else None,
                "taban_fiyat": target["taban_fiyat"] if target else None,
                "stop_fiyat": target["stop_fiyat"] if target else None,
                "hedef_dolar_kazanci": target["hedef_dolar_kazanci"] if target else None,
            },
            "note_excerpt": html_short(note["notes"]) if note else "",
            "has_note": bool(note and note["notes"]),
        })

    wl_rows = conn.execute(
        f"""SELECT upper(w.symbol) AS symbol, w.portfolio, w.notes, w.added_at
            FROM watchlist w
            WHERE w.user_id = ? {pf_filter.replace('portfolio', 'w.portfolio')}
              AND NOT EXISTS (
                SELECT 1 FROM open_positions op
                WHERE op.user_id = w.user_id AND upper(op.symbol) = upper(w.symbol)
                  AND op.portfolio = w.portfolio)
            ORDER BY w.symbol, w.portfolio""",
        tuple([user_id] + pf_params),
    ).fetchall()
    watchlist_only = []
    for r in wl_rows:
        sym, pf = r["symbol"], r["portfolio"]
        target = conn.execute(
            """SELECT hedef_fiyat, taban_fiyat, stop_fiyat
               FROM symbol_targets WHERE user_id=? AND upper(symbol)=? AND portfolio=?""",
            (user_id, sym, pf),
        ).fetchone()
        tag = conn.execute(
            "SELECT tag FROM symbol_tags WHERE user_id=? AND upper(symbol)=?", (user_id, sym),
        ).fetchone()
        watchlist_only.append({
            "symbol": sym, "portfolio": pf, "tag": tag["tag"] if tag else None,
            "targets": {
                "hedef_fiyat": target["hedef_fiyat"] if target else None,
                "taban_fiyat": target["taban_fiyat"] if target else None,
                "stop_fiyat": target["stop_fiyat"] if target else None,
            },
            "note_excerpt": html_short(r["notes"]), "added_at": r["added_at"],
        })

    return {
        "meta": {"user_id": user_id, "portfolio_filter": portfolio,
                 "open_count": len(positions), "watchlist_only_count": len(watchlist_only),
                 "total_cost_basis_usd": sum(p["total_cost_basis"] for p in positions)},
        "positions": positions,
        "watchlist_only": watchlist_only,
    }
