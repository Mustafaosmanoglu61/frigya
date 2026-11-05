#!/usr/bin/env python3
"""
frigya_mcp — Frigya portföy analiz MCP servisi, YEREL stdio modu.

Mimari ilke (kullanıcının tasarımı): SERVİS DB'ye erişir, client/skill doğrudan değil.
Bu server yerelde çalışır, ~/Tax_Portfolilo/webapp/tax.db'ye sahiptir.

Canlı veri için bu server'a gerek yok: aynı araçlar Frigya webapp'inde Streamable HTTP olarak
`https://frigya.ottomantion.com/mcp` adresinde çalışır (webapp/mcp_http.py); istemci kişisel
token'la bağlanır (Yönetim → MCP Erişimi).

Tasarım: İş mantığı `frigya_core` paketinde (importable, subprocess YOK); araç tanımları
`frigya_core.mcp_tools`'ta, iki taşıma (stdio / HTTP) için ortak → tek hakikat kaynağı.

Massive Market verisi: server API'ye çağrı yapmaz. `frigya_sembol_analiz` opsiyonel
`market_json` passthrough alır (client Massive MCP'sinden çeker, JSON olarak geçirir).

Ortam değişkenleri:
  DB_PATH — SQLite yolu (default: ~/Tax_Portfolilo/webapp/tax.db otomatik bulunur)
  FRIGYA_USER_ID / FRIGYA_USER_EMAIL — hangi kullanıcı (yoksa admin)
"""
import os
import sys

from mcp.server.fastmcp import FastMCP

# frigya_core'u bu dizinden import edilebilir kıl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frigya_core as fc
from frigya_core import mcp_tools as t

mcp = FastMCP("frigya_mcp")


def _resolve_local(_ctx, user):
    """DB: DB_PATH env / bilinen konumlar. Kullanıcı: `user` param > env > admin (open_conn)."""
    return None, user


t.register_tools(mcp, _resolve_local)


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:
    sym = os.getenv("SELFTEST_SYMBOL", "IREX")
    pf_name = os.getenv("SELFTEST_PORTFOLIO", "family")
    print(f"[selftest] frigya_core v{fc.__version__} · yerel DB", file=sys.stderr)
    try:
        out = t.sembol_analiz(t.SembolAnalizInput(symbol=sym))
        print(f"[selftest] OK sembol_analiz({sym}): open_qty="
              f"{out.get('position',{}).get('open_qty')} · "
              f"synthesis={[k for k,v in out.get('synthesis',{}).items() if v]}", file=sys.stderr)
        md = fc.render_markdown(out)
        print(f"[selftest] OK render_markdown: {len(md.splitlines())} satır", file=sys.stderr)
        pf = t.portfoy_tara(t.PortfoyInput())
        print(f"[selftest] OK portfoy: open_count={pf['meta']['open_count']}", file=sys.stderr)
        dr = t.hedef_guncelle(t.HedefGuncelleInput(symbol=sym, portfolio=pf_name, stop=33.0, apply=False))
        print(f"[selftest] OK hedef dry-run: {dr['_status']}", file=sys.stderr)
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
