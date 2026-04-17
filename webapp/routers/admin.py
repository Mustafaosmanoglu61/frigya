"""Admin panel: PDF/CSV upload, portfolio management."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from datetime import datetime
import hmac
import io
import json
import sqlite3
import tempfile
import shutil
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
from ingestion import parse_csv, parse_pdf, insert_rows
from portfolio_helper import get_portfolios, get_all_portfolios_with_data, create_portfolio, delete_portfolio
import pdfplumber

router = APIRouter(prefix="/yonetim", tags=["yonetim"])

RESTORE_TOKEN_ENV = "DB_RESTORE_TOKEN"
MAX_SQLITE_UPLOAD_MB = 200


def _validate_sqlite_file(path: str) -> None:
    """Raise ValueError if uploaded file is not a usable SQLite database."""
    try:
        with sqlite3.connect(path) as conn:
            # Touch schema + quick integrity check before replacing live DB.
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            check = conn.execute("PRAGMA quick_check").fetchone()
            status = (check[0] if check else "").lower()
            if status != "ok":
                raise ValueError(f"SQLite doğrulama başarısız: {status or 'bilinmeyen hata'}")
    except sqlite3.Error as exc:
        raise ValueError(f"Geçersiz SQLite dosyası: {exc}") from exc

@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request):
    """Yönetim dashboard — tüm giriş yapmış kullanıcılara açık."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    is_admin = user["role"] == auth_service.ROLE_ADMIN
    portfolio_data = get_all_portfolios_with_data(user_id)
    portfolios = get_portfolios(user_id)

    all_users = []
    pending_users = []
    if is_admin:
        with database.db() as conn:
            rows = conn.execute(
                "SELECT id, email, role, is_active, approval_status, approved_at, created_at "
                "FROM users ORDER BY created_at ASC"
            ).fetchall()
            all_users = [dict(r) for r in rows]
            pending_rows = conn.execute(
                "SELECT id, email, created_at FROM users "
                "WHERE approval_status=? AND is_active=1 ORDER BY created_at ASC",
                (auth_service.APPROVAL_PENDING,),
            ).fetchall()
            pending_users = [dict(r) for r in pending_rows]

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "portfolio_data": portfolio_data,
        "portfolios": portfolios,
        "is_admin": is_admin,
        "all_users": all_users,
        "pending_users": pending_users,
        "pending_count": len(pending_users),
        "current_user_id": user_id,
        "active": "admin",
    })


@router.post("/portföy-ekle")
async def add_portfolio_form(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
):
    """Add a new portfolio."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    name = name.strip()
    description = description.strip()

    if not name:
        return RedirectResponse(url="/yonetim?error=Portföy%20adı%20boş%20olamaz", status_code=303)

    if create_portfolio(user_id, name, description):
        return RedirectResponse(url=f"/yonetim?success={name}%20portföyü%20oluşturuldu", status_code=303)
    else:
        return RedirectResponse(url=f"/yonetim?error={name}%20portföyü%20zaten%20var", status_code=303)


@router.post("/portföy-sil/{portfolio_name}")
async def delete_portfolio_form(request: Request, portfolio_name: str):
    """Delete a portfolio (marks as inactive)."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio_name = portfolio_name.strip()

    if not portfolio_name:
        return RedirectResponse(url="/yonetim?error=Portföy%20adı%20geçersiz", status_code=303)

    if delete_portfolio(user_id, portfolio_name):
        return RedirectResponse(url=f"/yonetim?success={portfolio_name}%20portföyü%20silindi", status_code=303)
    else:
        return RedirectResponse(url=f"/yonetim?error=Silme%20başarısız", status_code=303)


@router.get("/old", response_class=HTMLResponse)
async def admin_home_old(request: Request):
    """Admin dashboard (old version - kept for compatibility)."""
    user = auth_service.require_admin_user(request)
    user_id = int(user["id"])
    with database.db() as conn:
        portfolios = conn.execute(
            "SELECT DISTINCT portfolio FROM raw_transactions WHERE user_id = ? ORDER BY portfolio",
            (user_id,),
        ).fetchall()
        port_list = [p["portfolio"] for p in portfolios]

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Admin - Frigya</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <nav class="navbar navbar-dark bg-primary-custom">
            <div class="container-fluid">
                <span class="navbar-brand">Frigya Admin</span>
                <a href="/" class="btn btn-light btn-sm">← Back</a>
            </div>
        </nav>

        <div class="container-fluid p-4">
            <div class="row">
                <div class="col-md-6">
                    <div class="card mb-3">
                        <div class="card-header">Portfolio Seçimi</div>
                        <div class="card-body">
                            <select id="portfolio" class="form-select">
                                <option value="">-- Yeni Portfolio --</option>
                                {chr(10).join(f'<option value="{p}">{p}</option>' for p in port_list)}
                            </select>
                            <input type="text" id="new_portfolio" class="form-control mt-2" placeholder="Portfolio adı (yeni ise)">
                        </div>
                    </div>

                    <div class="card mb-3">
                        <div class="card-header">PDF Yükleme (Aylık Özet)</div>
                        <div class="card-body">
                            <input type="file" id="pdf_file" accept=".pdf" class="form-control">
                            <button onclick="uploadPDF()" class="btn btn-primary mt-2 w-100">Yükle</button>
                            <div id="pdf_status" class="mt-2"></div>
                        </div>
                    </div>
                </div>

                <div class="col-md-6">
                    <div class="card mb-3">
                        <div class="card-header">CSV Yükleme (Emir Geçmişi)</div>
                        <div class="card-body">
                            <input type="file" id="csv_file" accept=".csv" class="form-control">
                            <button onclick="uploadCSV()" class="btn btn-primary mt-2 w-100">Yükle</button>
                            <div id="csv_status" class="mt-2"></div>
                        </div>
                    </div>

                    <div class="card mb-3">
                        <div class="card-header">FIFO Yeniden Hesapla</div>
                        <div class="card-body">
                            <button onclick="recompute()" class="btn btn-warning w-100">Hesapla</button>
                            <div id="compute_status" class="mt-2"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card mt-4">
                <div class="card-header">İşlem Geçmişi</div>
                <div id="logs" class="card-body" style="max-height: 300px; overflow-y: auto;">
                </div>
            </div>
        </div>

        <script src="/static/js/charts.js"></script>
        <style>
            .bg-primary-custom {{ background-color: #1F4E79; }}
        </style>
        <script>
        async function uploadPDF() {{
            const file = document.getElementById('pdf_file').files[0];
            const portfolio = document.getElementById('portfolio').value || document.getElementById('new_portfolio').value;
            if (!file || !portfolio) {{
                alert('Portfolio ve PDF dosya seçiniz');
                return;
            }}

            const formData = new FormData();
            formData.append('file', file);
            formData.append('portfolio', portfolio);

            document.getElementById('pdf_status').innerHTML = '<span class="badge bg-info">Yükleniyor...</span>';

            const resp = await fetch('/admin/api/upload-pdf', {{method: 'POST', body: formData}});
            const data = await resp.json();

            if (resp.ok) {{
                document.getElementById('pdf_status').innerHTML =
                    `<span class="badge bg-success">Başarılı: ${{data.inserted}} eklendi, ${{data.skipped}} mükerrer</span>`;
                loadLogs();
            }} else {{
                document.getElementById('pdf_status').innerHTML =
                    `<span class="badge bg-danger">Hata: ${{data.error}}</span>`;
            }}
        }}

        async function uploadCSV() {{
            const file = document.getElementById('csv_file').files[0];
            const portfolio = document.getElementById('portfolio').value || document.getElementById('new_portfolio').value;
            if (!file || !portfolio) {{
                alert('Portfolio ve CSV dosya seçiniz');
                return;
            }}

            const formData = new FormData();
            formData.append('file', file);
            formData.append('portfolio', portfolio);

            document.getElementById('csv_status').innerHTML = '<span class="badge bg-info">Yükleniyor...</span>';

            const resp = await fetch('/admin/api/upload-csv', {{method: 'POST', body: formData}});
            const data = await resp.json();

            if (resp.ok) {{
                document.getElementById('csv_status').innerHTML =
                    `<span class="badge bg-success">Başarılı: ${{data.inserted}} eklendi, ${{data.skipped}} mükerrer</span>`;
                loadLogs();
            }} else {{
                document.getElementById('csv_status').innerHTML =
                    `<span class="badge bg-danger">Hata: ${{data.error}}</span>`;
            }}
        }}

        async function recompute() {{
            document.getElementById('compute_status').innerHTML = '<span class="badge bg-info">Hesaplanıyor...</span>';
            const resp = await fetch('/admin/api/recompute', {{method: 'POST'}});
            const data = await resp.json();

            if (resp.ok) {{
                document.getElementById('compute_status').innerHTML =
                    `<span class="badge bg-success">Başarılı: ${{data.sell_results}} satış işlemi</span>`;
            }} else {{
                document.getElementById('compute_status').innerHTML =
                    `<span class="badge bg-danger">Hata: ${{data.error}}</span>`;
            }}
        }}

        async function loadLogs() {{
            const resp = await fetch('/admin/api/logs');
            const logs = await resp.json();
            const html = logs.map(l =>
                `<div class="text-sm"><strong>${{l.filename}}</strong> - ${{l.rows_inserted}} eklendi, ${{l.status}}</div>`
            ).join('');
            document.getElementById('logs').innerHTML = html || 'Henüz işlem yok';
        }}

        loadLogs();
        </script>
    </body>
    </html>
    """

@router.post("/api/upload-pdf")
async def upload_pdf(request: Request, file: UploadFile = File(...), portfolio: str = Form(...)):
    """Upload and parse PDF."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    if portfolio not in get_portfolios(user_id):
        raise HTTPException(status_code=400, detail="Geçersiz portföy")
    try:
        content = await file.read()
        rows, _warnings = parse_pdf(content, filename=file.filename or "upload.pdf")

        # Add portfolio
        for row in rows:
            row['portfolio'] = portfolio
            row['user_id'] = user_id

        with database.db() as conn:
            inserted, skipped = insert_rows(rows, conn)

        return {"inserted": inserted, "skipped": skipped, "portfolio": portfolio}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...), portfolio: str = Form(...)):
    """Upload and parse CSV."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    if portfolio not in get_portfolios(user_id):
        raise HTTPException(status_code=400, detail="Geçersiz portföy")
    try:
        content = await file.read()
        text = content.decode('utf-8-sig')

        rows, _warnings = parse_csv(text, filename=file.filename or "upload.csv")

        # Add portfolio
        for row in rows:
            row['portfolio'] = portfolio
            row['user_id'] = user_id

        with database.db() as conn:
            inserted, skipped = insert_rows(rows, conn)

        return {"inserted": inserted, "skipped": skipped, "portfolio": portfolio}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/recompute")
async def recompute(request: Request):
    """Recompute FIFO for all portfolios (her kullanıcıya açık, kendi verisini etkiler)."""
    auth_service.require_current_user(request)
    try:
        stats = database.recompute_fifo()
        return {"sell_results": stats['sell_results'], "symbols": stats['symbols']}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/logs")
async def get_logs(request: Request):
    """Get ingestion logs."""
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    with database.db() as conn:
        rows = conn.execute(
            "SELECT filename, rows_inserted, rows_skipped, status, ingested_at "
            "FROM ingestion_log WHERE user_id = ? ORDER BY ingested_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/restore-sqlite")
async def restore_sqlite(
    request: Request,
    file: UploadFile = File(...),
    restore_token: str = Form(default=""),
):
    """
    Restore live SQLite database from uploaded .db file.
    Security: requires DB_RESTORE_TOKEN env var and matching form token.
    """
    auth_service.require_admin_user(request)

    expected_token = os.getenv(RESTORE_TOKEN_ENV, "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{RESTORE_TOKEN_ENV} ayarlı değil. "
                "Render Environment bölümünden token ekleyip yeniden deploy edin."
            ),
        )

    if not hmac.compare_digest(restore_token.strip(), expected_token):
        raise HTTPException(status_code=403, detail="Geçersiz restore token")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Boş dosya yüklenemez")
    if len(content) > MAX_SQLITE_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Dosya çok büyük (maks {MAX_SQLITE_UPLOAD_MB} MB)",
        )

    tmp_path = None
    backup_path = None

    try:
        db_path = database.ensure_db_path_ready()

        fd, tmp_path = tempfile.mkstemp(prefix="restore-", suffix=".db", dir="/tmp")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(content)

        _validate_sqlite_file(tmp_path)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        if os.path.exists(db_path):
            backup_path = f"{db_path}.backup-{timestamp}"
            shutil.copy2(db_path, backup_path)

        # Safer than replacing the DB file inode while app is running:
        # copy pages from uploaded DB into the current target file.
        with sqlite3.connect(tmp_path) as src_conn, sqlite3.connect(db_path) as dst_conn:
            src_conn.backup(dst_conn)
            dst_conn.commit()

        # Ensure app-required pragmas/schema exist after restore.
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        database.init_db()
        auth_service.ensure_identity_bootstrap()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"DB restore başarısız: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {
        "ok": True,
        "message": "SQLite restore tamamlandı",
        "db_path": db_path,
        "backup_path": backup_path,
    }


@router.get("/api/users/pending")
async def list_pending_users(request: Request):
    """Onay bekleyen kullanıcılar — admin only."""
    auth_service.require_admin_user(request)
    with database.db() as conn:
        rows = conn.execute(
            "SELECT id, email, created_at FROM users "
            "WHERE approval_status=? AND is_active=1 ORDER BY created_at ASC",
            (auth_service.APPROVAL_PENDING,),
        ).fetchall()
    return {"pending": [dict(r) for r in rows], "count": len(rows)}


@router.post("/api/users/{user_id}/approve")
async def approve_user_endpoint(request: Request, user_id: int):
    """Onayla — admin only."""
    current = auth_service.require_admin_user(request)
    with database.db() as conn:
        target = conn.execute(
            "SELECT id, email, approval_status FROM users WHERE id=? AND is_active=1",
            (user_id,),
        ).fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    auth_service.approve_user(int(current["id"]), user_id)
    return {"ok": True, "user_id": user_id, "approval_status": auth_service.APPROVAL_APPROVED}


@router.post("/api/users/{user_id}/reject")
async def reject_user_endpoint(request: Request, user_id: int):
    """Reddet — admin only. Son admin'i reddetmeye / kendini reddetmeye izin verme."""
    current = auth_service.require_admin_user(request)
    if int(current["id"]) == int(user_id):
        raise HTTPException(status_code=400, detail="Kendi hesabını reddedemezsin")
    with database.db() as conn:
        target = conn.execute(
            "SELECT id, email, role FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        if target["role"] == auth_service.ROLE_ADMIN:
            admin_count = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role=? AND is_active=1",
                (auth_service.ROLE_ADMIN,),
            ).fetchone()["c"]
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Son admin reddedilemez")
    auth_service.reject_user(int(current["id"]), user_id)
    return {"ok": True, "user_id": user_id, "approval_status": auth_service.APPROVAL_REJECTED}


@router.get("/api/users")
async def list_users(request: Request):
    """List all users — admin only."""
    auth_service.require_admin_user(request)
    with database.db() as conn:
        rows = conn.execute(
            "SELECT id, email, role, is_active, created_at "
            "FROM users ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/users/{user_id}/role")
async def set_user_role(request: Request, user_id: int):
    """Change a user's role. Admin only. Prevents demoting the last admin."""
    current = auth_service.require_admin_user(request)
    body = await request.json()
    new_role = (body.get("role") or "").strip().lower()
    if new_role not in (auth_service.ROLE_ADMIN, auth_service.ROLE_USER):
        raise HTTPException(status_code=400, detail="Geçersiz rol")

    with database.db() as conn:
        target = conn.execute(
            "SELECT id, email, role FROM users WHERE id=? AND is_active=1",
            (user_id,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        if target["role"] == auth_service.ROLE_ADMIN and new_role != auth_service.ROLE_ADMIN:
            admin_count = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role=? AND is_active=1",
                (auth_service.ROLE_ADMIN,),
            ).fetchone()["c"]
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Son admin rolü düşürülemez")
            if int(target["id"]) == int(current["id"]):
                raise HTTPException(status_code=400, detail="Kendi admin rolünü düşüremezsin")

        conn.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))

    return {"ok": True, "user_id": user_id, "role": new_role}
