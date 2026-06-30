"""
Frigya AI analiz endpoint'leri — frigya_core paketini doğrudan import eder.

Mimari: webapp, frigya-mcp/frigya_core paketini (SSOT) import edip analizi sunar.
Subprocess/MCP yok — aynı çekirdek fonksiyonlar. Massive piyasa verisi için
frigya_core.fetch_market kendi REST key'iyle çalışır (MASSIVE_API_KEY).

Endpoint'ler (hepsi giriş gerektirir, /api/ prefix'i auth guard'a tabi):
  GET /api/ai/frigya/sembol/{symbol}?portfolio=&format=json|markdown|html&market=true
  GET /api/ai/frigya/portfoy?portfolio=
  GET /api/ai/frigya/davranis?portfolio=&year=

Not: Bu endpoint'ler sync `def` — FastAPI bunları threadpool'da çalıştırır,
böylece bloklayan sqlite + HTTP çağrıları event loop'u kilitlemez.
"""
import os
import sys

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse

import auth_service
import database
from portfolio_helper import resolve_portfolio, is_super

# frigya_core'u import edilebilir kıl (proje yanındaki frigya-mcp paketi)
_FRIGYA_MCP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frigya-mcp",
)
if _FRIGYA_MCP not in sys.path:
    sys.path.insert(0, _FRIGYA_MCP)

try:
    import frigya_core as fc
except Exception as _e:  # pragma: no cover
    fc = None
    _FRIGYA_IMPORT_ERROR = str(_e)

router = APIRouter()


def _ensure_core():
    if fc is None:
        return JSONResponse(
            {"error": f"frigya_core import edilemedi: {_FRIGYA_IMPORT_ERROR}. "
                      f"Beklenen yol: {_FRIGYA_MCP}"},
            status_code=500,
        )
    return None


def _portfolio_filter(request, portfolio, user_id):
    """Süper (tüm portföyler) ise None döndür → frigya tüm portföyleri birleştirir."""
    current = resolve_portfolio(request, portfolio, user_id)
    return None if is_super(current) else current


@router.get("/api/ai/frigya/sembol/{symbol}")
def frigya_sembol(request: Request, symbol: str,
                  portfolio: str = Query(None),
                  format: str = Query("json", pattern="^(json|markdown|html)$"),
                  market: bool = Query(False)):
    """Bir sembolün komple Frigya sentezi. market=true ise Massive REST verisi de katılır."""
    err = _ensure_core()
    if err:
        return err
    user = auth_service.require_current_user(request)
    uid = int(user["id"])
    pf = _portfolio_filter(request, portfolio, uid)

    try:
        prefetched = fc.fetch_market(symbol) if market else None
        sentez = fc.build_sentez(
            symbol, portfolio=pf, prefetched_market=prefetched,
            db_path=database.get_db_path(), user_id=uid,
        )
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:300]}"}, status_code=500)

    if format == "markdown":
        return PlainTextResponse(fc.render_markdown(sentez), media_type="text/markdown; charset=utf-8")
    if format == "html":
        return HTMLResponse(fc.render_html(sentez))
    return JSONResponse(sentez)


@router.get("/api/ai/frigya/portfoy")
def frigya_portfoy(request: Request, portfolio: str = Query(None)):
    """Tüm açık pozisyonlar + watchlist + hedefler."""
    err = _ensure_core()
    if err:
        return err
    user = auth_service.require_current_user(request)
    uid = int(user["id"])
    pf = _portfolio_filter(request, portfolio, uid)
    try:
        conn, _path, _u = fc.open_conn(db_path=database.get_db_path(), user_id=uid)
        try:
            return JSONResponse(fc.portfoy_data(conn, uid, pf))
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:300]}"}, status_code=500)


@router.get("/api/ai/frigya/davranis")
def frigya_davranis(request: Request, portfolio: str = Query(None),
                    year: int = Query(None)):
    """Genel trade davranış paternleri."""
    err = _ensure_core()
    if err:
        return err
    user = auth_service.require_current_user(request)
    uid = int(user["id"])
    pf = _portfolio_filter(request, portfolio, uid)
    try:
        conn, _path, _u = fc.open_conn(db_path=database.get_db_path(), user_id=uid)
        try:
            return JSONResponse(fc.davranis_data(conn, uid, pf, year))
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:300]}"}, status_code=500)
