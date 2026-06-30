"""
frigya_core.sentez — ana orkestratör. SUBPROCESS YOK — her şey doğrudan fonksiyon çağrısı.

build_sentez(symbol, portfolio=None, market=None, db_path=None, user_id=None, conn=None) → dict

market (opsiyonel passthrough): {
  "teknik": {sma, ema, rsi, macd, daily},
  "haber":  "<news CSV>",
  "meta":   {overview, related, market_status}
}
"""
from datetime import datetime

from . import db as _db
from . import massive as _massive
from .config import open_conn
from .notes import parse_notes_list


def _build_position(dbd):
    op = dbd.get("open_position", {})
    lots = op.get("lots", [])
    return {
        "open_qty": op.get("total_qty", 0),
        "avg_cost": op.get("avg_cost"),
        "cost_basis": op.get("total_cost_basis", 0),
        "lot_count": len(lots),
        "lots": [
            {"date": l["buy_date"], "qty": l["qty"], "price": l["buy_price"],
             "cost": l["cost_basis"], "portfolio": l["portfolio"]}
            for l in lots
        ],
    }


def _build_history(dbd):
    realized = dbd.get("realized", [])
    behavior = dbd.get("behavior", {})
    return {
        "realized_count": behavior.get("total_realized_trades", 0),
        "win_rate_pct": behavior.get("win_rate_pct"),
        "avg_hold_days": behavior.get("avg_hold_days"),
        "net_pnl": behavior.get("total_net_pnl"),
        "avg_win_pnl": behavior.get("avg_win_pnl"),
        "avg_loss_pnl": behavior.get("avg_loss_pnl"),
        "best_trade": behavior.get("best_trade"),
        "worst_trade": behavior.get("worst_trade"),
        "recent_trades": [
            {"date": r["date"], "qty": r["qty"], "price": r["sale_price"],
             "pnl": r["pnl"], "pnl_pct": round((r["pnl_pct"] or 0) * 100, 2),
             "status": r["status"], "portfolio": r["portfolio"]}
            for r in realized[-6:]
        ],
    }


def _build_targets(dbd):
    return [
        {"portfolio": t["portfolio"], "hedef": t.get("hedef_fiyat"), "taban": t.get("taban_fiyat"),
         "stop": t.get("stop_fiyat"), "hedef_dolar_kazanci": t.get("hedef_dolar_kazanci"),
         "updated_at": t.get("updated_at")}
        for t in dbd.get("targets", [])
    ]


def _position_with_market(position, market):
    qty = position.get("open_qty", 0)
    avg = position.get("avg_cost")
    last = market.get("last_close") if market else None
    if qty and avg and last:
        mtm = qty * last
        cost = qty * avg
        unrealized = mtm - cost
        position["mtm_value"] = round(mtm, 2)
        position["mtm_price"] = last
        position["unrealized"] = round(unrealized, 2)
        position["unrealized_pct"] = round(unrealized / cost * 100, 2) if cost else None
        for lot in position.get("lots", []):
            lot_mtm = lot["qty"] * last
            lot["mtm_value"] = round(lot_mtm, 2)
            lot["unrealized"] = round(lot_mtm - lot["cost"], 2)
            lot["unrealized_pct"] = round((lot_mtm - lot["cost"]) / lot["cost"] * 100, 2) if lot["cost"] else None
    return position


def _build_synthesis(symbol, position, history, targets, market, notes_parsed):
    out = {
        "current_state": None, "target_position": None, "note_evaluation": None,
        "behavioral_warning": None, "short_term_view": None, "long_term_view": None,
        "actionable_decision": None, "open_questions": [],
    }

    if position["open_qty"] and position.get("unrealized") is not None:
        sign = "+" if position["unrealized"] >= 0 else ""
        out["current_state"] = (
            f"{position['open_qty']:.0f} adet, ort. maliyet ${position['avg_cost']:.2f}, "
            f"anlık ${position['mtm_price']:.2f} → "
            f"{sign}{position['unrealized']:.2f}$ ({sign}{position['unrealized_pct']}%) unrealized."
        )
    elif position["open_qty"]:
        out["current_state"] = (
            f"{position['open_qty']:.0f} adet açık, ort. maliyet ${position['avg_cost']:.2f}. "
            f"Anlık fiyat verisi yok."
        )
    else:
        out["current_state"] = "Açık pozisyon yok — temiz sayfa."

    if targets and market and market.get("last_close"):
        last = market["last_close"]
        items = []
        for t in targets:
            parts = [f"[{t['portfolio']}]"]
            if t["stop"]:
                parts.append(f"stop ${t['stop']} ({(last - t['stop']) / last * 100:+.1f}% uzak)")
            if t["hedef"]:
                parts.append(f"hedef ${t['hedef']} ({(t['hedef'] - last) / last * 100:+.1f}% uzak)")
            items.append(" · ".join(parts))
        out["target_position"] = " | ".join(items) if items else None

    levels = notes_parsed.get("levels_from_notes", {})
    if levels:
        bits = []
        if levels.get("stop"):    bits.append(f"stop ${levels['stop']}")
        if levels.get("taban"):   bits.append(f"taban ${levels['taban']}")
        if "hedef_min" in levels:  bits.append(f"hedef ${levels['hedef_min']}-${levels['hedef_max']}")
        elif levels.get("hedef"):  bits.append(f"hedef ${levels['hedef']}")
        out["note_evaluation"] = f"Kullanıcının notunda seviyeler: {', '.join(bits)}. Bu seviyelere saygı duyulmalı."
    if notes_parsed.get("latest_earnings_hint"):
        eh = notes_parsed["latest_earnings_hint"]
        out["open_questions"].append(
            f"Notunda earnings ipucu var ({eh.get('date_hint') or 'tarih net değil'}): "
            f"'{eh.get('snippet', '')[:80]}'"
        )

    if history["realized_count"] >= 3:
        wr = history.get("win_rate_pct", 0)
        ah = history.get("avg_hold_days")
        bits = [f"bu sembolde win rate %{wr:.0f}"]
        if ah:
            bits.append(f"ort. hold {ah:.1f}g")
        if history.get("avg_win_pnl") and history.get("avg_loss_pnl"):
            bits.append(f"win/loss oranı {abs(history['avg_win_pnl'] / history['avg_loss_pnl']):.2f}")
        out["behavioral_warning"] = ", ".join(bits) + "."

    if market:
        bits = []
        if market.get("rsi14") is not None:
            r = market["rsi14"]
            label = "aşırı satım" if r < 30 else "aşırı alım" if r > 70 else "nötr"
            bits.append(f"RSI {r:.1f} ({label})")
        if market.get("stoch_pct_k") is not None:
            s = market["stoch_pct_k"]
            if s < 20:
                bits.append(f"Stoch {s:.1f} (dipte)")
            elif s > 80:
                bits.append(f"Stoch {s:.1f} (zirvede)")
        if market.get("macd"):
            h = market["macd"].get("histogram")
            if h is not None:
                bits.append(f"MACD histogram {h:+.2f} ({'bullish' if h > 0 else 'bearish'} momentum)")
        out["short_term_view"] = " | ".join(bits) if bits else None

    if market and market.get("last_close"):
        last = market["last_close"]
        trend = []
        for k, label in [("sma10", "SMA10"), ("sma20", "SMA20"), ("sma50", "SMA50")]:
            v = market.get(k)
            if v:
                trend.append(f"{label} ${v:.2f} {'üstünde' if last > v else 'altında'}")
        dd = market.get("drawdown_from_peak")
        if dd is not None:
            trend.append(f"60g zirveden {dd:.1f}%")
        out["long_term_view"] = " | ".join(trend) if trend else None

    if position["open_qty"] and levels.get("stop") and market and market.get("last_close"):
        last = market["last_close"]
        stop = levels["stop"]
        if last < stop * 1.05:
            out["actionable_decision"] = f"Fiyat ({last:.2f}) notundaki stop seviyesine (${stop}) çok yakın — risk yönetimi kararı gerekir."
        elif "hedef_max" in levels and last >= levels["hedef_max"] * 0.95:
            out["actionable_decision"] = f"Fiyat hedef bölgesine (${levels['hedef_max']}) yaklaştı — yarı kapatma değerlendir."
        else:
            out["actionable_decision"] = f"Pozisyon notundaki seviyelerle uyumlu (${stop}-${levels.get('hedef_max', levels.get('hedef', '?'))}). Aksiyon: tut."

    return out


def build_sentez(symbol, portfolio=None, market=None, prefetched_market=None,
                 db_path=None, user_id=None, conn=None):
    """Tam sentez dict üretir. conn verilmezse içeride açar/kapar.

    market           : MCP CSV passthrough {teknik, haber, meta} (Claude yolu)
    prefetched_market: önceden normalize edilmiş {teknik, news, meta} (webapp REST yolu,
                       massive_fetch.fetch_market çıktısı)
    """
    sym = symbol.upper()
    own_conn = conn is None
    if own_conn:
        conn, _path, user_id = open_conn(db_path, user_id)
    elif user_id is None:
        from .config import detect_user_id
        user_id = detect_user_id(conn)

    try:
        dbd = _db.sembol_data(conn, user_id, sym, portfolio)
    finally:
        if own_conn:
            conn.close()

    notes_parsed = parse_notes_list(dbd.get("symbol_notes", []))

    teknik = news = meta = None
    data_gaps = []
    if prefetched_market and prefetched_market.get("_status") != "no_key":
        teknik = prefetched_market.get("teknik")
        news = prefetched_market.get("news")
        meta = prefetched_market.get("meta")
        if prefetched_market.get("_errors"):
            data_gaps.append("massive kısmi: " + ", ".join(prefetched_market["_errors"].keys()))
        if not (teknik or news or meta):
            data_gaps.append("market verisi alınamadı")
    elif market:
        if market.get("teknik"):
            teknik = _massive.normalize_teknik(market["teknik"], symbol=sym)
        if market.get("haber"):
            news = _massive.normalize_haber(sym, market["haber"], limit=10)
        if market.get("meta"):
            meta = _massive.normalize_meta(sym, market["meta"])
    else:
        if prefetched_market and prefetched_market.get("_status") == "no_key":
            data_gaps.append("MASSIVE_API_KEY yok — DB-only analiz")
        else:
            data_gaps.append("market verisi yok (passthrough geçilmedi)")

    position = _build_position(dbd)
    if teknik:
        position = _position_with_market(position, teknik)

    history = _build_history(dbd)
    targets = _build_targets(dbd)
    synthesis = _build_synthesis(sym, position, history, targets, teknik, notes_parsed)

    return {
        "meta": {
            "symbol": sym,
            "tag": (dbd.get("meta", {}).get("tag") or {}).get("tag") if dbd.get("meta") else None,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "portfolio_filter": portfolio,
        },
        "position": position,
        "frigya_history": history,
        "targets": targets,
        "market": teknik or {"_status": "not_fetched"},
        "notes": {
            "symbol_notes_raw": dbd.get("symbol_notes", []),
            "portfolio_notes_raw": dbd.get("portfolio_notes", []),
            "parsed_overlay": notes_parsed.get("levels_from_notes", {}),
            "earnings_hint": notes_parsed.get("latest_earnings_hint"),
            "thesis_keywords": notes_parsed.get("thesis_keywords", []),
            "macro_mentions": notes_parsed.get("macro_mentions", []),
        },
        "news": news,
        "company_meta": meta,
        "synthesis": synthesis,
        "data_gaps": data_gaps,
    }
