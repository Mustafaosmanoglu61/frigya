#!/bin/sh
# Local SQLite DB'yi Railway volume'una taşır (railway ssh, stdin pipe).
#
#   ./scripts/railway_db_push.sh [local_db]      # varsayılan: webapp/tax.db
#
# 1) Local DB'den WAL-güvenli anlık görüntü (sqlite3 .backup) + integrity_check
# 2) gzip+base64 → `railway ssh` stdin → container'da webapp/restore_db_stdin.py
#    sha256 + integrity doğrular, hedefi yedekler, SQLite backup API ile yükler
#
# Önkoşul: repo kökünde `railway link` ile frigya servisi bağlı olmalı.
# Veri yalnızca Railway'in SSH kanalından geçer; repoya/imaja/URL'ye yazılmaz.
set -eu

SRC_DB="${1:-webapp/tax.db}"
[ -f "$SRC_DB" ] || { echo "DB bulunamadı: $SRC_DB" >&2; exit 1; }

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
SNAP="$TMP_DIR/snapshot.db"

sqlite3 "$SRC_DB" ".backup '$SNAP'"
CHECK="$(sqlite3 "$SNAP" 'PRAGMA integrity_check;')"
[ "$CHECK" = "ok" ] || { echo "integrity_check başarısız: $CHECK" >&2; exit 1; }

SHA="$(shasum -a 256 "$SNAP" | cut -d' ' -f1)"
ROWS="$(sqlite3 "$SNAP" 'SELECT COUNT(*) FROM raw_transactions;')"
echo "Anlık görüntü: $(du -h "$SNAP" | cut -f1), raw_transactions=$ROWS"

gzip -c "$SNAP" | base64 | railway ssh -- python /app/restore_db_stdin.py "$SHA"
