"""Kişisel API token'ları (MCP Erişimi) — oluştur / listele / iptal.

Yalnızca session ile çalışır: /api/tokens token kapsamı dışında (auth_service.in_api_token_scope),
yani bir token kendi kendine yeni token üretemez.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service

router = APIRouter(prefix="/api/tokens", tags=["api-tokens"])


@router.get("")
async def list_tokens(request: Request):
    user = auth_service.require_current_user(request)
    return JSONResponse({"tokens": auth_service.list_api_tokens(int(user["id"]))})


@router.post("")
async def create_token(request: Request):
    user = auth_service.require_current_user(request)
    body = await request.json()
    try:
        row, token = auth_service.create_api_token(int(user["id"]), body.get("name") or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, **row, "token": token})


@router.delete("/{token_id}")
async def revoke_token(request: Request, token_id: int):
    user = auth_service.require_current_user(request)
    if not auth_service.revoke_api_token(int(user["id"]), token_id):
        return JSONResponse({"error": "Token bulunamadı"}, status_code=404)
    return JSONResponse({"ok": True})
