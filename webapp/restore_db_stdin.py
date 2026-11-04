"""
stdin'den gelen (gzip + base64) SQLite DB'yi canlı DB_PATH'e geri yükler.

Railway container'ında çalışır; local tarafı scripts/railway_db_push.sh:
    gzip -c snap.db | base64 | railway ssh -- python /app/restore_db_stdin.py <sha256>

Güvenlik/sağlamlık:
- sha256 eşleşmezse hiçbir şeye dokunmaz
- integrity_check 'ok' değilse dokunmaz
- hedef DB önce aynı volume'a yedeklenir
- SQLite backup API ile sayfa kopyası (çalışan uygulamanın dosya inode'u değişmez,
  admin /api/restore-sqlite ile aynı yöntem)
"""
import base64
import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

import auth_service
import database


def main() -> int:
    if len(sys.argv) != 2:
        print("kullanım: python restore_db_stdin.py <sha256>", file=sys.stderr)
        return 2
    expected_sha = sys.argv[1].strip().lower()

    payload = gzip.decompress(base64.b64decode(sys.stdin.buffer.read()))
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != expected_sha:
        print(f"sha256 uyuşmuyor: {actual_sha} != {expected_sha}", file=sys.stderr)
        return 1

    fd, src = tempfile.mkstemp(prefix="restore-", suffix=".db", dir="/tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        with sqlite3.connect(src) as conn:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            print(f"integrity_check başarısız: {check}", file=sys.stderr)
            return 1

        dst = database.ensure_db_path_ready()
        if os.path.exists(dst):
            backup = f"{dst}.backup-{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
            shutil.copy2(dst, backup)
            print("hedef yedeklendi:", backup)

        with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
            s.backup(d)
        database.init_db()
        auth_service.ensure_identity_bootstrap()

        with sqlite3.connect(dst) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        print(f"restore tamam: {dst} — raw_transactions={rows}, users={users}")
        return 0
    finally:
        os.remove(src)


if __name__ == "__main__":
    sys.exit(main())
