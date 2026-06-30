"""
frigya_core.massive_fetch — Massive REST API'sini DOĞRUDAN çağırır (webapp yolu).

MCP/Claude yolundan farkı: burada Claude aracı yok; servis kendi API key'iyle
Massive REST'e HTTP isteği atar (Polygon-uyumlu JSON döner), normalize edip
build_sentez'in beklediği {teknik, news, meta} dict'ini üretir.

Sadece stdlib (urllib) — frigya_core bağımlılıksız kalsın diye.

Ortam değişkenleri:
  MASSIVE_API_KEY   — zorunlu (yoksa fetch atlanır)
  MASSIVE_BASE_URL  — default https://api.massive.com
  MASSIVE_AUTH_MODE — bearer (default) | apikey | xapikey
                      bearer → Authorization: Bearer <key>
                      apikey → ?apiKey=<key>  (Polygon klasik)
                      xapikey→ X-API-Key: <key>

Auth şeması kesin değilse: önce bearer denenir, 401/403 olursa apikey'e düşülür.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import massive


DEFAULT_BASE = "https://api.massive.com"


def _cfg():
    return (
        os.getenv("MASSIVE_API_KEY", "").strip(),
        os.getenv("MASSIVE_BASE_URL", DEFAULT_BASE).strip().rstrip("/"),
        os.getenv("MASSIVE_AUTH_MODE", "bearer").strip().lower(),
    )


def _request(url, headers, timeout=15):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path, params, api_key, base_url, auth_mode):
    """Tek GET. auth_mode'a göre header/param. bearer 401/403 olursa apikey'e düşer."""
    params = dict(params or {})
    headers = {"Accept": "application/json", "User-Agent": "frigya-core/0.1"}

    def build(mode):
        p = dict(params)
        h = dict(headers)
        if mode == "apikey":
            p["apiKey"] = api_key
        elif mode == "xapikey":
            h["X-API-Key"] = api_key
        else:  # bearer
            h["Authorization"] = f"Bearer {api_key}"
        qs = urllib.parse.urlencode(p)
        return f"{base_url}{path}?{qs}", h

    url, hdrs = build(auth_mode)
    try:
        return _request(url, hdrs)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and auth_mode != "apikey":
            url2, hdrs2 = build("apikey")  # fallback
            return _request(url2, hdrs2)
        raise


def fetch_market(symbol, days=90, limit_news=10):
    """Massive REST'ten {teknik, news, meta} normalize dict döndürür.

    Her endpoint bağımsız; biri patlarsa _errors'a yazılır, kalan veri yine döner.
    API key yoksa {"_status": "no_key"} döner (sessiz atlama).
    """
    api_key, base_url, auth_mode = _cfg()
    if not api_key:
        return {"_status": "no_key", "_hint": "MASSIVE_API_KEY tanımlı değil — DB-only analiz yapılır."}

    sym = symbol.upper()
    errors = {}

    def safe(label, fn):
        try:
            return fn()
        except Exception as e:
            errors[label] = f"{type(e).__name__}: {str(e)[:160]}"
            return None

    to_d = datetime.utcnow().date()
    frm_d = to_d - timedelta(days=days)
    frm, to = frm_d.isoformat(), to_d.isoformat()

    def g(path, params=None):
        return _get(path, params, api_key, base_url, auth_mode)

    aggs = safe("aggs", lambda: g(f"/v2/aggs/ticker/{sym}/range/1/day/{frm}/{to}",
                                  {"adjusted": "true", "sort": "asc", "limit": 300}))
    sma = safe("sma", lambda: g(f"/v1/indicators/sma/{sym}",
                                {"timespan": "day", "window": 20, "series_type": "close", "limit": 1}))
    ema = safe("ema", lambda: g(f"/v1/indicators/ema/{sym}",
                                {"timespan": "day", "window": 21, "series_type": "close", "limit": 1}))
    rsi = safe("rsi", lambda: g(f"/v1/indicators/rsi/{sym}",
                                {"timespan": "day", "window": 14, "series_type": "close", "limit": 1}))
    macd = safe("macd", lambda: g(f"/v1/indicators/macd/{sym}",
                                  {"timespan": "day", "short_window": 12, "long_window": 26,
                                   "signal_window": 9, "limit": 1}))
    news = safe("news", lambda: g("/v2/reference/news",
                                  {"ticker": sym, "limit": limit_news, "order": "desc"}))
    overview = safe("overview", lambda: g(f"/v3/reference/tickers/{sym}"))
    related = safe("related", lambda: g(f"/v1/related-companies/{sym}"))
    mstatus = safe("market_status", lambda: g("/v1/marketstatus/now"))

    def _vals(ind):
        if not ind:
            return None
        res = ind.get("results")
        if isinstance(res, dict):
            return res.get("values")
        return None

    teknik = massive.teknik_from_json(
        (aggs or {}).get("results") or [],
        sma_values=_vals(sma), ema_values=_vals(ema),
        rsi_values=_vals(rsi), macd_values=_vals(macd), symbol=sym,
    )
    haber = massive.haber_from_json(sym, (news or {}).get("results") or [], limit=limit_news)
    meta = massive.meta_from_json(
        sym,
        overview=(overview or {}).get("results"),
        related=(related or {}).get("results"),
        marketstatus=mstatus or None,
    )

    return {
        "teknik": teknik,
        "news": haber,
        "meta": meta,
        "_source": "massive_rest",
        "_errors": errors or None,
    }
