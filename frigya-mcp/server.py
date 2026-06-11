#!/usr/bin/env python3
"""
frigya_mcp — Frigya portföy analiz MCP servisi.

Mimari ilke (kullanıcının tasarımı):
  SERVİS DB'ye erişir, skill doğrudan değil.
  Bu server yerelde çalışır, ~/Tax_Portfolilo/webapp/tax.db'ye sahiptir.
  Claude Desktop (veya herhangi bir MCP client) bu server'ı çağırır;
  sandbox'taki skill/agent yerel dosyaya hiç dokunmaz.

Tasarım:
  Bu server, mevcut frigya-analiz skill scriptlerini (data/analiz/yazma/render
  katmanları) subprocess ile sarmalar. Scriptler tek hakikat kaynağıdır (SSOT);
  burada iş mantığı tekrar edilmez.

Massive Market verisi:
  Bu server Massive API'sine doğrudan ÇAĞRI YAPMAZ (key gerektirmez). Bunun yerine
  `frigya_sembol_analiz` aracı opsiyonel bir `market_json` passthrough alır:
  Client (Claude Desktop) önce Massive MCP'sini çağırır, sonucu market_json olarak
  bu araca geçirir. Böylece teknik + DB + notlar burada birleşir.

Ortam değişkenleri:
  FRIGYA_SCRIPTS_DIR — skill scriptlerinin kök dizini
                       (default: ~/.claude/skills/frigya-analiz/scripts)
  DB_PATH            — SQLite yolu (default: scriptler kendi bulur ~/Tax_Portfolilo/webapp/tax.db)
"""
import asyncio
import json
import os
import sys
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Konfigürasyon
# ---------------------------------------------------------------------------
DEFAULT_SCRIPTS_DIR = os.path.expanduser("~/.claude/skills/frigya-analiz/scripts")
SCRIPTS_DIR = os.path.abspath(os.path.expanduser(
    os.getenv("FRIGYA_SCRIPTS_DIR", DEFAULT_SCRIPTS_DIR)
))

mcp = FastMCP("frigya_mcp")


# ---------------------------------------------------------------------------
# Paylaşılan yardımcılar
# ---------------------------------------------------------------------------
def _script_path(rel: str) -> str:
    """Scripts köküne göre tam yol döndürür (örn. 'analiz/sentez.py')."""
    return os.path.join(SCRIPTS_DIR, rel)


def _child_env() -> dict:
    """Alt sürece geçecek ortam — DB_PATH varsa forward edilir (servis DB sahibi)."""
    env = dict(os.environ)
    return env


async def _run_script(rel: str, args: list, stdin_str: Optional[str] = None) -> str:
    """
    Bir frigya scriptini subprocess ile çalıştırır, stdout (JSON/metin) döndürür.

    sys.executable kullanılır — server hangi Python'da çalışıyorsa scriptler de
    onunla çalışır (scriptler 3.9+ uyumlu, sadece stdlib kullanır).

    Hata durumunda eyleme yönelik bir mesaj fırlatır.
    """
    path = _script_path(rel)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Script bulunamadı: {path}. FRIGYA_SCRIPTS_DIR doğru mu? "
            f"(şu an: {SCRIPTS_DIR})"
        )

    proc = await asyncio.create_subprocess_exec(
        sys.executable, path, *args,
        stdin=asyncio.subprocess.PIPE if stdin_str is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_child_env(),
    )
    stdin_bytes = stdin_str.encode("utf-8") if stdin_str is not None else None
    out, err = await proc.communicate(input=stdin_bytes)

    if proc.returncode != 0:
        msg = (err or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"{rel} hata kodu {proc.returncode} ile bitti: {msg[:400]}"
        )
    return (out or b"").decode("utf-8", "replace")


def _err(e: Exception) -> str:
    """Tutarlı, eyleme yönelik hata mesajı (JSON döner ki client parse edebilsin)."""
    return json.dumps({
        "error": True,
        "type": type(e).__name__,
        "message": str(e)[:500],
    }, ensure_ascii=False)


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
            "Opsiyonel Massive Market verisi (passthrough). Client önce Massive MCP'sinden "
            "çeker, şu yapıda JSON string geçirir: "
            "{\"teknik\": {\"sma\":..., \"rsi\":..., \"macd\":..., \"daily\": \"<aggs CSV>\"}, "
            "\"haber\": \"<news CSV>\", \"meta\": {\"overview\": \"<csv>\", \"related\": \"<csv>\", "
            "\"market_status\": \"<csv>\"}}. Verilmezse sadece DB analizi yapılır."
        ),
    )


class PortfoyInput(BaseModel):
    """frigya_portfoy_tara girişi."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")


class DavranisInput(BaseModel):
    """frigya_davranis_analiz girişi."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    portfolio: Optional[str] = Field(default=None, description="Tek portföye filtrele. Boşsa hepsi.")
    year: Optional[int] = Field(default=None, description="Tek yıla filtrele (örn. 2026).", ge=2000, le=2100)


class RenderInput(BaseModel):
    """Render araçları girişi."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    sentez_json: str = Field(..., description="frigya_sembol_analiz çıktısı olan tam sentez JSON string'i.", min_length=2)


class HedefGuncelleInput(BaseModel):
    """frigya_hedef_guncelle girişi — taktiksel stop/hedef yazımı."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    symbol: str = Field(..., description="Hisse sembolü", min_length=1, max_length=12)
    portfolio: str = Field(..., description="Hedeflerin yazılacağı portföy (zorunlu)", min_length=1)
    hedef: Optional[float] = Field(default=None, description="Hedef fiyat ($)")
    taban: Optional[float] = Field(default=None, description="Taban/destek fiyat ($)")
    stop: Optional[float] = Field(default=None, description="Stop fiyat ($) — taktiksel risk yönetimi")
    note: Optional[str] = Field(default=None, description="symbol_notes'a düşülecek neden notu")
    apply: bool = Field(default=False, description="True ise DB'ye YAZAR. False (default) ise dry-run: before/after gösterir, yazmaz.")


class AnalistHedefInput(BaseModel):
    """frigya_analist_hedef girişi — uzun vade analyst range yazımı."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    symbol: str = Field(..., description="Hisse sembolü", min_length=1, max_length=12)
    portfolio: str = Field(..., description="Portföy (zorunlu)", min_length=1)
    low: Optional[float] = Field(default=None, description="Analyst low target → taban_fiyat")
    high: Optional[float] = Field(default=None, description="Analyst high target → hedef_fiyat")
    source: Optional[str] = Field(default="manuel", description="Kaynak (örn. 'TradingView', 'Bölüm 8')")
    target_date: Optional[str] = Field(default=None, description="Analyst hedef vadesi (örn. '12 ay')")
    apply: bool = Field(default=False, description="True ise DB'ye YAZAR. False (default) dry-run.")


# ---------------------------------------------------------------------------
# Araçlar — OKUMA
# ---------------------------------------------------------------------------
@mcp.tool(
    name="frigya_sembol_analiz",
    annotations={
        "title": "Sembol Analizi (DB + notlar + opsiyonel piyasa)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def frigya_sembol_analiz(params: SembolAnalizInput) -> str:
    """Bir sembolün komple Frigya sentezini üretir (sentez.py orkestratörü).

    DB'den şunları toplar: trade geçmişi, FIFO K/Z, açık pozisyon + ortalama maliyet,
    tanımlı hedef/taban/stop, symbol_notes + portfolio_notes (seviye/earnings/tez parse
    edilmiş), bu semboldeki davranış istatistikleri. market_json verilirse Massive teknik
    (SMA/RSI/MACD), haber sentiment'i ve şirket meta'sı da birleştirilir.

    Args:
        params (SembolAnalizInput):
            - symbol (str): Sembol, örn. 'RKLB'
            - portfolio (Optional[str]): Portföy filtresi
            - market_json (Optional[str]): Massive passthrough (bkz. field açıklaması)

    Returns:
        str: Sentez JSON (references/sentez_sema.md şeması). Üst seviye alanlar:
        {
          "meta": {symbol, tag, as_of, ...},
          "position": {open_qty, avg_cost, cost_basis, lots[], (market varsa) unrealized},
          "frigya_history": {realized_count, win_rate_pct, avg_hold_days, net_pnl, recent_trades[]},
          "targets": [{portfolio, hedef, taban, stop}],
          "market": {last_close, sma10/20/50, rsi14, macd{}, high_60d, drawdown_from_peak, bars[]} | {"_status":"not_fetched"},
          "notes": {symbol_notes_raw[], portfolio_notes_raw[], parsed_overlay{stop,taban,hedef_min,hedef_max}, earnings_hint, ...},
          "news": {articles[], sentiment_summary{}} | null,
          "company_meta": {name, market_cap_fmt, related_tickers[], market_status{}} | null,
          "synthesis": {current_state, target_position, note_evaluation, behavioral_warning, short_term_view, long_term_view, actionable_decision, open_questions[]},
          "data_gaps": [...]
        }

    Examples:
        - "RKLB analiz et" → symbol="RKLB" (market_json yoksa DB-only)
        - Piyasa dahil tam analiz → önce Massive MCP'den veri çek, market_json olarak geçir
        - Render için: bu çıktıyı frigya_render_markdown / frigya_render_html'e ver
    """
    try:
        args = [params.symbol]
        if params.portfolio:
            args += ["--portfolio", params.portfolio]
        stdin_str = None
        if params.market_json:
            args.append("--with-market")
            stdin_str = params.market_json
        return await _run_script("analiz/sentez.py", args, stdin_str=stdin_str)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="frigya_portfoy_tara",
    annotations={
        "title": "Portföy Taraması (açık pozisyonlar + watchlist + hedefler)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def frigya_portfoy_tara(params: PortfoyInput) -> str:
    """Tüm açık pozisyonları + watchlist + tanımlı hedef/stop'ları tek JSON'da döker.

    Hangi sembollerin hedefe/stop'a yakın olduğunu, hangilerinde not olduğunu görmek için.

    Args:
        params (PortfoyInput): portfolio (Optional[str]) — tek portföye filtre

    Returns:
        str: JSON {meta{open_count, total_cost_basis_usd}, positions[{symbol, total_qty,
             avg_cost, targets{}, note_excerpt}], watchlist_only[]}
    """
    try:
        args = []
        if params.portfolio:
            args += ["--portfolio", params.portfolio]
        return await _run_script("data/db_portfoy.py", args)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="frigya_davranis_analiz",
    annotations={
        "title": "Davranış Analizi (paternler, sektör, hold süresi)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def frigya_davranis_analiz(params: DavranisInput) -> str:
    """Kullanıcının genel trade davranış paternlerini hesaplar.

    Sektör (tag) bazlı başarı, hold süresi dağılımı (intraday/swing/uzun), aylık K/Z trendi,
    en başarılı/zayıf semboller, win/loss oranı, açık pozisyon sektör konsantrasyonu.

    Args:
        params (DavranisInput): portfolio (Optional[str]), year (Optional[int])

    Returns:
        str: JSON {overall{win_rate_pct, roi_pct, avg_hold_days, win_loss_ratio},
             best_symbols[], worst_symbols[], tag_breakdown[], hold_duration_distribution[],
             monthly_trend[], open_positions_snapshot{}}
    """
    try:
        args = []
        if params.portfolio:
            args += ["--portfolio", params.portfolio]
        if params.year:
            args += ["--year", str(params.year)]
        return await _run_script("analiz/davranis.py", args)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Araçlar — RENDER
# ---------------------------------------------------------------------------
@mcp.tool(
    name="frigya_render_markdown",
    annotations={
        "title": "Sentez → Markdown",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def frigya_render_markdown(params: RenderInput) -> str:
    """Sentez JSON'unu kompakt Türkçe markdown'a dönüştürür (chat'e yapıştırmaya hazır).

    Args:
        params (RenderInput): sentez_json (str) — frigya_sembol_analiz çıktısı

    Returns:
        str: Markdown metin (pozisyon, piyasa, hedef, notlar, geçmiş, haber, karar)
    """
    try:
        return await _run_script("render/markdown.py", [], stdin_str=params.sentez_json)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="frigya_render_html",
    annotations={
        "title": "Sentez → HTML artifact (Chart.js grafikli)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def frigya_render_html(params: RenderInput) -> str:
    """Sentez JSON'unu kompakt HTML artifact'a dönüştürür (açık tema + Chart.js fiyat grafiği).

    Grafik için market.bars verisi gerekir (market_json ile analiz yapıldıysa dolu olur).

    Args:
        params (RenderInput): sentez_json (str) — frigya_sembol_analiz çıktısı

    Returns:
        str: Tek dosya HTML (style + body + opsiyonel Chart.js script)
    """
    try:
        return await _run_script("render/html.py", [], stdin_str=params.sentez_json)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Araçlar — YAZMA (onay sonrası; default dry-run)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="frigya_hedef_guncelle",
    annotations={
        "title": "Taktiksel Hedef/Stop Güncelle (DB yazma)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def frigya_hedef_guncelle(params: HedefGuncelleInput) -> str:
    """Bir sembolün taktiksel hedef/taban/stop seviyelerini symbol_targets'a yazar.

    GÜVENLİK: apply=False (default) iken DRY-RUN — sadece before/after/changes döner, YAZMAZ.
    Önce dry-run göster, kullanıcı onaylarsa apply=True ile tekrar çağır.
    apply=True'da symbol_notes'a otomatik bir kayıt da düşer (timestamp + diff).

    Args:
        params (HedefGuncelleInput): symbol, portfolio (zorunlu), hedef?, taban?, stop?, note?, apply

    Returns:
        str: JSON {symbol, portfolio, before{}, after{}, changes{}, _status, (apply ise) note_added}
    """
    try:
        args = [params.symbol, "--portfolio", params.portfolio]
        if params.hedef is not None:
            args += ["--hedef", str(params.hedef)]
        if params.taban is not None:
            args += ["--taban", str(params.taban)]
        if params.stop is not None:
            args += ["--stop", str(params.stop)]
        if params.note:
            args += ["--not", params.note]
        if not params.apply:
            args.append("--dry-run")
        return await _run_script("yazma/hedef_guncelle.py", args)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="frigya_analist_hedef",
    annotations={
        "title": "Analyst Range Güncelle (uzun vade hedef/taban, DB yazma)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def frigya_analist_hedef(params: AnalistHedefInput) -> str:
    """Uzun vade analyst fiyat aralığını yazar: high→hedef_fiyat, low→taban_fiyat. stop dokunulmaz.

    GÜVENLİK: apply=False (default) DRY-RUN. Onay sonrası apply=True.
    apply=True'da symbol_notes'a 'analyst-range' prefix'li kayıt düşer.

    Args:
        params (AnalistHedefInput): symbol, portfolio, low?, high?, source?, target_date?, apply

    Returns:
        str: JSON {symbol, portfolio, source, before{}, after{}, changes{}, _status}
    """
    try:
        args = [params.symbol, "--portfolio", params.portfolio]
        if params.low is not None:
            args += ["--low", str(params.low)]
        if params.high is not None:
            args += ["--high", str(params.high)]
        if params.source:
            args += ["--source", params.source]
        if params.target_date:
            args += ["--target-date", params.target_date]
        if params.apply:
            args.append("--apply")
        return await _run_script("yazma/analist_hedef.py", args)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Selftest (MCP client olmadan hızlı doğrulama)
# ---------------------------------------------------------------------------
async def _selftest() -> int:
    print(f"[selftest] SCRIPTS_DIR = {SCRIPTS_DIR}", file=sys.stderr)
    print(f"[selftest] python = {sys.executable}", file=sys.stderr)
    sym = os.getenv("SELFTEST_SYMBOL", "IREX")
    try:
        out = await frigya_sembol_analiz(SembolAnalizInput(symbol=sym))
        d = json.loads(out)
        if d.get("error"):
            print(f"[selftest] FAIL sembol_analiz: {d}", file=sys.stderr)
            return 1
        print(f"[selftest] OK sembol_analiz({sym}): position.open_qty="
              f"{d.get('position',{}).get('open_qty')} · "
              f"synthesis keys={[k for k,v in d.get('synthesis',{}).items() if v]}", file=sys.stderr)

        md = await frigya_render_markdown(RenderInput(sentez_json=out))
        print(f"[selftest] OK render_markdown: {len(md.splitlines())} satır", file=sys.stderr)

        pf = await frigya_portfoy_tara(PortfoyInput())
        pfd = json.loads(pf)
        print(f"[selftest] OK portfoy_tara: open_count="
              f"{pfd.get('meta',{}).get('open_count')}", file=sys.stderr)

        dr = await frigya_hedef_guncelle(HedefGuncelleInput(
            symbol=sym, portfolio="family", stop=33.0, apply=False))
        drd = json.loads(dr)
        print(f"[selftest] OK hedef_guncelle dry-run: _status={drd.get('_status')}", file=sys.stderr)

        print("[selftest] TÜM TESTLER GEÇTİ ✅", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"[selftest] EXCEPTION: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(asyncio.run(_selftest()))
    mcp.run()
