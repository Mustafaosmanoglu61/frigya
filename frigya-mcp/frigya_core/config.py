"""
frigya_core.config — DB yolu çözümü, kullanıcı tespiti, ortak HTML yardımcıları.

Kütüphane kodu: sys.exit yerine exception fırlatır.
"""
import os
import re
import sqlite3
from html import unescape


def find_db_path(explicit=None):
    """SQLite yolunu çöz. Öncelik: explicit > DB_PATH env > bilinen konumlar."""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.getenv("DB_PATH", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    for c in [
        os.path.expanduser("~/Tax_Portfolilo/webapp/tax.db"),
        os.path.expanduser("~/Tax_Portfolilo/tax.db"),
        "./webapp/tax.db",
        "./tax.db",
    ]:
        if os.path.isfile(c):
            return os.path.abspath(c)
    raise FileNotFoundError(
        "DB bulunamadı. DB_PATH env değişkeni verin veya tax.db'yi "
        "~/Tax_Portfolilo/webapp/ altına koyun."
    )


def detect_user_id(conn, explicit=None):
    """Admin kullanıcıyı tercih et, yoksa ilk kullanıcı, yoksa 1."""
    if explicit:
        return int(explicit)
    row = conn.execute(
        "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return int(row[0])
    row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    return int(row[0]) if row else 1


def open_conn(db_path=None, user_id=None):
    """(conn, path, user_id) döndürür. Servis DB sahibi — tek giriş noktası."""
    path = find_db_path(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    uid = detect_user_id(conn, user_id)
    return conn, path, uid


def html_to_plain(html):
    """HTML not → düz metin (görseller [GÖRSEL] placeholder'ı olur)."""
    if not html:
        return ""
    s = html
    s = re.sub(r"<img[^>]*>", " [GÖRSEL] ", s, flags=re.IGNORECASE)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</li\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def html_short(html, max_chars=140):
    """HTML not → tek satır kısa özet."""
    if not html:
        return ""
    s = re.sub(r"<img[^>]*>", " [GÖRSEL] ", html, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


def parse_date(s):
    return (s or "")[:10]
