#!/usr/bin/env python3
"""
frigya_mcp — Frigya portföy analiz MCP servisi (standalone, importable çekirdek).

Mimari ilke (kullanıcının tasarımı): SERVİS DB'ye erişir, client/skill doğrudan değil.
Bu server yerelde çalışır, ~/Tax_Portfolilo/webapp/tax.db'ye sahiptir.

Tasarım: İş mantığı `frigya_core` paketinde (importable, subprocess YOK). Bu server
o paketi import edip MCP tool'ları olarak sunar. Aynı paketi Frigya webapp routers/ai.py
de import edebilir → tek hakikat kaynağı.

Massive Market verisi: server API'ye çağrı yapmaz. `frigya_sembol_analiz` opsiyonel
`market_json` passthrough alır (client Massive MCP'sinden çeker, JSON olarak geçirir).

Ortam değişkenleri:
  DB_PATH — SQLite yolu (default: ~/Tax_Portfolilo/webapp/tax.db otomatik bulunur)
"""
import json
import os
import sys
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# frigya_core'u bu dizinden import edilebilir kıl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frigya_core as fc

mcp = FastMCP("frigya_mcp")


def _err(e: Exception) -> str:
    return json.dumps({"error": True, "type": type(e).__name__, "message": str(e)[:500]},
                      ensure_ascii=False)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# Pydantic giriş modelleri
# ---------------------------------------------------------------------------
class SembolAnalizInput(BaseModel):
    """frigya_sembol_analiz girişi."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    symbol: str = Field(..., description="Hisse sembolü (örn. 'RKLB', 'IREX')", min_length=1, max_length=12)
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele (örn. 'family'). Boşsa tüm portföyler birleşir.")
    market_json: Optional[str] = Field(
        default=None,
        description=(
            "Opsiyonel Massive Market verisi (passthrough). Client önce Massive MCP'sinden çeker, "
            "şu yapıda JSON string geçirir: "
            "{\"teknik\": {\"sma\":..., \"rsi\":..., \"macd\":..., \"daily\": \"<aggs CSV>\"}, "
            "\"haber\": \"<news CSV>\", \"meta\": {\"overview\": \"<csv>\", \"related\": \"<csv>\", "
            "\"market_status\": \"<csv>\"}}. Verilmezse sadece DB analizi yapılır."
        ),
    )


class PortfoyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")


class DavranisInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")
    year: Optional[int] = Field(default=None, description="Tek yıla filtrele (örn. 2026).", ge=2000, le=2100)


class RenderInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    sentez_json: str = Field(..., description="frigya_sembol_analiz çıktısı olan tam sentez JSON string'i.", min_length=2)


class HedefGuncelleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    symbol: str = Field(..., description="Hisse sembolü", min_length=1, max_length=12)
    portfolio: str = Field(..., description="Hedeflerin yazılacağı portföy (zorunlu)", min_length=1)
    hedef: Optional[float] = Field(default=None, description="Hedef fiyat ($)")
    taban: Optional[float] = Field(default=None, description="Taban/destek fiyat ($)")
    stop: Optional[float] = Field(default=None, description="Stop fiyat ($) — taktiksel risk yönetimi")
    note: Optional[str] = Field(default=None, description="symbol_notes'a düşülecek neden notu")
    apply: bool = Field(default=False, description="True ise DB'ye YAZAR. False (default) dry-run: before/after gösterir, yazmaz.")


class AnalistHedefInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    symbol: str = Field(..., description="Hisse sembolü", min_length=1, max_length=12)
    portfolio: str = Field(..., description="Portföy (zorunlu)", min_length=1)
    low: Optional[float] = Field(default=None, description="Analyst low target → taban_fiyat")
    high: Optional[float] = Field(default=None, description="Analyst high target → hedef_fiyat")
    source: Optional[str] = Field(default="manuel", description="Kaynak (örn. 'TradingView', 'Bölüm 8')")
    analyst: Optional[str] = Field(default=None, description="Spesifik analist adı (varsa)")
    target_date: Optional[str] = Field(default=None, description="Analyst hedef vadesi (örn. '12 ay')")
    apply: bool = Field(default=False, description="True ise DB'ye YAZAR. False (default) dry-run.")


# ---------------------------------------------------------------------------
# OKUMA araçları
# ---------------------------------------------------------------------------
@mcp.tool(name="frigya_sembol_analiz", annotations={
    "title": "Sembol Analizi (DB + notlar + opsiyonel piyasa)",
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def frigya_sembol_analiz(params: SembolAnalizInput) -> str:
    """Bir sembolün komple Frigya sentezini üretir (frigya_core.build_sentez).

    DB'den: trade geçmişi, FIFO K/Z, açık pozisyon + ortalama maliyet, hedef/taban/stop,
    symbol_notes + portfolio_notes (seviye/earnings/tez parse edilmiş), davranış istatistikleri.
    market_json verilirse Massive teknik (SMA/RSI/MACD), haber sentiment, şirket meta birleşir.

    Args:
        params (SembolAnalizInput): symbol, portfolio?, market_json? (Massive passthrough)

    Returns:
        str: Sentez JSON (references/sentez_sema.md). Üst seviye: meta, position,
        frigya_history, targets, market, notes, news, company_meta, synthesis, data_gaps.
    """
    try:
        market = json.loads(params.market_json) if params.market_json else None
        result = fc.build_sentez(params.symbol, portfolio=params.portfolio, market=market)
        return _dump(result)
    except Exception as e:
        return _err(e)


@mcp.tool(name="frigya_portfoy_tara", annotations={
    "title": "Portföy Taraması (açık pozisyonlar + watchlist + hedefler)",
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def frigya_portfoy_tara(params: PortfoyInput) -> str:
    """Tüm açık pozisyonları + watchlist + tanımlı hedef/stop'ları tek JSON'da döker.

    Args:
        params (PortfoyInput): portfolio (Optional[str])

    Returns:
        str: JSON {meta{open_count, total_cost_basis_usd}, positions[], watchlist_only[]}
    """
    try:
        conn, _path, uid = fc.open_conn()
        try:
            return _dump(fc.portfoy_data(conn, uid, params.portfolio))
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


@mcp.tool(name="frigya_davranis_analiz", annotations={
    "title": "Davranış Analizi (paternler, sektör, hold süresi)",
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def frigya_davranis_analiz(params: DavranisInput) -> str:
    """Kullanıcının genel trade davranış paternlerini hesaplar.

    Sektör başarı, hold süresi dağılımı, aylık trend, en iyi/zayıf semboller, win/loss oranı.

    Args:
        params (DavranisInput): portfolio?, year?

    Returns:
        str: JSON {overall{}, best_symbols[], worst_symbols[], tag_breakdown[],
             hold_duration_distribution[], monthly_trend[], open_positions_snapshot{}}
    """
    try:
        conn, _path, uid = fc.open_conn()
        try:
            return _dump(fc.davranis_data(conn, uid, params.portfolio, params.year))
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# RENDER araçları
# ---------------------------------------------------------------------------
@mcp.tool(name="frigya_render_markdown", annotations={
    "title": "Sentez → Markdown",
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def frigya_render_markdown(params: RenderInput) -> str:
    """Sentez JSON'unu kompakt Türkçe markdown'a dönüştürür.

    Args:
        params (RenderInput): sentez_json (frigya_sembol_analiz çıktısı)

    Returns:
        str: Markdown metin
    """
    try:
        return fc.render_markdown(json.loads(params.sentez_json))
    except Exception as e:
        return _err(e)


@mcp.tool(name="frigya_render_html", annotations={
    "title": "Sentez → HTML artifact (Chart.js grafikli)",
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def frigya_render_html(params: RenderInput) -> str:
    """Sentez JSON'unu kompakt HTML artifact'a dönüştürür (açık tema + Chart.js fiyat grafiği).

    Grafik için market.bars gerekir (market_json ile analiz yapıldıysa dolu olur).

    Args:
        params (RenderInput): sentez_json

    Returns:
        str: Tek dosya HTML
    """
    try:
        return fc.render_html(json.loads(params.sentez_json))
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# YAZMA araçları (default dry-run)
# ---------------------------------------------------------------------------
@mcp.tool(name="frigya_hedef_guncelle", annotations={
    "title": "Taktiksel Hedef/Stop Güncelle (DB yazma)",
    "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def frigya_hedef_guncelle(params: HedefGuncelleInput) -> str:
    """Bir sembolün taktiksel hedef/taban/stop seviyelerini symbol_targets'a yazar.

    GÜVENLİK: apply=False (default) → DRY-RUN (before/after/changes döner, YAZMAZ).
    Önce dry-run göster, kullanıcı onaylarsa apply=True ile tekrar çağır.
    apply=True'da symbol_notes'a otomatik kayıt düşer (timestamp + diff).

    Args:
        params (HedefGuncelleInput): symbol, portfolio (zorunlu), hedef?, taban?, stop?, note?, apply

    Returns:
        str: JSON {symbol, portfolio, before{}, after{}, changes{}, _status, (apply ise) note_added}
    """
    try:
        conn, _path, uid = fc.open_conn()
        try:
            result = fc.hedef_guncelle(
                conn, uid, params.symbol, params.portfolio,
                hedef=params.hedef, taban=params.taban, stop=params.stop,
                note=params.note, apply=params.apply,
            )
            return _dump(result)
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


@mcp.tool(name="frigya_analist_hedef", annotations={
    "title": "Analyst Range Güncelle (uzun vade hedef/taban, DB yazma)",
    "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def frigya_analist_hedef(params: AnalistHedefInput) -> str:
    """Uzun vade analyst fiyat aralığını yazar: high→hedef_fiyat, low→taban_fiyat. stop dokunulmaz.

    GÜVENLİK: apply=False (default) → DRY-RUN. Onay sonrası apply=True.
    apply=True'da symbol_notes'a 'analyst-range' prefix'li kayıt düşer.

    Args:
        params (AnalistHedefInput): symbol, portfolio, low?, high?, source?, analyst?, target_date?, apply

    Returns:
        str: JSON {symbol, portfolio, source, before{}, after{}, changes{}, _status}
    """
    try:
        conn, _path, uid = fc.open_conn()
        try:
            result = fc.analist_hedef(
                conn, uid, params.symbol, params.portfolio,
                low=params.low, high=params.high, source=params.source,
                analyst=params.analyst, target_date=params.target_date, apply=params.apply,
            )
            return _dump(result)
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import asyncio
    sym = os.getenv("SELFTEST_SYMBOL", "IREX")
    print(f"[selftest] frigya_core v{fc.__version__}", file=sys.stderr)
    try:
        out = json.loads(asyncio.run(frigya_sembol_analiz(SembolAnalizInput(symbol=sym))))
        if out.get("error"):
            print(f"[selftest] FAIL: {out}", file=sys.stderr)
            return 1
        print(f"[selftest] OK sembol_analiz({sym}): open_qty="
              f"{out.get('position',{}).get('open_qty')} · "
              f"synthesis={[k for k,v in out.get('synthesis',{}).items() if v]}", file=sys.stderr)
        md = fc.render_markdown(out)
        print(f"[selftest] OK render_markdown: {len(md.splitlines())} satır", file=sys.stderr)
        conn, _p, uid = fc.open_conn()
        pf = fc.portfoy_data(conn, uid)
        print(f"[selftest] OK portfoy: open_count={pf['meta']['open_count']}", file=sys.stderr)
        dr = fc.hedef_guncelle(conn, uid, sym, "family", stop=33.0, apply=False)
        print(f"[selftest] OK hedef dry-run: {dr['_status']}", file=sys.stderr)
        conn.close()
        print("[selftest] TÜM TESTLER GEÇTİ ✅", file=sys.stderr)
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[selftest] EXCEPTION: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    mcp.run()
