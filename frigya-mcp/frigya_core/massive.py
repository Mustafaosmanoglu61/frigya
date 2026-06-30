"""
frigya_core.massive — Massive Market ham yanıtlarını normalize eder.

Üç fonksiyon (skill data/massive_*.py'den port — argparse/stdin yerine doğrudan arg):
  normalize_teknik(data, symbol=None, fallback=False)
  normalize_haber(symbol, raw, limit=10)
  normalize_meta(symbol, payload)

Bu fonksiyonlar API çağrısı YAPMAZ — ham yanıtı (CSV/JSON string) alıp şekillendirir.
Client (Claude/webapp) Massive'den çeker, buraya passthrough eder.
"""
import ast
import csv
import io
import json


# ---------------------------------------------------------------------------
# TEKNİK (indicators + aggregates)
# ---------------------------------------------------------------------------
def _parse_aggs_csv(csv_str):
    if not csv_str:
        return []
    lines = csv_str.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = lines[0].split(",")
    out = []
    for line in lines[1:]:
        if not line.strip() or "Next page available" in line:
            continue
        parts = line.split(",")
        if len(parts) < len(headers):
            continue
        try:
            row = {headers[i]: float(parts[i]) if parts[i] else None for i in range(len(headers))}
            out.append(row)
        except (ValueError, IndexError):
            continue
    return out


def _parse_indicator(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        if "value" in raw and "timestamp" in raw:
            return raw
        if "values" in raw and isinstance(raw["values"], list) and raw["values"]:
            return raw["values"][0]
    if isinstance(raw, str):
        lines = raw.strip().split("\n")
        for line in lines[1:]:
            if "[{" in line:
                try:
                    start = line.find("[{")
                    end = line.rfind("}]") + 2
                    if start >= 0 and end > start:
                        values = ast.literal_eval(line[start:end])
                        if values:
                            return values[0]
                except Exception:
                    pass
    return None


def _sma(arr, period):
    if len(arr) < period:
        return None
    return sum(arr[-period:]) / period


def _ema(arr, period):
    if len(arr) < period:
        return None
    k = 2 / (period + 1)
    e = sum(arr[:period]) / period
    for x in arr[period:]:
        e = x * k + e * (1 - k)
    return e


def _rsi(arr, period=14):
    if len(arr) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        d = arr[i] - arr[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_g, avg_l = gains / period, losses / period
    for i in range(period + 1, len(arr)):
        d = arr[i] - arr[i - 1]
        g = d if d >= 0 else 0
        l = -d if d < 0 else 0
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


def _assemble_teknik(bars, sma_raw=None, ema_raw=None, rsi_raw=None, macd_raw=None,
                     symbol=None, fallback=False):
    """Ortak teknik birleştirme. bars = [{o,c,h,l,v,t}, ...] (eski→yeni sıralı).
    sma_raw/ema_raw/rsi_raw/macd_raw: CSV string VEYA {"values":[...]} dict VEYA None.
    Hem MCP-CSV hem JSON-REST yolu bu çekirdeği kullanır."""
    out = {}
    if symbol:
        out["symbol"] = symbol.upper()

    if bars:
        last = bars[-1]
        closes = [b["c"] for b in bars if b.get("c") is not None]
        highs = [b["h"] for b in bars if b.get("h") is not None]
        lows = [b["l"] for b in bars if b.get("l") is not None]
        vols = [b["v"] for b in bars if b.get("v") is not None]

        out["last_close"] = last.get("c")
        out["last_high"] = last.get("h")
        out["last_low"] = last.get("l")
        out["last_date_ts"] = last.get("t")
        out["volume_last"] = last.get("v")
        out["bar_count"] = len(bars)

        if len(highs) >= 14 and len(lows) >= 14:
            h14 = max(highs[-14:])
            l14 = min(lows[-14:])
            out["high_14d"] = h14
            out["low_14d"] = l14
            if h14 != l14:
                out["stoch_pct_k"] = round((out["last_close"] - l14) / (h14 - l14) * 100, 2)
        if highs:
            h_all = max(highs)
            l_all = min(lows)
            out["high_60d"] = h_all
            out["low_60d"] = l_all
            if h_all > 0:
                out["drawdown_from_peak"] = round((out["last_close"] - h_all) / h_all * 100, 2)

        if len(vols) >= 20:
            avg_v = sum(vols[-20:]) / 20
            out["volume_avg_20d"] = round(avg_v, 0)
            if avg_v > 0:
                out["volume_spike"] = round(out["volume_last"] / avg_v, 2)

        out["bars"] = [
            {"t": int(b["t"]) if b.get("t") else None, "c": b.get("c"),
             "h": b.get("h"), "l": b.get("l"), "v": b.get("v")}
            for b in bars
        ]

        if fallback or not sma_raw:
            out["sma10"] = round(_sma(closes, 10), 2) if _sma(closes, 10) else None
            out["sma20"] = round(_sma(closes, 20), 2) if _sma(closes, 20) else None
            out["sma50"] = round(_sma(closes, 50), 2) if _sma(closes, 50) else None
            out["ema21"] = round(_ema(closes, 21), 2) if _ema(closes, 21) else None
            out["rsi14"] = round(_rsi(closes, 14), 2) if _rsi(closes, 14) else None
            out["_indicator_source"] = "python_fallback"

    if not fallback:
        for raw, key in [(sma_raw, "sma20"), (ema_raw, "ema21"), (rsi_raw, "rsi14")]:
            v = _parse_indicator(raw)
            if v:
                out[key] = round(v.get("value"), 2) if v.get("value") else out.get(key)

        macd_v = _parse_indicator(macd_raw)
        if macd_v:
            out["macd"] = {
                "value": round(macd_v.get("value"), 4) if macd_v.get("value") is not None else None,
                "signal": round(macd_v.get("signal"), 4) if macd_v.get("signal") is not None else None,
                "histogram": round(macd_v.get("histogram"), 4) if macd_v.get("histogram") is not None else None,
            }
        if any(x for x in (sma_raw, ema_raw, rsi_raw, macd_raw)):
            out["_indicator_source"] = "massive_api"

    return out


def normalize_teknik(data, symbol=None, fallback=False):
    """data = {sma, ema, rsi, macd, daily} (MCP CSV passthrough). Teknik özet dict."""
    data = data or {}
    bars = _parse_aggs_csv(data.get("daily", ""))
    return _assemble_teknik(bars, data.get("sma"), data.get("ema"), data.get("rsi"),
                            data.get("macd"), symbol, fallback)


def teknik_from_json(aggs_results, sma_values=None, ema_values=None, rsi_values=None,
                     macd_values=None, symbol=None):
    """JSON-REST yolu: Polygon-tipi `results` listelerinden teknik özet.
    aggs_results: [{v,vw,o,c,h,l,t,n}, ...]; *_values: indicator results['values'] listesi."""
    return _assemble_teknik(
        aggs_results or [],
        {"values": sma_values} if sma_values else None,
        {"values": ema_values} if ema_values else None,
        {"values": rsi_values} if rsi_values else None,
        {"values": macd_values} if macd_values else None,
        symbol, fallback=False,
    )


# ---------------------------------------------------------------------------
# HABER (news + sentiment)
# ---------------------------------------------------------------------------
def _unwrap_result(raw):
    if raw is None:
        return ""
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            return data.get("result", raw) if isinstance(data, dict) else raw
        except Exception:
            return raw
    if isinstance(raw, dict):
        return raw.get("result", "")
    return raw


def _parse_news_csv(csv_str):
    if not csv_str:
        return []
    f = io.StringIO(csv_str.strip())
    reader = csv.DictReader(f)
    out = []
    for row in reader:
        if "Next page available" in str(row):
            continue
        out.append(row)
    return out


def _parse_tickers(tickers_str):
    if not tickers_str:
        return []
    try:
        return ast.literal_eval(tickers_str)
    except Exception:
        return []


def _sentiment_for_symbol(insights_str, symbol):
    if not insights_str:
        return None, None
    try:
        insights = ast.literal_eval(insights_str)
        for ins in insights:
            if isinstance(ins, dict) and ins.get("ticker", "").upper() == symbol.upper():
                return ins.get("sentiment"), ins.get("sentiment_reasoning")
    except Exception:
        pass
    return None, None


def normalize_haber(symbol, raw, limit=10):
    """Massive news ham CSV → sembol-spesifik sentiment'li haber dict."""
    sym = symbol.upper()
    csv_str = _unwrap_result(raw)
    rows = _parse_news_csv(csv_str)
    articles = []
    sent_count = {"positive": 0, "negative": 0, "neutral": 0}

    for r in rows[:limit]:
        sentiment, reasoning = _sentiment_for_symbol(r.get("insights", ""), sym)
        articles.append({
            "date": (r.get("published_utc", "") or "")[:10],
            "title": r.get("title", ""),
            "publisher": r.get("publisher_name", ""),
            "author": r.get("author", ""),
            "sentiment": sentiment,
            "sentiment_reasoning": reasoning,
            "url": r.get("article_url", ""),
            "tickers": _parse_tickers(r.get("tickers", "")),
            "description": (r.get("description", "") or "")[:280],
        })
        if sentiment in sent_count:
            sent_count[sentiment] += 1

    total = sum(sent_count.values())
    net = round((sent_count["positive"] - sent_count["negative"]) / total, 2) if total > 0 else 0
    return {
        "symbol": sym,
        "article_count": len(articles),
        "articles": articles,
        "sentiment_summary": {**sent_count, "net_score": net},
    }


# ---------------------------------------------------------------------------
# META (overview + related + market status)
# ---------------------------------------------------------------------------
def _parse_csv(csv_str):
    if not csv_str:
        return []
    f = io.StringIO(csv_str.strip())
    return list(csv.DictReader(f))


def _fmt_mcap(v):
    if not v:
        return None
    try:
        v = float(v)
    except Exception:
        return None
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"


def normalize_meta(symbol, payload):
    """payload = {overview, related, market_status} (CSV string'ler) → meta dict."""
    sym = symbol.upper()
    payload = payload or {}

    overview_rows = _parse_csv(_unwrap_result(payload.get("overview", "")))
    related_rows = _parse_csv(_unwrap_result(payload.get("related", "")))
    market_status_rows = _parse_csv(_unwrap_result(payload.get("market_status", "")))

    out = {"symbol": sym}

    if overview_rows:
        r = overview_rows[0]
        try:
            mcap = float(r.get("market_cap") or 0)
        except Exception:
            mcap = 0
        out.update({
            "name": r.get("name"),
            "exchange": r.get("primary_exchange"),
            "currency": r.get("currency_name"),
            "type": r.get("type"),
            "market_cap": mcap or None,
            "market_cap_fmt": _fmt_mcap(mcap),
            "sic_description": r.get("sic_description"),
            "ticker_root": r.get("ticker_root"),
            "employees": r.get("total_employees"),
            "list_date": r.get("list_date"),
            "homepage_url": r.get("homepage_url"),
            "phone_number": r.get("phone_number"),
            "city": r.get("address_city"),
            "state": r.get("address_state"),
            "description_short": (r.get("description", "") or "")[:300],
        })

    if related_rows:
        out["related_tickers"] = [r["ticker"] for r in related_rows if r.get("ticker")]

    if market_status_rows:
        r = market_status_rows[0]
        out["market_status"] = {
            "market": r.get("market"),
            "is_after_hours": r.get("afterHours") == "True",
            "is_early_hours": r.get("earlyHours") == "True",
            "nasdaq": r.get("exchanges_nasdaq"),
            "nyse": r.get("exchanges_nyse"),
            "server_time": r.get("serverTime"),
        }

    return out


# ---------------------------------------------------------------------------
# JSON-REST yolu (webapp doğrudan Massive REST çağırınca — Polygon-tipi JSON)
# ---------------------------------------------------------------------------
def _sentiment_from_insights_list(insights, symbol):
    if not insights:
        return None, None
    for ins in insights:
        if isinstance(ins, dict) and (ins.get("ticker", "") or "").upper() == symbol.upper():
            return ins.get("sentiment"), ins.get("sentiment_reasoning")
    return None, None


def haber_from_json(symbol, results, limit=10):
    """Polygon-tipi news `results` listesi (insights = list) → haber dict."""
    sym = symbol.upper()
    articles = []
    sent_count = {"positive": 0, "negative": 0, "neutral": 0}
    for r in (results or [])[:limit]:
        sentiment, reasoning = _sentiment_from_insights_list(r.get("insights") or [], sym)
        pub = r.get("publisher") or {}
        articles.append({
            "date": (r.get("published_utc", "") or "")[:10],
            "title": r.get("title", ""),
            "publisher": pub.get("name", "") if isinstance(pub, dict) else "",
            "author": r.get("author", ""),
            "sentiment": sentiment,
            "sentiment_reasoning": reasoning,
            "url": r.get("article_url", ""),
            "tickers": r.get("tickers") or [],
            "description": (r.get("description", "") or "")[:280],
        })
        if sentiment in sent_count:
            sent_count[sentiment] += 1
    total = sum(sent_count.values())
    net = round((sent_count["positive"] - sent_count["negative"]) / total, 2) if total > 0 else 0
    return {"symbol": sym, "article_count": len(articles), "articles": articles,
            "sentiment_summary": {**sent_count, "net_score": net}}


def meta_from_json(symbol, overview=None, related=None, marketstatus=None):
    """Polygon-tipi results → meta dict.
    overview: dict, related: [{ticker}], marketstatus: dict (booleans + nested exchanges)."""
    sym = symbol.upper()
    out = {"symbol": sym}

    if overview:
        try:
            mcap = float(overview.get("market_cap") or 0)
        except Exception:
            mcap = 0
        addr = overview.get("address") or {}
        branding = overview.get("branding") or {}
        out.update({
            "name": overview.get("name"),
            "exchange": overview.get("primary_exchange"),
            "currency": overview.get("currency_name"),
            "type": overview.get("type"),
            "market_cap": mcap or None,
            "market_cap_fmt": _fmt_mcap(mcap),
            "sic_description": overview.get("sic_description"),
            "ticker_root": overview.get("ticker_root"),
            "employees": overview.get("total_employees"),
            "list_date": overview.get("list_date"),
            "homepage_url": overview.get("homepage_url"),
            "phone_number": overview.get("phone_number"),
            "city": addr.get("city") if isinstance(addr, dict) else None,
            "state": addr.get("state") if isinstance(addr, dict) else None,
            "description_short": (overview.get("description", "") or "")[:300],
        })

    if related:
        out["related_tickers"] = [x.get("ticker") for x in related if isinstance(x, dict) and x.get("ticker")]

    if marketstatus:
        ex = marketstatus.get("exchanges") or {}

        def _flag(v):
            return bool(v) if isinstance(v, bool) else (v == "True")

        out["market_status"] = {
            "market": marketstatus.get("market"),
            "is_after_hours": _flag(marketstatus.get("afterHours")),
            "is_early_hours": _flag(marketstatus.get("earlyHours")),
            "nasdaq": ex.get("nasdaq") if isinstance(ex, dict) else None,
            "nyse": ex.get("nyse") if isinstance(ex, dict) else None,
            "server_time": marketstatus.get("serverTime"),
        }

    return out
