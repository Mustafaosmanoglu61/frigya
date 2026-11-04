# Frigya — Railway imajı. Yalnızca webapp/ kopyalanır; kişisel veri
# (tax.db, yedekler, CSV/PDF) .dockerignore ile imaja hiç girmez.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# sqlite3 CLI: `railway ssh` ile DB bakımı/kontrolü için
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY webapp/requirements.txt .
RUN pip install -r requirements.txt

COPY webapp/ .

# routers/frigya_ai.py, frigya_core'u <app'in bir üstü>/frigya-mcp altında arar → /frigya-mcp.
# Yalnızca paket kodu (*.py) girer; .dockerignore frigya-mcp/'nin geri kalanını dışarıda tutar.
COPY frigya-mcp/frigya_core/ /frigya-mcp/frigya_core/

# DB_PATH Railway volume'una işaret eder (bkz. .railway/railway.ts / Variables)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
