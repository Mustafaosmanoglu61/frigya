"""
frigya_core.davranis — genel davranış paternleri (skill analiz/davranis.py'den port).

davranis_data(conn, user_id, portfolio=None, year=None) → dict
"""
from collections import defaultdict
from datetime import datetime


def davranis_data(conn, user_id, portfolio=None, year=None):
    filters = ["fr.user_id = ?"]
    params = [user_id]
    if portfolio:
        filters.append("fr.portfolio = ?")
        params.append(portfolio)
    if year:
        filters.append("fr.tax_year = ?")
        params.append(year)
    where = " AND ".join(filters)

    realized = conn.execute(
        f"""SELECT fr.id, fr.tx_date, upper(fr.symbol) AS symbol, fr.quantity,
                   fr.sale_proceeds, fr.cost_basis, fr.pnl, fr.pnl_pct, fr.tax_year, fr.portfolio
            FROM fifo_results fr WHERE {where} ORDER BY fr.tx_date""",
        tuple(params),
    ).fetchall()

    if not realized:
        return {"meta": {"user_id": user_id}, "note": "Hiç realized işlem yok."}

    hold_days_per_trade = {}
    for r in realized:
        sell_date = r["tx_date"][:10]
        matches = conn.execute(
            "SELECT buy_date FROM fifo_lot_matches WHERE fifo_result_id = ?", (r["id"],),
        ).fetchall()
        days = []
        try:
            sd = datetime.fromisoformat(sell_date)
            for m in matches:
                bd = m["buy_date"]
                if bd:
                    try:
                        days.append((sd - datetime.fromisoformat(bd[:10])).days)
                    except Exception:
                        pass
        except Exception:
            pass
        if days:
            hold_days_per_trade[r["id"]] = sum(days) / len(days)

    tag_rows = conn.execute(
        "SELECT upper(symbol) AS symbol, tag FROM symbol_tags WHERE user_id = ?", (user_id,),
    ).fetchall()
    sym_to_tag = {r["symbol"]: r["tag"] for r in tag_rows}

    total_pnl = sum(r["pnl"] for r in realized)
    wins = [r for r in realized if r["pnl"] >= 0]
    losses = [r for r in realized if r["pnl"] < 0]
    total_proceeds = sum(r["sale_proceeds"] for r in realized)
    total_cost = sum(r["cost_basis"] for r in realized)

    per_sym = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0,
                                   "net_pnl": 0.0, "total_proceeds": 0.0, "total_cost": 0.0})
    for r in realized:
        s = per_sym[r["symbol"]]
        s["trades"] += 1
        s["net_pnl"] += r["pnl"]
        s["total_proceeds"] += r["sale_proceeds"]
        s["total_cost"] += r["cost_basis"]
        if r["pnl"] >= 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    sym_list = [
        {"symbol": k, "tag": sym_to_tag.get(k), **v,
         "win_rate_pct": (v["wins"] * 100.0 / v["trades"]) if v["trades"] else 0,
         "pnl_pct": (v["net_pnl"] * 100.0 / v["total_cost"]) if v["total_cost"] > 0 else None}
        for k, v in per_sym.items()
    ]
    best_syms = sorted(sym_list, key=lambda x: x["net_pnl"], reverse=True)[:10]
    worst_syms = sorted(sym_list, key=lambda x: x["net_pnl"])[:10]
    most_traded = sorted(sym_list, key=lambda x: x["trades"], reverse=True)[:10]

    per_tag = defaultdict(lambda: {"symbols": set(), "trades": 0, "wins": 0, "losses": 0,
                                   "net_pnl": 0.0, "total_cost": 0.0})
    for r in realized:
        tag = sym_to_tag.get(r["symbol"]) or "(etiketsiz)"
        t = per_tag[tag]
        t["symbols"].add(r["symbol"])
        t["trades"] += 1
        t["net_pnl"] += r["pnl"]
        t["total_cost"] += r["cost_basis"]
        if r["pnl"] >= 0:
            t["wins"] += 1
        else:
            t["losses"] += 1
    tag_breakdown = [
        {"tag": k, "unique_symbols": len(v["symbols"]), "trades": v["trades"],
         "wins": v["wins"], "losses": v["losses"],
         "win_rate_pct": (v["wins"] * 100.0 / v["trades"]) if v["trades"] else 0,
         "net_pnl": v["net_pnl"],
         "pnl_pct": (v["net_pnl"] * 100.0 / v["total_cost"]) if v["total_cost"] > 0 else None}
        for k, v in per_tag.items()
    ]
    tag_breakdown.sort(key=lambda x: x["net_pnl"], reverse=True)

    buckets = {"intraday_0g": 0, "short_1_7g": 0, "swing_8_30g": 0, "uzun_30g_plus": 0, "bilinmiyor": 0}
    bucket_pnl = {k: 0.0 for k in buckets}
    for r in realized:
        d = hold_days_per_trade.get(r["id"])
        if d is None:
            b = "bilinmiyor"
        elif d == 0:
            b = "intraday_0g"
        elif d <= 7:
            b = "short_1_7g"
        elif d <= 30:
            b = "swing_8_30g"
        else:
            b = "uzun_30g_plus"
        buckets[b] += 1
        bucket_pnl[b] += r["pnl"]
    hold_dist = [{"bucket": k, "trades": buckets[k], "net_pnl": bucket_pnl[k]} for k in buckets]

    monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
    for r in realized:
        m = monthly[r["tx_date"][:7]]
        m["trades"] += 1
        m["net_pnl"] += r["pnl"]
        if r["pnl"] >= 0:
            m["wins"] += 1
        else:
            m["losses"] += 1
    monthly_list = [{"month": k, **v} for k, v in sorted(monthly.items())]

    pf_open = ""
    pf_open_p = []
    if portfolio:
        pf_open = " AND portfolio = ? "
        pf_open_p = [portfolio]
    open_rows = conn.execute(
        f"""SELECT upper(symbol) AS symbol, SUM(quantity) AS qty, SUM(cost_basis) AS cost
            FROM open_positions WHERE user_id = ? {pf_open} GROUP BY upper(symbol)""",
        tuple([user_id] + pf_open_p),
    ).fetchall()
    open_positions = [
        {"symbol": r["symbol"], "qty": r["qty"], "cost_basis": r["cost"],
         "avg_cost": (r["cost"] / r["qty"] if r["qty"] > 1e-9 else None),
         "tag": sym_to_tag.get(r["symbol"])}
        for r in open_rows
    ]
    open_total_cost = sum(p["cost_basis"] for p in open_positions)
    open_by_tag = defaultdict(float)
    for p in open_positions:
        open_by_tag[p["tag"] or "(etiketsiz)"] += p["cost_basis"]
    open_tag_pct = [
        {"tag": k, "cost_basis": v, "pct_of_open": (v * 100.0 / open_total_cost) if open_total_cost else 0}
        for k, v in sorted(open_by_tag.items(), key=lambda x: -x[1])
    ]

    return {
        "meta": {"user_id": user_id, "portfolio_filter": portfolio, "year_filter": year,
                 "realized_count": len(realized)},
        "overall": {
            "total_trades": len(realized), "wins": len(wins), "losses": len(losses),
            "win_rate_pct": (len(wins) * 100.0 / len(realized)),
            "total_proceeds": total_proceeds, "total_cost": total_cost, "net_pnl": total_pnl,
            "roi_pct": (total_pnl * 100.0 / total_cost) if total_cost > 0 else None,
            "avg_win_pnl": (sum(r["pnl"] for r in wins) / len(wins)) if wins else None,
            "avg_loss_pnl": (sum(r["pnl"] for r in losses) / len(losses)) if losses else None,
            "win_loss_ratio": (
                abs((sum(r["pnl"] for r in wins) / len(wins)) /
                    (sum(r["pnl"] for r in losses) / len(losses)))
                if (wins and losses and sum(r["pnl"] for r in losses) != 0) else None),
            "avg_hold_days": (sum(hold_days_per_trade.values()) / len(hold_days_per_trade))
                              if hold_days_per_trade else None,
        },
        "best_symbols": best_syms,
        "worst_symbols": worst_syms,
        "most_traded_symbols": most_traded,
        "tag_breakdown": tag_breakdown,
        "hold_duration_distribution": hold_dist,
        "monthly_trend": monthly_list,
        "open_positions_snapshot": {
            "total_cost_basis": open_total_cost,
            "symbols": open_positions,
            "sector_concentration": open_tag_pct,
        },
    }
