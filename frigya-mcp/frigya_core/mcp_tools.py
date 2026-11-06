"""
frigya_core.mcp_tools — frigya MCP'nin 7 aracı; iki taşıma da aynı tanımları kullanır.

  stdio (yerel)           : frigya-mcp/server.py   → yerel tax.db, kullanıcı `user` param/env/admin
  Streamable HTTP (uzak)  : webapp/mcp_http.py     → sunucu DB'si, kullanıcı Bearer token'dan

register_tools(mcp, resolve, check_portfolio=None)
  resolve(ctx, user) -> (db_path, user_id)      db_path/user_id None ise open_conn varsayılanları
  check_portfolio(user_id, portfolio)           yazma araçlarından önce; geçersizse ValueError

Bu modül `mcp` paketine bağlıdır; frigya_core/__init__ onu import etmez (çekirdek mcp'siz de çalışır).
"""
import asyncio
import json
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import Context

from .config import open_conn
from .db import portfoy_data
from .davranis import davranis_data
from .massive_fetch import fetch_market
from .sentez import build_sentez
from .render import render_markdown, render_html
from .yazma import hedef_guncelle as _hedef_guncelle, analist_hedef as _analist_hedef


def _err(e: Exception) -> str:
    return json.dumps({"error": True, "type": type(e).__name__, "message": str(e)[:500]},
                      ensure_ascii=False)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


_USER_DESC = ("Hangi kullanıcı: email veya numerik id. Boşsa FRIGYA_USER_ID/FRIGYA_USER_EMAIL env, yoksa admin. "
              "Uzak MCP'de yok sayılır (kullanıcı token'dan gelir).")


# ---------------------------------------------------------------------------
# Pydantic giriş modelleri
# ---------------------------------------------------------------------------
class SembolAnalizInput(BaseModel):
    """frigya_sembol_analiz girişi."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    symbol: str = Field(..., description="Hisse sembolü (örn. 'RKLB', 'IREX')", min_length=1, max_length=12)
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele (örn. 'family'). Boşsa tüm portföyler birleşir.")
    user: Optional[str] = Field(default=None, description=_USER_DESC)
    market: bool = Field(
        default=False,
        description=(
            "True ise sunucu güncel fiyat, teknik gösterge, haber ve şirket bilgisini Massive'den kendi "
            "anahtarıyla çeker (birkaç saniye sürer). Anahtar tanımlı değilse data_gaps'te belirtilir."
        ),
    )
    market_json: Optional[str] = Field(
        default=None,
        description=(
            "Opsiyonel Massive Market verisi (passthrough); market=true ise yok sayılır. Client önce Massive MCP'sinden çeker, "
            "şu yapıda JSON string geçirir: "
            "{\"teknik\": {\"sma\":..., \"rsi\":..., \"macd\":..., \"daily\": \"<aggs CSV>\"}, "
            "\"haber\": \"<news CSV>\", \"meta\": {\"overview\": \"<csv>\", \"related\": \"<csv>\", "
            "\"market_status\": \"<csv>\"}}. Verilmezse sadece DB analizi yapılır."
        ),
    )


class PortfoyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")
    user: Optional[str] = Field(default=None, description=_USER_DESC)


class DavranisInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")
    year: Optional[int] = Field(default=None, description="Tek yıla filtrele (örn. 2026).", ge=2000, le=2100)
    user: Optional[str] = Field(default=None, description=_USER_DESC)


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
# Araç gövdeleri (senkron; taşımadan bağımsız — selftest de bunları çağırır)
# ---------------------------------------------------------------------------
def sembol_analiz(params: SembolAnalizInput, db_path=None, user_id=None) -> dict:
    market = json.loads(params.market_json) if params.market_json else None
    prefetched = fetch_market(params.symbol) if params.market else None
    return build_sentez(params.symbol, portfolio=params.portfolio, market=market,
                        prefetched_market=prefetched, db_path=db_path, user_id=user_id)


def portfoy_tara(params: PortfoyInput, db_path=None, user_id=None) -> dict:
    conn, _path, uid = open_conn(db_path, user_id)
    try:
        return portfoy_data(conn, uid, params.portfolio)
    finally:
        conn.close()


def davranis_analiz(params: DavranisInput, db_path=None, user_id=None) -> dict:
    conn, _path, uid = open_conn(db_path, user_id)
    try:
        return davranis_data(conn, uid, params.portfolio, params.year)
    finally:
        conn.close()


def hedef_guncelle(params: HedefGuncelleInput, db_path=None, user_id=None) -> dict:
    conn, _path, uid = open_conn(db_path, user_id)
    try:
        return _hedef_guncelle(
            conn, uid, params.symbol, params.portfolio,
            hedef=params.hedef, taban=params.taban, stop=params.stop,
            note=params.note, apply=params.apply,
        )
    finally:
        conn.close()


def analist_hedef(params: AnalistHedefInput, db_path=None, user_id=None) -> dict:
    conn, _path, uid = open_conn(db_path, user_id)
    try:
        return _analist_hedef(
            conn, uid, params.symbol, params.portfolio,
            low=params.low, high=params.high, source=params.source,
            analyst=params.analyst, target_date=params.target_date, apply=params.apply,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MCP kaydı
# ---------------------------------------------------------------------------
_READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}


def register_tools(mcp, resolve, check_portfolio=None):
    """7 aracı verilen FastMCP örneğine kaydeder (bkz. modül docstring'i)."""

    async def _run(fn, params, ctx, user=None, portfolio=None):
        db_path, uid = resolve(ctx, user)

        def work():
            if check_portfolio and portfolio is not None:
                check_portfolio(uid, portfolio)
            return fn(params, db_path, uid)

        # DB işi thread'de: uzak modda webapp'in event loop'unu bloklamasın
        return _dump(await asyncio.to_thread(work))

    @mcp.tool(name="frigya_sembol_analiz",
              annotations={"title": "Sembol Analizi (DB + notlar + opsiyonel piyasa)", **_READ})
    async def frigya_sembol_analiz(params: SembolAnalizInput, ctx: Context) -> str:
        """Bir sembolün komple Frigya sentezini üretir (frigya_core.build_sentez).

        DB'den: trade geçmişi, FIFO K/Z, açık pozisyon + ortalama maliyet, hedef/taban/stop,
        symbol_notes + portfolio_notes (seviye/earnings/tez parse edilmiş), davranış istatistikleri.
        market=true ise (veya market_json verilirse) Massive teknik (SMA/RSI/MACD), haber sentiment,
        şirket meta birleşir.

        Args:
            params (SembolAnalizInput): symbol, portfolio?, market?, market_json? (Massive passthrough)

        Returns:
            str: Sentez JSON (references/sentez_sema.md). Üst seviye: meta, position,
            frigya_history, targets, market, notes, news, company_meta, synthesis, data_gaps.
        """
        try:
            return await _run(sembol_analiz, params, ctx, params.user)
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_portfoy_tara",
              annotations={"title": "Portföy Taraması (açık pozisyonlar + watchlist + hedefler)", **_READ})
    async def frigya_portfoy_tara(params: PortfoyInput, ctx: Context) -> str:
        """Tüm açık pozisyonları + watchlist + tanımlı hedef/stop'ları tek JSON'da döker.

        Args:
            params (PortfoyInput): portfolio (Optional[str])

        Returns:
            str: JSON {meta{open_count, total_cost_basis_usd}, positions[], watchlist_only[]}
        """
        try:
            return await _run(portfoy_tara, params, ctx, params.user)
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_davranis_analiz",
              annotations={"title": "Davranış Analizi (paternler, sektör, hold süresi)", **_READ})
    async def frigya_davranis_analiz(params: DavranisInput, ctx: Context) -> str:
        """Kullanıcının genel trade davranış paternlerini hesaplar.

        Sektör başarı, hold süresi dağılımı, aylık trend, en iyi/zayıf semboller, win/loss oranı.

        Args:
            params (DavranisInput): portfolio?, year?

        Returns:
            str: JSON {overall{}, best_symbols[], worst_symbols[], tag_breakdown[],
                 hold_duration_distribution[], monthly_trend[], open_positions_snapshot{}}
        """
        try:
            return await _run(davranis_analiz, params, ctx, params.user)
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_render_markdown", annotations={"title": "Sentez → Markdown", **_READ})
    async def frigya_render_markdown(params: RenderInput) -> str:
        """Sentez JSON'unu kompakt Türkçe markdown'a dönüştürür.

        Args:
            params (RenderInput): sentez_json (frigya_sembol_analiz çıktısı)

        Returns:
            str: Markdown metin
        """
        try:
            return render_markdown(json.loads(params.sentez_json))
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_render_html",
              annotations={"title": "Sentez → HTML artifact (Chart.js grafikli)", **_READ})
    async def frigya_render_html(params: RenderInput) -> str:
        """Sentez JSON'unu kompakt HTML artifact'a dönüştürür (açık tema + Chart.js fiyat grafiği).

        Grafik için market.bars gerekir (market_json ile analiz yapıldıysa dolu olur).

        Args:
            params (RenderInput): sentez_json

        Returns:
            str: Tek dosya HTML
        """
        try:
            return render_html(json.loads(params.sentez_json))
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_hedef_guncelle",
              annotations={"title": "Taktiksel Hedef/Stop Güncelle (DB yazma)", **_WRITE})
    async def frigya_hedef_guncelle(params: HedefGuncelleInput, ctx: Context) -> str:
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
            return await _run(hedef_guncelle, params, ctx, portfolio=params.portfolio)
        except Exception as e:
            return _err(e)

    @mcp.tool(name="frigya_analist_hedef",
              annotations={"title": "Analyst Range Güncelle (uzun vade hedef/taban, DB yazma)", **_WRITE})
    async def frigya_analist_hedef(params: AnalistHedefInput, ctx: Context) -> str:
        """Uzun vade analyst fiyat aralığını yazar: high→hedef_fiyat, low→taban_fiyat. stop dokunulmaz.

        GÜVENLİK: apply=False (default) → DRY-RUN. Onay sonrası apply=True.
        apply=True'da symbol_notes'a 'analyst-range' prefix'li kayıt düşer.

        Args:
            params (AnalistHedefInput): symbol, portfolio, low?, high?, source?, analyst?, target_date?, apply

        Returns:
            str: JSON {symbol, portfolio, source, before{}, after{}, changes{}, _status}
        """
        try:
            return await _run(analist_hedef, params, ctx, portfolio=params.portfolio)
        except Exception as e:
            return _err(e)
