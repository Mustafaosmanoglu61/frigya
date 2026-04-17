"""
Ingestion pipeline: CSV and PDF parsers.
Both return a list of dicts ready to insert into raw_transactions.
"""
from __future__ import annotations
import io
import re
from datetime import datetime
from typing import List

import pandas as pd


def _parse_date(s: str) -> str:
    """Parse various date formats and return YYYY-MM-DD."""
    s = s.strip().split()[0]  # take date part only
    # Already YYYY-MM-DD?
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {s!r}")


def parse_csv(content: bytes | str, filename: str = "midas.csv") -> tuple[List[dict], List[str]]:
    """
    Parse a Midas 'emir-gecmisi-tumu' CSV.
    Returns (rows, warnings).
    Each row: {tx_date, symbol, direction, quantity, price, total, source_type, source_file, source_year}
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")

    df = pd.read_csv(io.StringIO(content), sep=None, engine="python")
    warnings: List[str] = []

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Detect required columns (Turkish names from Midas)
    col_map = {
        "tarih":    _find_col(df, ["Tarih", "Date", "Güncelleme Saati", "Guncelleme Saati"]),
        "islem":    _find_col(df, ["İşlem Tipi", "Islem Tipi", "Type", "Pozisyon"]),
        "sembol":   _find_col(df, ["Sembol", "Symbol"]),
        "gercmik":  _find_col(df, ["Gerçekleşen Miktar", "Gerceklesen Miktar", "Filled Qty"]),
        "ort_fiy":  _find_col(df, ["Ortalama İşlem Fiyatı", "Avg Price"]),
        "toplam":   _find_col(df, ["İşlem Tutarı", "Islem Tutari", "Total", "Toplam"]),
    }

    missing = [k for k, v in col_map.items() if v is None]
    if missing:
        raise ValueError(f"CSV sütunları bulunamadı: {missing}. Sütunlar: {list(df.columns)}")

    # Filter: only executed orders
    gm_col = col_map["gercmik"]
    df[gm_col] = pd.to_numeric(df[gm_col], errors="coerce").fillna(0)
    df = df[df[gm_col] > 0].copy()

    rows: List[dict] = []
    for _, row in df.iterrows():
        try:
            raw_date = str(row[col_map["tarih"]])
            tx_date = _parse_date(raw_date)
            year = int(tx_date[:4])

            raw_dir = str(row[col_map["islem"]]).strip()
            # Map to standard Turkish
            if raw_dir.lower() in ("alış", "alis", "buy", "al"):
                direction = "Alış"
            elif raw_dir.lower() in ("satış", "satis", "sell", "sat"):
                direction = "Satış"
            else:
                warnings.append(f"Bilinmeyen işlem tipi: {raw_dir!r} — satır atlandı")
                continue

            symbol = str(row[col_map["sembol"]]).strip().upper()
            quantity = float(str(row[col_map["gercmik"]]).replace(",", "."))
            price = float(str(row[col_map["ort_fiy"]]).replace(",", "."))
            # Midas CSV bug: Toplam = qty*price + qty. Use qty*price instead.
            total = round(quantity * price, 2)

            rows.append({
                "tx_date": tx_date,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "price": price,
                "total": total,
                "source_type": "CSV",
                "source_file": filename,
                "source_year": year,
            })
        except Exception as e:
            warnings.append(f"Satır atlandı: {e}")

    return rows, warnings


def parse_pdf(content: bytes, filename: str = "ektre.pdf") -> tuple[List[dict], List[str]]:
    """
    Parse a Midas monthly PDF extract.
    Looks for 'Yatırım İşlemleri' section and extracts rows where
    status == 'Gerçekleşti' and gerçekleşen adet > 0.
    Returns (rows, warnings).
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber kurulu değil: pip install pdfplumber")

    warnings: List[str] = []
    rows: List[dict] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(c or "").strip() for c in table[0]]

                # Check if this looks like a transaction table
                if not _is_transaction_table(header):
                    continue

                col_idx = _map_pdf_columns(header)
                if col_idx is None:
                    warnings.append(f"PDF tablo başlıkları tanınamadı: {header}")
                    continue

                for data_row in table[1:]:
                    try:
                        result = _parse_pdf_row(data_row, col_idx, filename, warnings)
                        if result:
                            rows.append(result)
                    except Exception as e:
                        warnings.append(f"PDF satır atlandı: {e}")

    return rows, warnings


def parse_rows(raw_rows: list, source_file: str = "manual") -> tuple[List[dict], List[str]]:
    """
    Accept pre-parsed rows (from agent) in format:
    [{"date": "YYYY-MM-DD", "symbol": "X", "direction": "Alış"/"Satış",
      "quantity": 1.0, "price": 10.0, "total": 10.0}, ...]
    """
    warnings: List[str] = []
    rows: List[dict] = []
    for r in raw_rows:
        try:
            direction = r.get("direction", "").strip()
            if direction not in ("Alış", "Satış"):
                warnings.append(f"Geçersiz direction: {direction!r}")
                continue
            tx_date = r["date"][:10]
            year = int(tx_date[:4])
            rows.append({
                "tx_date": tx_date,
                "symbol": str(r["symbol"]).strip().upper(),
                "direction": direction,
                "quantity": float(r["quantity"]),
                "price": float(r["price"]),
                "total": float(r["total"]),
                "source_type": "MANUAL",
                "source_file": source_file,
                "source_year": year,
            })
        except Exception as e:
            warnings.append(f"Satır atlandı: {e}")
    return rows, warnings


def insert_rows(rows: List[dict], conn) -> tuple[int, int]:
    """Insert rows into raw_transactions, return (inserted, skipped)."""
    inserted = skipped = 0
    for r in rows:
        try:
            portfolio = r.get("portfolio", "")
            user_id = int(r.get("user_id", 0))
            if not portfolio or user_id <= 0:
                skipped += 1
                continue
            conn.execute(
                """INSERT OR IGNORE INTO raw_transactions
                   (tx_date, symbol, direction, quantity, price, total,
                    source_type, source_file, source_year, portfolio, user_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (r["tx_date"], r["symbol"], r["direction"],
                 r["quantity"], r["price"], r["total"],
                 r["source_type"], r["source_file"], r["source_year"], portfolio, user_id),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    return inserted, skipped


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_col(df: pd.DataFrame, candidates: List[str]):
    for c in candidates:
        if c in df.columns:
            return c
    return None


_TX_KEYWORDS = {"sembol", "symbol", "işlem", "islem", "adet", "qty"}


def _is_transaction_table(header: List[str]) -> bool:
    lower = {h.lower() for h in header}
    return bool(lower & _TX_KEYWORDS)


def _map_pdf_columns(header: List[str]) -> dict | None:
    """Map column names → indices for PDF table."""
    mapping = {}
    for i, h in enumerate(header):
        h_l = h.lower()
        if "tarih" in h_l or "date" in h_l:
            mapping.setdefault("tarih", i)
        elif "sembol" in h_l or "symbol" in h_l:
            mapping.setdefault("sembol", i)
        elif "işlem" in h_l and "tipi" in h_l:
            mapping.setdefault("islem_tipi", i)
        elif "adet" in h_l or "miktar" in h_l or "qty" in h_l:
            mapping.setdefault("adet", i)
        elif "fiyat" in h_l or "price" in h_l:
            mapping.setdefault("fiyat", i)
        elif "tutar" in h_l or "total" in h_l or "amount" in h_l:
            mapping.setdefault("tutar", i)
        elif "durum" in h_l or "status" in h_l:
            mapping.setdefault("durum", i)

    required = {"tarih", "sembol", "adet", "fiyat"}
    if not required.issubset(mapping.keys()):
        return None
    return mapping


def _parse_pdf_row(row, col_idx: dict, filename: str, warnings: List[str]) -> dict | None:
    def cell(key):
        idx = col_idx.get(key)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] or "").strip()

    # Filter by status
    durum = cell("durum").lower()
    if "iptal" in durum:
        return None
    # Only process 'gerçekleşti' rows (or if no status column)
    if durum and "gerçekleş" not in durum and "gercekles" not in durum:
        return None

    raw_adet = cell("adet").replace(",", ".")
    if not raw_adet:
        return None
    try:
        adet = float(raw_adet)
    except ValueError:
        return None
    if adet <= 0:
        return None

    raw_date = cell("tarih")
    if not raw_date:
        return None
    tx_date = _parse_date(raw_date)
    year = int(tx_date[:4])

    symbol = cell("sembol").upper()
    if not symbol:
        return None

    raw_islem = cell("islem_tipi").lower()
    if "alış" in raw_islem or "alis" in raw_islem or "buy" in raw_islem:
        direction = "Alış"
    elif "satış" in raw_islem or "satis" in raw_islem or "sell" in raw_islem:
        direction = "Satış"
    else:
        warnings.append(f"PDF işlem tipi tanınamadı: {raw_islem!r}")
        return None

    try:
        price = float(cell("fiyat").replace(",", "."))
        total = float(cell("tutar").replace(",", ".")) if col_idx.get("tutar") else price * adet
    except ValueError:
        warnings.append(f"PDF fiyat/tutar parse hatası: {row}")
        return None

    return {
        "tx_date": tx_date,
        "symbol": symbol,
        "direction": direction,
        "quantity": adet,
        "price": price,
        "total": total,
        "source_type": "PDF",
        "source_file": filename,
        "source_year": year,
    }
