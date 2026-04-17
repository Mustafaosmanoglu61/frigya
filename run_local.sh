#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEBAPP_DIR="$ROOT_DIR/webapp"

if [[ ! -d "$WEBAPP_DIR" ]]; then
  echo "webapp klasoru bulunamadi: $WEBAPP_DIR"
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo ".env bulunamadi. .env.example kopyalaniyor..."
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "Olusturuldu: $ROOT_DIR/.env"
fi

python3 -m pip install -r "$WEBAPP_DIR/requirements.txt"
exec python3 -m uvicorn webapp.main:app --reload --host 127.0.0.1 --port 8000
