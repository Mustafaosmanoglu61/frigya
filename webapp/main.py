"""
Frigya Web Application — FastAPI entry point.

Run:
    cd webapp
    uvicorn main:app --reload --port 8000
"""
import sys
import os
from urllib.parse import quote

# Ensure webapp dir is on the path so imports work
sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in some local setups
    load_dotenv = None

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

import database
import auth_service
from routers import dashboard, islemler, semboller, sembol_detail, pozisyonlar, ingest_api, admin, fiyatlar, auth
from portfolio_helper import get_portfolios, create_portfolio

if load_dotenv:
    WEBAPP_DIR = os.path.dirname(__file__)
    PROJECT_ROOT = os.path.dirname(WEBAPP_DIR)
    # Prefer project-root .env, then webapp/.env if present.
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
    load_dotenv(os.path.join(WEBAPP_DIR, ".env"), override=False)

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
DEFAULT_DEV_SESSION_SECRET = "frigya-dev-secret"
SESSION_TIMEOUT = 20 * 60  # 20 dakika


def get_session_secret() -> str:
    """Use env-backed secret in production, safe fallback in development."""
    session_secret = os.getenv("SESSION_SECRET", "").strip()
    if session_secret:
        return session_secret
    if IS_PRODUCTION:
        raise RuntimeError(
            "SESSION_SECRET environment variable is required when APP_ENV=production."
        )
    return DEFAULT_DEV_SESSION_SECRET


SESSION_SECRET = get_session_secret()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    auth_service.ensure_identity_bootstrap()
    yield


app = FastAPI(title="Frigya", lifespan=lifespan)


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        user = auth_service.get_session_user(request)
        request.state.user = user

        is_public = any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)
        if is_public:
            return await call_next(request)

        if user is None:
            if path.startswith("/api/"):
                return JSONResponse({"error": "Oturum gerekli"}, status_code=401)
            next_url = request.url.path
            if request.url.query:
                next_url = f"{next_url}?{request.url.query}"
            return RedirectResponse(url=f"/auth/login?next={quote(next_url)}", status_code=302)

        return await call_next(request)


# Order matters: Session must wrap auth guard so request.session is available.
app.add_middleware(AuthGuardMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_TIMEOUT,
    same_site="lax",
    https_only=IS_PRODUCTION,
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)

PUBLIC_PATH_PREFIXES = (
    "/static",
    "/auth",
    "/healthz",
)


app.include_router(dashboard.router)
app.include_router(islemler.router)
app.include_router(semboller.router)
app.include_router(sembol_detail.router)
app.include_router(pozisyonlar.router)
app.include_router(ingest_api.router)
app.include_router(admin.router)
app.include_router(fiyatlar.router)
app.include_router(auth.router)


@app.post("/api/session/portfolio")
async def set_session_portfolio(request: Request):
    """Portfolio'yu session'a kaydet."""
    user = auth_service.require_current_user(request)
    body = await request.json()
    portfolio = body.get("portfolio", "").strip()
    portfolios = get_portfolios(int(user["id"]))
    if portfolio not in portfolios:
        return JSONResponse({"error": "Geçersiz portföy"}, status_code=400)
    request.session["portfolio"] = portfolio
    return JSONResponse({"ok": True, "portfolio": portfolio})


@app.get("/api/session/info")
async def get_session_info(request: Request):
    """Session bilgisini döndür."""
    user = auth_service.require_current_user(request)
    portfolio = request.session.get("portfolio")
    portfolios = get_portfolios(int(user["id"]))
    return JSONResponse({
        "portfolio": portfolio,
        "portfolios": portfolios,
        "has_session": portfolio is not None and portfolio in portfolios,
    })


@app.post("/api/portfolio/create")
async def create_portfolio_api(request: Request):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    body = await request.json()
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()

    if len(name) < 2:
        return JSONResponse({"error": "Portföy adı en az 2 karakter olmalı"}, status_code=400)

    ok = create_portfolio(user_id, name, description)
    if not ok:
        return JSONResponse({"error": "Portföy oluşturulamadı veya zaten var"}, status_code=400)

    request.session["portfolio"] = name
    return JSONResponse({"ok": True, "portfolio": name})
