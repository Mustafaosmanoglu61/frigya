import base64
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth_service
import database
from templates_config import templates
import ingestion

router = APIRouter(prefix="/api")


class IngestPayload(BaseModel):
    type: str                      # "csv" | "pdf" | "rows"
    filename: Optional[str] = "upload"
    content_b64: Optional[str] = None   # base64-encoded file content
    rows: Optional[List[dict]] = None   # pre-parsed rows (type="rows")


class IngestResult(BaseModel):
    inserted: int
    skipped: int
    warnings: List[str]
    recompute: dict


@router.post("/ingest", response_model=IngestResult)
async def ingest_file(request: Request, payload: IngestPayload):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    portfolio = request.session.get("portfolio")
    if not portfolio:
        raise HTTPException(400, "Önce bir portföy seçin")

    filename = payload.filename or "upload"

    try:
        if payload.type == "rows":
            if not payload.rows:
                raise HTTPException(400, "rows boş olamaz")
            rows, warnings = ingestion.parse_rows(payload.rows, source_file=filename)

        elif payload.type in ("csv", "pdf"):
            if not payload.content_b64:
                raise HTTPException(400, "content_b64 gerekli")
            content = base64.b64decode(payload.content_b64)

            if payload.type == "csv":
                rows, warnings = ingestion.parse_csv(content, filename=filename)
            else:
                rows, warnings = ingestion.parse_pdf(content, filename=filename)
        else:
            raise HTTPException(400, f"Bilinmeyen tip: {payload.type!r}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, str(e))

    for row in rows:
        row["portfolio"] = portfolio
        row["user_id"] = user_id

    with database.db() as conn:
        inserted, skipped = ingestion.insert_rows(rows, conn)
        conn.execute(
            """INSERT INTO ingestion_log
               (filename, file_type, rows_found, rows_inserted, rows_skipped, status, user_id)
               VALUES (?,?,?,?,?,?,?)""",
            (filename,
             "CSV" if payload.type == "csv" else "PDF" if payload.type == "pdf" else "MANUAL",
             len(rows), inserted, skipped, "success", user_id),
        )

    stats = database.recompute_fifo()

    return IngestResult(
        inserted=inserted,
        skipped=skipped,
        warnings=warnings,
        recompute=stats,
    )


@router.post("/recalculate")
async def recalculate():
    stats = database.recompute_fifo()
    return {"status": "ok", "stats": stats}


@router.get("/stats")
async def stats(request: Request):
    user = auth_service.require_current_user(request)
    user_id = int(user["id"])
    with database.db() as conn:
        tx_count = conn.execute("SELECT COUNT(*) FROM raw_transactions WHERE user_id = ?", (user_id,)).fetchone()[0]
        sell_count = conn.execute("SELECT COUNT(*) FROM fifo_results WHERE user_id = ?", (user_id,)).fetchone()[0]
        open_count = conn.execute("SELECT COUNT(DISTINCT symbol) FROM open_positions WHERE user_id = ?", (user_id,)).fetchone()[0]
        last_ingest = conn.execute(
            "SELECT filename, ingested_at FROM ingestion_log WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return {
        "transactions": tx_count,
        "sell_results": sell_count,
        "open_symbols": open_count,
        "last_ingest": dict(last_ingest) if last_ingest else None,
    }
