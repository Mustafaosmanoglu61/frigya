"""Merkezi Jinja2Templates instance — tüm router'lar buradan import eder."""
import os
from fastapi.templating import Jinja2Templates

_VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION")


def _read_version() -> str:
    try:
        with open(_VERSION_FILE) as f:
            return f.read().strip()
    except Exception:
        return "?"

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


class _TemplatesCompat:
    """
    Keep routers compatible across Starlette template API changes.
    Routers currently call: templates.TemplateResponse(name, context).
    Newer Starlette expects: TemplateResponse(request=..., name=..., context=...).
    """

    def __init__(self, inner: Jinja2Templates):
        self._inner = inner

    @property
    def env(self):
        return self._inner.env

    def __getattr__(self, item):
        return getattr(self._inner, item)

    def TemplateResponse(self, name, context, *args, **kwargs):
        request = context.get("request") if isinstance(context, dict) else None
        if request is not None:
            try:
                return self._inner.TemplateResponse(
                    request=request,
                    name=name,
                    context=context,
                    *args,
                    **kwargs,
                )
            except TypeError:
                # Older Starlette/FastAPI signature
                pass
        return self._inner.TemplateResponse(name, context, *args, **kwargs)


templates = _TemplatesCompat(Jinja2Templates(directory=_TEMPLATES_DIR))

# Version'u Jinja2 global değişkeni olarak kaydet (her template erişebilir)
templates.env.globals["APP_VERSION"] = _read_version()


# ─── Custom Filters ────────────────────────────────────────────────────────

def _fmtqty(value) -> str:
    """
    Sayıyı akıllıca formatla:
    - Tam sayıysa → "69"
    - Ondalıklıysa → max 2 hane, gereksiz sıfırları at → "12.50" → "12.5", "1.00" → "1"
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v == int(v):
        return f"{int(v):,}"
    # 2 ondalık hane, sondaki sıfırları at
    formatted = f"{v:,.2f}".rstrip('0').rstrip('.')
    return formatted


templates.env.filters["fmtqty"] = _fmtqty


def _pending_approvals_count() -> int:
    """Admin navbar rozetinde kullanılır. Hata olursa 0 döner."""
    try:
        import auth_service
        return auth_service.count_pending_users()
    except Exception:
        return 0


templates.env.globals["pending_approvals_count"] = _pending_approvals_count
