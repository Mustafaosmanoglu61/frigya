"""Authentication routes: email/password + Google OAuth."""
from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth_service
from templates_config import templates

router = APIRouter(prefix="/auth", tags=["auth"])


def _safe_next(next_url: str | None) -> str:
    if not next_url:
        return "/"
    next_url = next_url.strip()
    if not next_url.startswith("/"):
        return "/"
    if next_url.startswith("//"):
        return "/"
    return next_url


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = Query(default="/"),
    error: str = Query(default=""),
    info: str = Query(default=""),
):
    user = auth_service.get_session_user(request)
    if user:
        return RedirectResponse(url=_safe_next(next), status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next_url": _safe_next(next),
        "error": error,
        "info": info,
        "google_enabled": auth_service.get_google_oauth() is not None,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default="/"),
):
    user = auth_service.get_user_by_email(email)
    if not user or not auth_service.verify_password(password, user["password_hash"]):
        target = f"/auth/login?error={quote('E-posta veya şifre hatalı')}&next={quote(_safe_next(next_url))}"
        return RedirectResponse(url=target, status_code=303)

    status = user["approval_status"] if "approval_status" in user.keys() else auth_service.APPROVAL_APPROVED
    if status == auth_service.APPROVAL_PENDING:
        target = f"/auth/login?error={quote('Hesabın site yetkilisinin onayını bekliyor.')}"
        return RedirectResponse(url=target, status_code=303)
    if status == auth_service.APPROVAL_REJECTED:
        target = f"/auth/login?error={quote('Hesabın onaylanmadı. Yönetici ile iletişime geç.')}"
        return RedirectResponse(url=target, status_code=303)

    auth_service.login_user(request, user)
    return RedirectResponse(url=_safe_next(next_url), status_code=303)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, next: str = Query(default="/"), error: str = Query(default="")):
    user = auth_service.get_session_user(request)
    if user:
        return RedirectResponse(url=_safe_next(next), status_code=302)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "next_url": _safe_next(next),
        "error": error,
        "google_enabled": auth_service.get_google_oauth() is not None,
    })


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    next_url: str = Form(default="/"),
):
    email = auth_service.normalize_email(email)
    next_url = _safe_next(next_url)

    if len(password) < 8:
        target = f"/auth/register?error={quote('Şifre en az 8 karakter olmalı')}&next={quote(next_url)}"
        return RedirectResponse(url=target, status_code=303)
    if password != password_confirm:
        target = f"/auth/register?error={quote('Şifreler eşleşmiyor')}&next={quote(next_url)}"
        return RedirectResponse(url=target, status_code=303)
    if auth_service.get_user_by_email(email):
        target = f"/auth/register?error={quote('Bu e-posta zaten kayıtlı')}&next={quote(next_url)}"
        return RedirectResponse(url=target, status_code=303)

    auth_service.create_user(
        email=email,
        password=password,
        role=auth_service.ROLE_USER,
        approval_status=auth_service.APPROVAL_PENDING,
    )
    info = "Kaydın alındı. Hesabın site yetkilisinin onayını bekliyor — onaylandıktan sonra giriş yapabilirsin."
    target = f"/auth/login?info={quote(info)}"
    return RedirectResponse(url=target, status_code=303)


@router.get("/logout")
async def logout(request: Request):
    auth_service.logout_user(request)
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/google/start")
async def google_start(request: Request, next: str = Query(default="/")):
    oauth = auth_service.get_google_oauth()
    if oauth is None:
        return RedirectResponse(
            url=f"/auth/login?error={quote('Google girişi için ortam değişkenleri eksik')}",
            status_code=302,
        )

    next_url = _safe_next(next)
    request.session["oauth_next"] = next_url
    redirect_uri = (
        os.getenv(auth_service.GOOGLE_REDIRECT_URI_ENV, "").strip()
        or str(request.url_for("google_callback"))
    )
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    oauth = auth_service.get_google_oauth()
    if oauth is None:
        return RedirectResponse(
            url=f"/auth/login?error={quote('Google girişi için ortam değişkenleri eksik')}",
            status_code=302,
        )

    next_url = _safe_next(request.session.pop("oauth_next", "/"))

    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if userinfo is None:
            userinfo = await oauth.google.parse_id_token(request, token)
    except Exception:
        return RedirectResponse(
            url=f"/auth/login?error={quote('Google doğrulaması başarısız')}&next={quote(next_url)}",
            status_code=302,
        )

    email = auth_service.normalize_email(userinfo.get("email", ""))
    provider_user_id = str(userinfo.get("sub", "")).strip()
    if not email or not provider_user_id:
        return RedirectResponse(
            url=f"/auth/login?error={quote('Google hesabından e-posta alınamadı')}&next={quote(next_url)}",
            status_code=302,
        )

    user = auth_service.get_linked_google_user(provider_user_id)
    if not user:
        user = auth_service.get_user_by_email(email)
        if not user:
            user = auth_service.create_user(
                email=email,
                password=None,
                role=auth_service.ROLE_USER,
                approval_status=auth_service.APPROVAL_PENDING,
            )
        auth_service.link_google_account(user["id"], provider_user_id)

    status = user["approval_status"] if "approval_status" in user.keys() else auth_service.APPROVAL_APPROVED
    if status == auth_service.APPROVAL_PENDING:
        info = "Google hesabınla kaydın alındı. Hesabın site yetkilisinin onayını bekliyor."
        return RedirectResponse(url=f"/auth/login?info={quote(info)}", status_code=302)
    if status == auth_service.APPROVAL_REJECTED:
        return RedirectResponse(
            url=f"/auth/login?error={quote('Hesabın onaylanmadı. Yönetici ile iletişime geç.')}",
            status_code=302,
        )

    auth_service.login_user(request, user)
    return RedirectResponse(url=next_url, status_code=302)
