"""
Birleşik ALL profili — bayatlık durumu ve elle tetiklenen senkron.

TASARIM KARARI — neden otomatik değil
    sync_all_profile.main() hedef profili silip sıfırdan kurar ve sonunda
    database.recompute_fifo() çağırır; bu TÜM kullanıcıların türetilmiş
    tablolarını truncate edip yeniden hesaplar. Login'e veya sayfa açılışına
    bağlanırsa, o sırada admin/mustafa oturumdaysa verileri saniyelerce yarım
    görünür. Bu yüzden yazma işlemi yalnızca kullanıcının açık isteğiyle olur;
    arayüz sadece "bayat" uyarısı gösterir.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import i18n
import auth_service
import sync_all_profile

router = APIRouter()


def _not_applicable():
    return JSONResponse({"applicable": False, "stale": False})


@router.get("/api/all-profile/status")
async def all_profile_status(request: Request):
    """Bayatlık durumu. Yalnızca ALL profilinde anlamlı; diğerlerinde sessizce boş döner."""
    user = auth_service.require_current_user(request)
    st = await run_in_threadpool(sync_all_profile.get_status)

    if not st["exists"] or int(user["id"]) != st["uid"]:
        return _not_applicable()

    diffs = st.get("diffs", {})
    missing = diffs.get("raw_transactions", {}).get("delta", 0)
    cash    = diffs.get("cash_transactions", {}).get("delta", 0)
    return JSONResponse({
        "applicable": True,
        "stale":      st["stale"],
        "last_sync":  st["last_sync"],
        "missing_tx":   missing,
        "missing_cash": cash,
        "diffs":      diffs,
    })


@router.post("/api/all-profile/sync")
async def all_profile_sync(request: Request):
    """Senkronu elle çalıştır — yalnızca ALL profilinin kendisi tetikleyebilir."""
    user = auth_service.require_current_user(request)
    uid = await run_in_threadpool(sync_all_profile.get_target_uid)

    if uid is None:
        return JSONResponse({"error": i18n.tx(request, "Birleşik profil bulunamadı")}, status_code=404)
    if int(user["id"]) != uid:
        return JSONResponse(
            {"error": i18n.tx(request, "Bu işlem yalnızca birleşik profilden yapılabilir")}, status_code=403
        )

    try:
        await run_in_threadpool(sync_all_profile.main)
    except Exception as e:
        return JSONResponse({"error": i18n.tx(request, "Senkron başarısız: {err}", err=e)}, status_code=500)

    st = await run_in_threadpool(sync_all_profile.get_status)
    return JSONResponse({"ok": True, "stale": st["stale"], "last_sync": st["last_sync"]})
