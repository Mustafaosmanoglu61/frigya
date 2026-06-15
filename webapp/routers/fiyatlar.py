"""Fiyatlar & İzleme Listesi router."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from portfolio_helper import (
    get_portfolios, resolve_portfolio, get_selectable_portfolios, is_super, pf_clause,
)

router = APIRouter()


# ─── GET /fiyatlar ────────────────────────────────────────────────────────────

@router.get("/fiyatlar", response_class=HTMLResponse)
async def fiyatlar(
    request: Request,
    portfolio: Optional[str] = Query(None),
    tab: str = Query("pozisyonlar"),
):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    portfolio = resolve_portfolio(request, portfolio, user_id)
    super_mode = is_super(portfolio)
    pf_sql, pf_params = pf_clause(portfolio)
    pf_sql_op, pf_params_op = pf_clause(portfolio, alias="op")

    def _days_since(date_str):
        if not date_str:
            return None
        try:
            return (date.today() - datetime.strptime(date_str[:10], '%Y-%m-%d').date()).days
        except Exception:
            return None

    with database.db() as conn:
        if portfolio:
            # Açık pozisyonlar — portföyler arası sembol bazında toplama
            positions = conn.execute(
                f"""
                SELECT op.symbol,
                       SUM(op.quantity)   AS total_qty,
                       SUM(op.cost_basis) AS total_cost,
                       SUM(op.cost_basis) / NULLIF(SUM(op.quantity), 0) AS avg_buy_price,
                       MAX(op.buy_date)   AS last_buy_date,
                       (SELECT op2.buy_price FROM open_positions op2
                        WHERE op2.user_id = op.user_id AND op2.symbol = op.symbol
                        ORDER BY op2.buy_date DESC, op2.lot_seq DESC LIMIT 1) AS last_buy_price
                FROM open_positions op
                WHERE op.user_id = ? {pf_sql_op}
                GROUP BY op.symbol
                ORDER BY total_cost DESC
                """,
                tuple([user_id] + pf_params_op),
            ).fetchall()

            # Gerçekleşen K/Z özeti (sembol bazlı, tüm yıllar)
            realized_summary = {}
            for row in conn.execute(
                f"""
                SELECT symbol,
                       SUM(net_pnl)        AS net_pnl,
                       SUM(total_profit)    AS total_profit,
                       SUM(total_loss)      AS total_loss,
                       SUM(total_trades)    AS total_trades,
                       SUM(winning_trades)  AS winning_trades,
                       SUM(total_proceeds)  AS total_proceeds,
                       SUM(total_cost)      AS total_cost,
                       MAX(last_sale_date)  AS last_sale_date,
                       MAX(last_sale_price) AS last_sale_price
                FROM symbol_summary
                WHERE user_id = ? {pf_sql}
                GROUP BY symbol
                """,
                tuple([user_id] + pf_params),
            ).fetchall():
                realized_summary[row["symbol"]] = dict(row)

            # Portföy toplam gerçekleşen K/Z (pie chart için)
            portfolio_pnl = conn.execute(
                f"""
                SELECT COALESCE(SUM(total_profit), 0) AS total_profit,
                       COALESCE(SUM(total_loss), 0)   AS total_loss,
                       COALESCE(SUM(net_pnl), 0)      AS net_pnl,
                       COALESCE(SUM(total_trades), 0)  AS total_trades,
                       COALESCE(SUM(winning_trades), 0) AS winning_trades
                FROM symbol_summary
                WHERE user_id = ? {pf_sql}
                """,
                tuple([user_id] + pf_params),
            ).fetchone()

            if super_mode:
                # Süper: tüm portföylerin watchlist'i birleşik (sembol bazında tekil),
                # hangi portföylerde olduğu etiketle. Alış/satış/pozisyon bilgileri user
                # genelinde son kayıttan (portföyden bağımsız) alınır.
                watchlist_raw = conn.execute(
                    """
                    SELECT
                        MIN(w.id) AS id, w.symbol,
                        GROUP_CONCAT(DISTINCT w.portfolio) AS portfolios,
                        MAX(w.notes) AS notes, MIN(w.added_at) AS added_at,
                        (SELECT rt.price FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_price,
                        (SELECT rt.quantity FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_qty,
                        (SELECT rt.total FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_total,
                        (SELECT rt.tx_date FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_date,
                        (SELECT rt.price FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_price,
                        (SELECT rt.quantity FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_qty,
                        (SELECT rt.total FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_total,
                        (SELECT rt.tx_date FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_date,
                        (SELECT fr.pnl_pct FROM fifo_results fr
                         WHERE fr.user_id=w.user_id AND fr.symbol=w.symbol
                         ORDER BY fr.tx_date DESC LIMIT 1) AS last_pnl_pct,
                        (SELECT SUM(op.cost_basis) / NULLIF(SUM(op.quantity), 0)
                         FROM open_positions op
                         WHERE op.user_id=w.user_id AND op.symbol=w.symbol) AS avg_cost,
                        (SELECT SUM(op.quantity)
                         FROM open_positions op
                         WHERE op.user_id=w.user_id AND op.symbol=w.symbol) AS total_qty
                    FROM watchlist w
                    WHERE w.user_id = ?
                    GROUP BY w.symbol
                    ORDER BY MIN(w.added_at) DESC
                    """,
                    (user_id,),
                ).fetchall()
            else:
                # Watchlist — geçmiş işlem verisiyle zenginleştirilmiş (tek portföy)
                watchlist_raw = conn.execute(
                    """
                    SELECT
                        w.id, w.symbol, w.notes, w.added_at,
                        (SELECT rt.price FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_price,
                        (SELECT rt.quantity FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_qty,
                        (SELECT rt.total FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_total,
                        (SELECT rt.tx_date FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Alış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_buy_date,
                        (SELECT rt.price FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_price,
                        (SELECT rt.quantity FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_qty,
                        (SELECT rt.total FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_total,
                        (SELECT rt.tx_date FROM raw_transactions rt
                         WHERE rt.user_id=w.user_id AND rt.portfolio=w.portfolio
                           AND rt.symbol=w.symbol AND rt.direction='Satış'
                         ORDER BY rt.tx_date DESC LIMIT 1) AS last_sell_date,
                        (SELECT fr.pnl_pct FROM fifo_results fr
                         WHERE fr.user_id=w.user_id AND fr.portfolio=w.portfolio
                           AND fr.symbol=w.symbol
                         ORDER BY fr.tx_date DESC LIMIT 1) AS last_pnl_pct,
                        (SELECT SUM(op.cost_basis) / NULLIF(SUM(op.quantity), 0)
                         FROM open_positions op
                         WHERE op.user_id=w.user_id AND op.portfolio=w.portfolio
                           AND op.symbol=w.symbol) AS avg_cost,
                        (SELECT SUM(op.quantity)
                         FROM open_positions op
                         WHERE op.user_id=w.user_id AND op.portfolio=w.portfolio
                           AND op.symbol=w.symbol) AS total_qty
                    FROM watchlist w
                    WHERE w.user_id = ? AND w.portfolio = ?
                    ORDER BY w.added_at DESC
                    """,
                    (user_id, portfolio),
                ).fetchall()

            watchlist = []
            for w in watchlist_raw:
                d = dict(w)
                d['last_buy_days']  = _days_since(d.get('last_buy_date'))
                d['last_sell_days'] = _days_since(d.get('last_sell_date'))
                watchlist.append(d)
        else:
            positions = []
            realized_summary = {}
            portfolio_pnl = None
            watchlist = []

    # Hedef/taban fiyatlar — süperde portföy etiketli liste (read-only)
    if not portfolio:
        targets = {}
        targets_all = {}
    elif super_mode:
        targets = {}
        targets_all = database.get_symbol_targets_all_portfolios(user_id)
    else:
        targets = database.get_symbol_targets(user_id, portfolio)
        targets_all = {}

    return templates.TemplateResponse(
        "fiyatlar.html",
        {
            "request":            request,
            "positions":          positions,
            "watchlist":          watchlist,
            "targets":            targets,
            "targets_all":        targets_all,
            "realized_summary":   realized_summary if portfolio else {},
            "portfolio_pnl":      portfolio_pnl,
            "active_tab":         tab,
            "active":             "fiyatlar",
            "portfolios":         portfolios,
            "current_portfolio":  portfolio,
            "is_super":           super_mode,
        },
    )


# ─── POST /api/fiyatlar/guncelle ─────────────────────────────────────────────

@router.post("/api/fiyatlar/guncelle")
async def fiyatlar_guncelle(request: Request):
    """Tüm açık pozisyon + watchlist sembollerini yfinance'dan çekip JSON olarak döner."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        return JSONResponse({"ok": True, "prices": {}, "fetched_at": _now()})

    # Süperde tüm portföylerin sembolleri çekilir (portföy filtresi düşer)
    pf_sql, pf_params = pf_clause(portfolio)

    with database.db() as conn:
        pos_syms = [
            r["symbol"] for r in conn.execute(
                f"SELECT DISTINCT symbol FROM open_positions WHERE user_id = ? {pf_sql}",
                tuple([user_id] + pf_params),
            ).fetchall()
        ]
        wl_syms = [
            r["symbol"] for r in conn.execute(
                f"SELECT symbol FROM watchlist WHERE user_id = ? {pf_sql}",
                tuple([user_id] + pf_params),
            ).fetchall()
        ]

    all_symbols = list({s.upper() for s in pos_syms + wl_syms})

    if not all_symbols:
        return JSONResponse({"ok": True, "prices": {}, "fetched_at": _now()})

    # yfinance senkron ve sembol başına ağ isteği yapar; thread'e atarak
    # event loop'u bloke etmesini önle (yoksa diğer istekler — sekme geçişleri
    # dahil — bu çağrı bitene kadar kilitlenir, özellikle süper modda sembol
    # sayısı katlandığında).
    from price_service import get_prices
    prices = await run_in_threadpool(get_prices, all_symbols)

    return JSONResponse({
        "ok":        True,
        "fetched_at": _now(),
        "prices":    prices,
    })


# ─── Watchlist CRUD ───────────────────────────────────────────────────────────

@router.post("/api/fiyatlar/watchlist/ekle")
async def watchlist_ekle(request: Request):
    """Watchlist'e sembol ekle."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    body = await request.json()
    symbol = body.get("symbol", "").strip().upper()
    portfolio = request.session.get("portfolio")

    if not symbol:
        return JSONResponse({"error": "Sembol boş olamaz"}, status_code=400)
    if not portfolio:
        return JSONResponse({"error": "Önce portföy oluşturun veya seçin"}, status_code=400)
    if is_super(portfolio):
        return JSONResponse({"error": "Süper portföyde ekleme yapılamaz, gerçek bir portföy seçin"}, status_code=400)

    with database.db() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE user_id=? AND portfolio=? AND upper(symbol)=?",
            (user_id, portfolio, symbol),
        ).fetchone()
        if existing:
            return JSONResponse({"error": f"{symbol} zaten listede"}, status_code=409)
        conn.execute(
            "INSERT INTO watchlist (user_id, portfolio, symbol) VALUES (?, ?, ?)",
            (user_id, portfolio, symbol),
        )

    return JSONResponse({"ok": True, "symbol": symbol})


@router.get("/api/fiyatlar/watchlist/{item_id}/note")
async def watchlist_note_get(item_id: int, request: Request):
    """Watchlist sembolü için kayıtlı notu getir (HTML içerik dahil)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    with database.db() as conn:
        row = conn.execute(
            "SELECT notes FROM watchlist WHERE id=? AND user_id=? AND portfolio=?",
            (item_id, user_id, portfolio),
        ).fetchone()
    return JSONResponse({"ok": True, "note": (row["notes"] if row else "") or ""})


@router.patch("/api/fiyatlar/watchlist/{item_id}/note")
async def watchlist_note_update(item_id: int, request: Request):
    """Watchlist sembolü için not güncelle (HTML içerik destekli — resimler base64 inline)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    body = await request.json()
    # HTML içerik için strip yapma — sadece komple boşsa None'a çevir
    note = body.get("note", "")
    if not note or not note.strip():
        note = None
    if is_super(portfolio):
        return JSONResponse({"error": "Süper portföyde düzenleme yapılamaz"}, status_code=400)
    with database.db() as conn:
        conn.execute(
            "UPDATE watchlist SET notes=? WHERE id=? AND user_id=? AND portfolio=?",
            (note, item_id, user_id, portfolio),
        )
    return JSONResponse({"ok": True})


@router.delete("/api/fiyatlar/watchlist/{item_id}")
async def watchlist_sil(item_id: int, request: Request):
    """Watchlist'ten sembol sil (portfolio guard ile)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        return JSONResponse({"ok": True})
    if is_super(portfolio):
        return JSONResponse({"error": "Süper portföyde silme yapılamaz"}, status_code=400)
    with database.db() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE id=? AND user_id=? AND portfolio=?",
            (item_id, user_id, portfolio),
        )
    return JSONResponse({"ok": True})


# ─── Symbol Targets CRUD ─────────────────────────────────────────────────────

@router.post("/api/fiyatlar/targets")
async def targets_upsert(request: Request):
    """Sembol için hedef/taban fiyat kaydet (upsert)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        return JSONResponse({"error": "Portföy seçilmedi"}, status_code=400)
    if is_super(portfolio):
        return JSONResponse({"error": "Süper portföyde hedef kaydedilemez, gerçek bir portföy seçin"}, status_code=400)

    body = await request.json()
    symbol = body.get("symbol", "").strip().upper()
    if not symbol:
        return JSONResponse({"error": "Sembol boş olamaz"}, status_code=400)

    hedef = body.get("hedef_fiyat")
    taban = body.get("taban_fiyat")
    kazanc = body.get("hedef_dolar_kazanci")
    stop = body.get("stop_fiyat")

    # None veya boş string → None
    hedef = float(hedef) if hedef not in (None, "", "null") else None
    taban = float(taban) if taban not in (None, "", "null") else None
    kazanc = float(kazanc) if kazanc not in (None, "", "null") else None
    stop = float(stop) if stop not in (None, "", "null") else None

    database.upsert_symbol_target(user_id, portfolio, symbol, hedef, taban, kazanc, stop)

    return JSONResponse({"ok": True, "symbol": symbol})


@router.delete("/api/fiyatlar/targets/{symbol}")
async def targets_delete(symbol: str, request: Request):
    """Sembol hedef/taban bilgisini sil."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        return JSONResponse({"ok": True})
    if is_super(portfolio):
        return JSONResponse({"error": "Süper portföyde silme yapılamaz"}, status_code=400)
    database.delete_symbol_target(user_id, portfolio, symbol.upper())
    return JSONResponse({"ok": True})


# ─── Symbol tags (sektör/klasman) ────────────────────────────────────────────

@router.post("/api/fiyatlar/symbol-tag")
async def symbol_tag_upsert(request: Request):
    """Sembol için tek tag (sektör/klasman) kaydet. Tag boş → sil.
    User-scoped (portfolyodan bağımsız)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    body = await request.json()
    symbol = (body.get("symbol") or "").strip().upper()
    if not symbol:
        return JSONResponse({"error": "Sembol boş olamaz"}, status_code=400)
    tag = body.get("tag")
    if tag is not None:
        tag = str(tag).strip()
    database.upsert_symbol_tag(user_id, symbol, tag)
    return JSONResponse({"ok": True, "symbol": symbol, "tag": tag or None})


@router.get("/api/fiyatlar/symbol-tags")
async def symbol_tags_list(request: Request):
    """{tags: {SYMBOL: 'tag'}, distinct: ['Fintech', 'AI', ...]}"""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    return JSONResponse({
        "tags": database.get_symbol_tags(user_id),
        "distinct": database.get_distinct_tags(user_id),
    })


# ─── TradingView Widget ──────────────────────────────────────────────────────

# Borsalara göre sembol listesi
_NYSE_SYMBOLS = {
    "IBKR", "CEG", "AXON", "KTOS", "MUU", "SPHR",
    "GE", "JPM", "BAC", "WMT", "DIS", "KO", "PFE", "T", "VZ",
}

# AMEX (ARCA) — ETF'ler için
_AMEX_SYMBOLS = {
    "SOXL", "TQQQ", "UPRO", "SPY", "QQQ", "IWM", "AGQ", "AMDL", "RKLX", "IREX",
}

# CBOE — seçenek ve bazı ETF'ler
_CBOE_SYMBOLS = {
}

@router.get("/widget/chart/{symbol}", response_class=HTMLResponse)
async def tw_widget(request: Request, symbol: str):
    """TradingView Advanced Chart widget — iframe veya modal'da kullanılır."""
    symbol = symbol.upper().strip()

    # Exchange belirle
    if symbol in _NYSE_SYMBOLS:
        exchange = "NYSE"
    elif symbol in _AMEX_SYMBOLS:
        exchange = "AMEX"
    elif symbol in _CBOE_SYMBOLS:
        exchange = "CBOE"
    else:
        # Varsayılan: NASDAQ
        exchange = "NASDAQ"

    tv_symbol = f"{exchange}:{symbol}"
    return templates.TemplateResponse("td_widget.html", {
        "request": request,
        "symbol": symbol,
        "tv_symbol": tv_symbol,
    })


# ─── Yardımcı ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


# ─── GET /api/price/{symbol} ─────────────────────────────────────────────

@router.get("/api/price/{symbol}")
async def get_single_price(symbol: str):
    """Tek sembol için anlık fiyat döndür."""
    symbol = symbol.upper().strip()
    from price_service import get_prices
    prices = await run_in_threadpool(get_prices, [symbol])
    p = prices.get(symbol, {})
    return JSONResponse({"ok": True, "symbol": symbol, "price": p})


# ─── POST /api/fiyatlar/validate-symbol ──────────────────────────────────

@router.post("/api/fiyatlar/validate-symbol")
async def validate_symbol(request: Request):
    """Ticker'ın geçerli olup olmadığını kontrol et."""
    body = await request.json()
    symbol = body.get("symbol", "").strip().upper()

    if not symbol:
        return JSONResponse({"valid": False, "error": "Sembol boş olamaz"}, status_code=400)

    def _validate():
        # yfinance senkron + ağ; event loop'u bloke etmemek için thread'de çalışır.
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info

        # Validasyon: fast_info'da exchange varsa ve history verisi varsa valid
        # fast_info.last_price None olabilir ama exchange/currency varsa sembol geçerli demektir
        has_exchange = info and info.get("exchange") is not None

        # Ya da history'de en az 1 satır varsa geçerli
        hist = ticker.history(period="1d")
        has_history = len(hist) > 0
        if not (has_exchange or has_history):
            return None

        # Fiyatı al: fast_info ya da history'den
        price = info.get("last_price") if info else None
        if price is None and len(hist) > 0:
            price = float(hist["Close"].iloc[-1])
        name = info.get("longName", symbol) if info else symbol
        return {"price": price, "name": name}

    try:
        res = await run_in_threadpool(_validate)
        if res is None:
            return JSONResponse({
                "valid": False,
                "error": f"{symbol} geçerli bir ticker değil veya kalktı"
            }, status_code=400)

        return JSONResponse({
            "valid": True,
            "symbol": symbol,
            "price": res["price"],
            "name": res["name"],
        })
    except Exception as e:
        return JSONResponse({
            "valid": False,
            "error": f"{symbol} bulunamadı"
        }, status_code=400)


# ─── GET /api/fiyatlar/symbol-charts (all position symbols) ──────────────

@router.get("/api/fiyatlar/symbol-charts")
async def symbol_charts(request: Request):
    """Her açık pozisyon sembolü için gerçekleşen K/Z tarihçesi (sparkline + pie)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        return JSONResponse({"ok": True, "charts": {}})

    with database.db() as conn:
        rows = conn.execute(
            """
            SELECT symbol, tx_date, pnl
            FROM fifo_results
            WHERE user_id = ? AND portfolio = ?
            ORDER BY tx_date, rowid
            """,
            (user_id, portfolio),
        ).fetchall()

    charts = {}
    for row in rows:
        sym = row["symbol"]
        if sym not in charts:
            charts[sym] = []
        charts[sym].append({"date": row["tx_date"], "pnl": row["pnl"]})

    return JSONResponse({"ok": True, "charts": charts})


# ─── GET /api/fiyatlar/chart/{symbol} ─────────────────────────────────────

@router.get("/api/fiyatlar/chart/{symbol}")
async def fiyatlar_chart(symbol: str, interval: str = Query("1d")):
    """Sembol için historical chart verisi (OHLCV)."""
    symbol = symbol.upper().strip()

    if not symbol:
        return JSONResponse({"error": "Sembol boş"}, status_code=400)

    try:
        from price_service import get_historical_data
        data = await run_in_threadpool(get_historical_data, symbol, interval=interval)
        return JSONResponse({"ok": True, "symbol": symbol, "interval": interval, "data": data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
