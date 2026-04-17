#!/usr/bin/env python3
"""
2026 verilerini SQLite'a yükler:
1. ROBN carry-forward lotlarını ekler (2025'ten 2026'ya devir)
2. Midas CSV'sini parse eder (Pozisyon: Al/Sat, tarih: Güncelleme Saati)
3. recompute_fifo() çalıştırır

Run from webapp/:
    python seed_2026.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import database
from ingestion import insert_rows

CSV_PATH = os.getenv("MIDAS_CSV_PATH", "")

# Year-end carry-forward lots (previous year → current year).
# Real lots (if any) live in data/carry_lots_2026.py (gitignored).
# Copy data/carry_lots_2026.sample.py for a template.
def _load_carry():
    import importlib.util, pathlib
    base = pathlib.Path(__file__).parent.parent / "data"
    real = base / "carry_lots_2026.py"
    sample = base / "carry_lots_2026.sample.py"
    target = real if real.exists() else sample
    if not target.exists():
        return []
    spec = importlib.util.spec_from_file_location("_carry_2026", target)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "CARRY", [])

ROBN_CARRY = _load_carry()


def seed():
    database.init_db()

    # 1. ROBN carry lots
    with database.db() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM carry_forward_lots WHERE symbol='ROBN' AND carry_into_year=2026"
        ).fetchone()[0]

        if existing == 0:
            for sym, lot_date, qty, price, cost in ROBN_CARRY:
                conn.execute(
                    """INSERT INTO carry_forward_lots
                       (symbol, lot_date, quantity, price, cost, carry_into_year, notes)
                       VALUES (?,?,?,?,?,2026,'Manuel devir — CLAUDE.md §6.1')""",
                    (sym, lot_date, qty, price, cost),
                )
            print(f"ROBN carry lots eklendi: {len(ROBN_CARRY)} lot")
        else:
            print(f"ROBN carry lots zaten mevcut, atlandı.")

    # 2. Parse 2026 CSV
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df["Gerçekleşen Miktar"] = pd.to_numeric(df["Gerçekleşen Miktar"], errors="coerce").fillna(0)
    df = df[df["Gerçekleşen Miktar"] > 0].copy()

    rows = []
    skipped_rows = []
    for _, row in df.iterrows():
        pozisyon = str(row["Pozisyon"]).strip().lower()
        if pozisyon in ("al", "alış", "buy"):
            direction = "Alış"
        elif pozisyon in ("sat", "satış", "sell"):
            direction = "Satış"
        else:
            skipped_rows.append(f"Bilinmeyen pozisyon: {row['Pozisyon']!r}")
            continue

        # Tarih: "2026-01-15 14:30:00" → "2026-01-15"
        raw_date = str(row["Güncelleme Saati"]).strip()
        tx_date = raw_date[:10]  # YYYY-MM-DD

        symbol = str(row["Sembol"]).strip().upper()
        qty    = float(row["Gerçekleşen Miktar"])
        price  = float(str(row["Ortalama İşlem Fiyatı"]).replace(",", "."))
        total  = float(str(row["Toplam"]).replace(",", "."))
        year   = int(tx_date[:4])

        # Sadece 2026 ve sonrasını al — 2025 verileri zaten TX listesinden yüklendi
        if year < 2026:
            continue

        rows.append({
            "tx_date":     tx_date,
            "symbol":      symbol,
            "direction":   direction,
            "quantity":    qty,
            "price":       price,
            "total":       total,
            "source_type": "CSV",
            "source_file": os.path.basename(CSV_PATH),
            "source_year": year,
        })

    print(f"\n2026 CSV: {len(df)} gerçekleşen işlem parse edildi")
    if skipped_rows:
        for w in skipped_rows:
            print(f"  Uyarı: {w}")

    with database.db() as conn:
        inserted, skipped = insert_rows(rows, conn)
        print(f"  Eklendi: {inserted}, Atlandı (mükerrer): {skipped}")

    # 3. FIFO yeniden hesapla
    print("\nFIFO yeniden hesaplanıyor...")
    stats = database.recompute_fifo()
    print(f"  Satış sonuçları: {stats['sell_results']}")
    print(f"  Açık pozisyonlar: {stats['open_lots']}")
    print(f"  Semboller: {stats['symbols']}")

    with database.db() as conn:
        for year in [2025, 2026]:
            row = conn.execute("""
                SELECT SUM(sale_proceeds) AS proceeds, SUM(pnl) AS net_pnl,
                       COUNT(*) AS trades,
                       SUM(CASE WHEN eksik_lot=1 THEN 1 ELSE 0 END) AS eksik
                FROM fifo_results WHERE tax_year=?
            """, (year,)).fetchone()
            if row and row["trades"]:
                print(f"\n--- {year} ---")
                print(f"  Satış Geliri: ${row['proceeds']:,.2f}")
                print(f"  Net K/Z:      ${row['net_pnl']:,.2f}")
                print(f"  İşlem:        {row['trades']} ({row['eksik']} eksik lot)")


if __name__ == "__main__":
    seed()
