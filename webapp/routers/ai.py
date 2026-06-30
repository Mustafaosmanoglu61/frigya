from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    import anthropic
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    anthropic = None

import auth_service
from templates_config import templates
from portfolio_helper import get_selectable_portfolios, resolve_portfolio, is_super

router = APIRouter()

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_SYSTEM_PROMPT = (
    "Sen Frigya'nın AI asistanısın. Kısa, net ve uygulanabilir cevaplar ver."
)


def _extract_text(message) -> str:
    parts = []
    for block in getattr(message, "content", []):
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "")
            if text:
                parts.append(text)
    return "".join(parts).strip()


@router.get("/ai", response_class=HTMLResponse)
async def ai_page(request: Request, portfolio: str = Query(None)):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolios = get_selectable_portfolios(user_id)
    current_portfolio = resolve_portfolio(request, portfolio, user_id)
    return templates.TemplateResponse("ai.html", {
        "request": request,
        "active": "ai",
        "portfolios": portfolios,
        "current_portfolio": current_portfolio,
        "is_super": is_super(current_portfolio),
        "default_model": DEFAULT_MODEL,
    })


@router.post("/api/ai/chat")
async def ai_chat(request: Request):
    auth_service.require_current_user(request)
    if anthropic is None:
        return JSONResponse(
            {"error": "anthropic paketi kurulu değil. requirements yüklenmeli."},
            status_code=500,
        )

    body = await request.json()
    raw_messages = body.get("messages")
    if raw_messages is None and body.get("message"):
        raw_messages = [{"role": "user", "content": body.get("message")}]

    if not isinstance(raw_messages, list):
        return JSONResponse({"error": "messages listesi gerekli."}, status_code=400)

    messages = []
    for item in raw_messages[-30:]:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})

    while messages and messages[0]["role"] != "user":
        messages.pop(0)

    if not messages:
        return JSONResponse({"error": "En az bir kullanıcı mesajı gerekli."}, status_code=400)

    model = body.get("model", DEFAULT_MODEL)
    if not isinstance(model, str) or not model.strip():
        model = DEFAULT_MODEL
    else:
        model = model.strip()

    system_prompt = body.get("system", DEFAULT_SYSTEM_PROMPT)
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        system_prompt = DEFAULT_SYSTEM_PROMPT
    else:
        system_prompt = system_prompt.strip()

    raw_max_tokens = body.get("max_tokens", 4096)
    try:
        max_tokens = int(raw_max_tokens)
    except (TypeError, ValueError):
        max_tokens = 4096
    max_tokens = max(256, min(max_tokens, 8192))

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY tanımlı değil."},
            status_code=500,
        )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            cache_control={"type": "ephemeral"},
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
        )
    except anthropic.AuthenticationError:
        return JSONResponse({"error": "Claude API kimlik doğrulaması başarısız."}, status_code=401)
    except anthropic.PermissionDeniedError:
        return JSONResponse({"error": "Claude API yetki hatası."}, status_code=403)
    except anthropic.RateLimitError as exc:
        retry_after = getattr(exc.response, "headers", {}).get("retry-after", "60")
        return JSONResponse(
            {"error": f"Rate limit aşıldı. {retry_after} sn sonra tekrar dene."},
            status_code=429,
        )
    except anthropic.BadRequestError as exc:
        return JSONResponse({"error": f"Geçersiz istek: {exc.message}"}, status_code=400)
    except anthropic.APIConnectionError:
        return JSONResponse({"error": "Claude API bağlantı hatası."}, status_code=502)
    except anthropic.APIStatusError as exc:
        return JSONResponse({"error": f"Claude API durum hatası ({exc.status_code})."}, status_code=502)

    reply = _extract_text(response) or "(Metin yanıtı alınamadı.)"
    usage = getattr(response, "usage", None)
    usage_payload = {
        "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None) if usage else None,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None) if usage else None,
    }

    return JSONResponse({
        "reply": reply,
        "model": model,
        "usage": usage_payload,
    })
