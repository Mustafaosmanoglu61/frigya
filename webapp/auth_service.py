"""Authentication and authorization service layer."""
from __future__ import annotations

import os
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import HTTPException, Request

import database

try:
    from authlib.integrations.starlette_client import OAuth
except Exception:  # pragma: no cover - optional dependency in local dev
    OAuth = None

ROLE_ADMIN = "admin"
ROLE_USER = "user"
SESSION_USER_ID_KEY = "user_id"

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"

INITIAL_ADMIN_EMAIL_ENV = "INITIAL_ADMIN_EMAIL"
INITIAL_ADMIN_PASSWORD_ENV = "INITIAL_ADMIN_PASSWORD"

GOOGLE_CLIENT_ID_ENV = "GOOGLE_CLIENT_ID"
GOOGLE_CLIENT_SECRET_ENV = "GOOGLE_CLIENT_SECRET"
GOOGLE_REDIRECT_URI_ENV = "GOOGLE_REDIRECT_URI"

PBKDF2_ALGO = "sha256"
PBKDF2_ITERATIONS = 200_000


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if not password_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        _algo, salt, digest_hex = password_hash.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            PBKDF2_ALGO,
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def create_user(
    email: str,
    password: Optional[str],
    role: str = ROLE_USER,
    approval_status: str = APPROVAL_PENDING,
):
    email = normalize_email(email)
    if not email:
        raise ValueError("Email boş olamaz")
    password_hash = hash_password(password) if password else None
    with database.db() as conn:
        cur = conn.execute(
            """INSERT INTO users (email, password_hash, role, is_active, approval_status)
               VALUES (?, ?, ?, 1, ?)""",
            (email, password_hash, role, approval_status),
        )
        return conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()


def is_approved(user) -> bool:
    try:
        return user is not None and user["approval_status"] == APPROVAL_APPROVED
    except (KeyError, IndexError):
        # Legacy row without the column — treat as approved for backwards compat
        return user is not None


def approve_user(admin_id: int, user_id: int) -> None:
    with database.db() as conn:
        conn.execute(
            """UPDATE users
               SET approval_status=?, approved_by=?, approved_at=datetime('now')
               WHERE id=?""",
            (APPROVAL_APPROVED, admin_id, user_id),
        )


def reject_user(admin_id: int, user_id: int) -> None:
    # is_active=1 kalır ki login denemesinde net "reddedildi" mesajı gösterilebilsin
    with database.db() as conn:
        conn.execute(
            """UPDATE users
               SET approval_status=?, approved_by=?, approved_at=datetime('now')
               WHERE id=?""",
            (APPROVAL_REJECTED, admin_id, user_id),
        )


def count_pending_users() -> int:
    with database.db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE approval_status=? AND is_active=1",
            (APPROVAL_PENDING,),
        ).fetchone()
    return int(row["c"] or 0)


def get_user_by_email(email: str):
    email = normalize_email(email)
    with database.db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email=? AND is_active=1",
            (email,),
        ).fetchone()


def get_user_by_id(user_id: int):
    with database.db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id=? AND is_active=1",
            (user_id,),
        ).fetchone()


def get_linked_google_user(provider_user_id: str):
    with database.db() as conn:
        return conn.execute(
            """
            SELECT u.*
            FROM oauth_accounts oa
            JOIN users u ON u.id = oa.user_id
            WHERE oa.provider = 'google'
              AND oa.provider_user_id = ?
              AND u.is_active = 1
            """,
            (provider_user_id,),
        ).fetchone()


def link_google_account(user_id: int, provider_user_id: str):
    with database.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO oauth_accounts (provider, provider_user_id, user_id)
            VALUES ('google', ?, ?)
            """,
            (provider_user_id, user_id),
        )


def login_user(request: Request, user_row) -> None:
    request.session[SESSION_USER_ID_KEY] = user_row["id"]
    # Reset per-user portfolio selection on sign in
    request.session.pop("portfolio", None)


def logout_user(request: Request) -> None:
    request.session.clear()


def get_session_user(request: Request):
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None
    user = get_user_by_id(int(user_id))
    if not user or not is_approved(user):
        request.session.pop(SESSION_USER_ID_KEY, None)
        return None
    return user


def require_current_user(request: Request):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Oturum gerekli")
    return user


def require_admin_user(request: Request):
    user = require_current_user(request)
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    return user


def get_google_oauth() -> Optional[OAuth]:
    if OAuth is None:
        return None
    client_id = os.getenv(GOOGLE_CLIENT_ID_ENV, "").strip()
    client_secret = os.getenv(GOOGLE_CLIENT_SECRET_ENV, "").strip()
    redirect_uri = os.getenv(GOOGLE_REDIRECT_URI_ENV, "").strip()
    if not (client_id and client_secret and redirect_uri):
        return None

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def ensure_identity_bootstrap() -> None:
    """
    Ensure identity tables exist, seed initial admin, and migrate tenant columns.
    """
    admin_email_env = os.getenv(INITIAL_ADMIN_EMAIL_ENV, "").strip()
    admin_password_env = os.getenv(INITIAL_ADMIN_PASSWORD_ENV, "").strip()
    admin_email = normalize_email(admin_email_env or "admin@example.local")
    admin_password = admin_password_env or "ChangeThisAdminPass123!"

    with database.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                email            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash    TEXT,
                role             TEXT    NOT NULL CHECK(role IN ('admin', 'user')) DEFAULT 'user',
                is_active        INTEGER NOT NULL DEFAULT 1,
                approval_status  TEXT    NOT NULL DEFAULT 'pending',
                approved_by      INTEGER,
                approved_at      TEXT,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

            CREATE TABLE IF NOT EXISTS oauth_accounts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                provider          TEXT    NOT NULL,
                provider_user_id  TEXT    NOT NULL,
                user_id           INTEGER NOT NULL REFERENCES users(id),
                created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(provider, provider_user_id)
            );
            CREATE INDEX IF NOT EXISTS ix_oauth_user ON oauth_accounts(user_id);
            """
        )

        # Migrate legacy users table: add approval columns if missing, auto-approve existing users.
        user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "approval_status" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'approved'")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_users_approval ON users(approval_status)")
        if "approved_by" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN approved_by INTEGER")
        if "approved_at" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN approved_at TEXT")

        admin = conn.execute(
            "SELECT * FROM users WHERE email=?",
            (admin_email,),
        ).fetchone()
        if not admin:
            password_hash = hash_password(admin_password)
            cur = conn.execute(
                """
                INSERT INTO users (email, password_hash, role, is_active, approval_status)
                VALUES (?, ?, 'admin', 1, 'approved')
                """,
                (admin_email, password_hash),
            )
            admin = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        else:
            if admin["role"] != ROLE_ADMIN:
                conn.execute("UPDATE users SET role='admin' WHERE id=?", (admin["id"],))
                admin = conn.execute("SELECT * FROM users WHERE id=?", (admin["id"],)).fetchone()
            if not admin["password_hash"] and admin_password:
                conn.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (hash_password(admin_password), admin["id"]),
                )
                admin = conn.execute("SELECT * FROM users WHERE id=?", (admin["id"],)).fetchone()
            if admin["approval_status"] != APPROVAL_APPROVED:
                conn.execute(
                    "UPDATE users SET approval_status='approved' WHERE id=?",
                    (admin["id"],),
                )
                admin = conn.execute("SELECT * FROM users WHERE id=?", (admin["id"],)).fetchone()

        admin_id = int(admin["id"])

    schema_changed = database.ensure_multitenant_schema(admin_id)
    if schema_changed:
        database.recompute_fifo()
