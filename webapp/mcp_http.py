"""Uzak frigya MCP — Streamable HTTP, `/mcp` (main.py rotaları ve lifespan'i bağlar).

Kimlik: AuthGuardMiddleware `/mcp` için yalnızca kişisel API token'ı kabul eder (session cookie
değil) ve token sahibini request.state.user'a koyar; araçlar o kullanıcının verisinde çalışır,
`user` parametresi yok sayılır. Araç tanımları frigya_core.mcp_tools'ta (stdio ile ortak).
"""
import os
import sys

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import database
from portfolio_helper import get_portfolios

# frigya_core: repo'da ../frigya-mcp, imajda /frigya-mcp (bkz. Dockerfile, routers/frigya_ai.py)
_FRIGYA_MCP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frigya-mcp")
if _FRIGYA_MCP not in sys.path:
    sys.path.insert(0, _FRIGYA_MCP)
from frigya_core import mcp_tools  # noqa: E402

mcp = FastMCP(
    "frigya",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    # SDK localhost'ta Host/Origin kısıtını kendiliğinden açar ve canlı domaini reddeder.
    # /mcp yalnızca Bearer token'la çalıştığı (cookie yok) için DNS rebinding burada risk değil.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _resolve(ctx: Context, _user):
    user = getattr(ctx.request_context.request.state, "user", None)
    if not user:
        raise PermissionError("Geçerli bir API token'ı gerekli")
    return database.get_db_path(), int(user["id"])


def _check_portfolio(user_id: int, portfolio: str) -> None:
    if portfolio not in get_portfolios(user_id):
        raise ValueError(f"portföy bulunamadı: {portfolio}")


mcp_tools.register_tools(mcp, _resolve, _check_portfolio)
