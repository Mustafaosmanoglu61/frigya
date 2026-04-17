#!/usr/bin/env python3
"""
One-time seed: loads the 2025 TX list from data/transactions_2025.py
(or the committed .sample.py) into the SQLite database, then runs the FIFO recompute.

Run from the webapp/ directory:
    python seed_2025.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import database
from ingestion import insert_rows


def _load_tx_list():
    """Load the TX list from data/transactions_2025.py (real) or the committed sample."""
    import importlib.util, pathlib
    base = pathlib.Path(__file__).parent.parent / "data"
    real = base / "transactions_2025.py"
    sample = base / "transactions_2025.sample.py"
    target = real if real.exists() else sample
    if not target.exists():
        raise ValueError("data/transactions_2025(.sample).py bulunamadı")
    spec = importlib.util.spec_from_file_location("_tx_2025_seed", target)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TX


TX = _load_tx_list()


def seed():
    database.init_db()

    rows_2025 = []
    for tx_date, symbol, direction, quantity, price, total in TX:
        year = int(tx_date[:4])
        rows_2025.append({
            "tx_date": tx_date,
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "price": price,
            "total": total,
            "source_type": "MANUAL",
            "source_file": "build_2025_usd.py",
            "source_year": year,
        })

    print(f"2025 TX listesi: {len(rows_2025)} işlem")

    with database.db() as conn:
        inserted, skipped = insert_rows(rows_2025, conn)
        print(f"  Eklendi: {inserted}, Atlandı (mükerrer): {skipped}")

    print("\nFIFO yeniden hesaplanıyor...")
    stats = database.recompute_fifo()
    print(f"  Satış sonuçları: {stats['sell_results']}")
    print(f"  Açık pozisyonlar: {stats['open_lots']}")
    print(f"  Semboller: {stats['symbols']}")

    # Verify key values
    with database.db() as conn:
        total_pnl = conn.execute(
            "SELECT SUM(pnl) FROM fifo_results"
        ).fetchone()[0]
        total_proceeds = conn.execute(
            "SELECT SUM(sale_proceeds) FROM fifo_results"
        ).fetchone()[0]
        eksik = conn.execute(
            "SELECT COUNT(*) FROM fifo_results WHERE eksik_lot=1"
        ).fetchone()[0]
        open_count = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM open_positions"
        ).fetchone()[0]

    print(f"\n--- Özet ---")
    print(f"Toplam Satış Geliri: ${total_proceeds:,.2f}")
    print(f"Net K/Z:             ${total_pnl:,.2f}")
    print(f"Eksik Lot:           {eksik} işlem")
    print(f"Açık Pozisyon:       {open_count} sembol")


if __name__ == "__main__":
    seed()
