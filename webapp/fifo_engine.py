"""
Pure FIFO engine — no database dependency.
Accepts a sorted list of RawTx and optional CarryLot entries,
returns FifoSellResult list + OpenLot list.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from typing import List, Optional


@dataclass
class RawTx:
    tx_id:     int
    tx_date:   str   # YYYY-MM-DD
    symbol:    str
    direction: str   # 'Alış' | 'Satış'
    quantity:  float
    price:     float
    total:     float


@dataclass
class CarryLot:
    symbol:   str
    lot_date: str
    quantity: float
    price:    float
    cost:     float


@dataclass
class LotMatch:
    buy_tx_id:     Optional[int]   # None = carry lot
    buy_date:      Optional[str]
    buy_price:     Optional[float]
    consumed_qty:  float
    consumed_cost: float
    is_carry_lot:  bool


@dataclass
class FifoSellResult:
    raw_tx_id:     int
    tx_date:       str
    symbol:        str
    quantity:      float
    sale_price:    float
    sale_proceeds: float
    cost_basis:    float
    eksik_lot:     bool
    lot_matches:   List[LotMatch] = field(default_factory=list)


@dataclass
class OpenLot:
    symbol:       str
    lot_seq:      int
    buy_date:     str
    quantity:     float
    buy_price:    float
    cost_basis:   float
    is_carry_lot: bool
    source_tx_id: Optional[int]   # None for carry lots


# Internal queue entry
# [qty, price, cost, tx_id_or_None, date_str, is_carry]
_EPS = 1e-7


def run_fifo(
    transactions: List[RawTx],
    carry_lots:   List[CarryLot],
) -> tuple[List[FifoSellResult], List[OpenLot]]:
    """
    Transactions must already be sorted by (tx_date, tx_id) ascending.
    Carry lots are pre-loaded into the queue before any transactions.
    """
    # queue: symbol → list of [qty, price, cost, tx_id|None, date, is_carry]
    queue: dict[str, list] = defaultdict(list)

    # Pre-load carry lots
    for cl in carry_lots:
        sym = cl.symbol.upper()
        queue[sym].append([cl.quantity, cl.price, cl.cost, None, cl.lot_date, True])

    sell_results: List[FifoSellResult] = []

    for tx in transactions:
        sym = tx.symbol.upper()

        if tx.direction == "Alış":
            queue[sym].append([tx.quantity, tx.price, tx.total, tx.tx_id, tx.tx_date, False])

        else:  # Satış
            kalan      = tx.quantity
            total_cost = 0.0
            eksik_lot  = False
            matches: List[LotMatch] = []

            while kalan > _EPS:
                if not queue[sym]:
                    eksik_lot = True
                    break

                lot = queue[sym][0]
                lot_qty, lot_price, lot_cost, lot_tx_id, lot_date, lot_carry = lot

                if lot_qty <= kalan + _EPS:
                    consumed   = min(lot_qty, kalan)
                    frac       = consumed / lot_qty if lot_qty > 1e-10 else 0.0
                    cost_chunk = lot_cost * frac
                    total_cost += cost_chunk
                    kalan      -= consumed
                    matches.append(LotMatch(
                        buy_tx_id=lot_tx_id,
                        buy_date=lot_date,
                        buy_price=lot_price,
                        consumed_qty=consumed,
                        consumed_cost=cost_chunk,
                        is_carry_lot=lot_carry,
                    ))
                    queue[sym].pop(0)
                else:
                    oran       = kalan / lot_qty
                    cost_chunk = lot_cost * oran
                    total_cost += cost_chunk
                    matches.append(LotMatch(
                        buy_tx_id=lot_tx_id,
                        buy_date=lot_date,
                        buy_price=lot_price,
                        consumed_qty=kalan,
                        consumed_cost=cost_chunk,
                        is_carry_lot=lot_carry,
                    ))
                    queue[sym][0] = [
                        lot_qty - kalan,
                        lot_price,
                        lot_cost - cost_chunk,
                        lot_tx_id,
                        lot_date,
                        lot_carry,
                    ]
                    kalan = 0.0

            sell_results.append(FifoSellResult(
                raw_tx_id=tx.tx_id,
                tx_date=tx.tx_date,
                symbol=sym,
                quantity=tx.quantity,
                sale_price=tx.price,
                sale_proceeds=tx.total,
                cost_basis=total_cost,
                eksik_lot=eksik_lot,
                lot_matches=matches,
            ))

    # Build open positions from remaining queue
    open_lots: List[OpenLot] = []
    for sym, lots in queue.items():
        for seq, lot in enumerate(lots, start=1):
            lot_qty, lot_price, lot_cost, lot_tx_id, lot_date, lot_carry = lot
            if lot_qty > _EPS:
                open_lots.append(OpenLot(
                    symbol=sym,
                    lot_seq=seq,
                    buy_date=lot_date,
                    quantity=lot_qty,
                    buy_price=lot_price,
                    cost_basis=lot_cost,
                    is_carry_lot=lot_carry,
                    source_tx_id=lot_tx_id,
                ))

    return sell_results, open_lots
