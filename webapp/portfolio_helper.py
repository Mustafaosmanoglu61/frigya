"""Portfolio helper — shared across routers."""
from typing import Optional
import database
from fastapi import Request


def resolve_portfolio(request: Request, query_portfolio: Optional[str], user_id: int) -> Optional[str]:
    """
    Portfolio öncelik sırası:
    1. URL query parametresi (?portfolio=X) → session'a yaz
    2. Session'dan oku
    3. Sistemdeki ilk portföy (fallback)
    """
    portfolios = get_portfolios(user_id)

    # URL'den geliyorsa session'a kaydet
    if query_portfolio and query_portfolio in portfolios:
        request.session["portfolio"] = query_portfolio
        return query_portfolio

    # Session'dan oku
    session_portfolio = request.session.get("portfolio")
    if session_portfolio and session_portfolio in portfolios:
        return session_portfolio

    # Fallback: ilk portföy (yoksa None)
    if portfolios:
        fallback = portfolios[0]
        request.session["portfolio"] = fallback
        return fallback

    request.session.pop("portfolio", None)
    return None


def get_portfolios(user_id: int):
    """Return list of portfolio names for this user."""
    with database.db() as conn:
        # Get from portfolios table
        rows = conn.execute(
            "SELECT name FROM portfolios WHERE user_id = ? AND is_active = 1 ORDER BY name",
            (user_id,),
        ).fetchall()

        # Get from raw_transactions (for backward compatibility)
        tx_rows = conn.execute(
            """
            SELECT DISTINCT portfolio
            FROM raw_transactions
            WHERE user_id = ?
            ORDER BY portfolio
            """,
            (user_id,),
        ).fetchall()

    # Combine and deduplicate
    from_table = [r["name"] for r in rows] if rows else []
    from_tx = [r["portfolio"] for r in tx_rows] if tx_rows else []

    all_portfolios = list(set(from_table + from_tx))
    all_portfolios.sort()

    return all_portfolios


def get_all_portfolios_with_data(user_id: int):
    """Return this user's portfolios with stats."""
    with database.db() as conn:
        # Get from portfolios table + raw_transactions (UNION for completeness)
        rows = conn.execute("""
            SELECT
                p.id, p.name, p.description, p.is_active,
                COUNT(DISTINCT rt.id) as tx_count,
                COUNT(DISTINCT CASE WHEN fr.id IS NOT NULL THEN rt.id END) as sales_count,
                COALESCE(SUM(CASE WHEN fr.id IS NOT NULL THEN fr.sale_proceeds ELSE 0 END), 0) as total_proceeds,
                COALESCE(SUM(CASE WHEN fr.id IS NOT NULL THEN fr.pnl ELSE 0 END), 0) as net_pnl
            FROM portfolios p
            LEFT JOIN raw_transactions rt ON rt.portfolio = p.name AND rt.user_id = p.user_id
            LEFT JOIN fifo_results fr ON fr.raw_tx_id = rt.id AND fr.user_id = p.user_id
            WHERE p.is_active = 1 AND p.user_id = ?
            GROUP BY p.id, p.name, p.description, p.is_active

            UNION ALL

            SELECT
                NULL as id, rt.portfolio as name, NULL as description, 1 as is_active,
                COUNT(DISTINCT rt.id) as tx_count,
                COUNT(DISTINCT CASE WHEN fr.id IS NOT NULL THEN rt.id END) as sales_count,
                COALESCE(SUM(CASE WHEN fr.id IS NOT NULL THEN fr.sale_proceeds ELSE 0 END), 0) as total_proceeds,
                COALESCE(SUM(CASE WHEN fr.id IS NOT NULL THEN fr.pnl ELSE 0 END), 0) as net_pnl
            FROM raw_transactions rt
            LEFT JOIN fifo_results fr ON fr.raw_tx_id = rt.id AND fr.user_id = rt.user_id
            WHERE rt.user_id = ?
              AND rt.portfolio NOT IN (
                    SELECT name FROM portfolios WHERE is_active = 1 AND user_id = ?
              )
            GROUP BY rt.portfolio

            ORDER BY name
        """, (user_id, user_id, user_id)).fetchall()
    return rows


def create_portfolio(user_id: int, name: str, description: str = None) -> bool:
    """Create a new portfolio. Returns True if successful."""
    try:
        with database.db() as conn:
            conn.execute(
                "INSERT INTO portfolios (user_id, name, description) VALUES (?, ?, ?)",
                (user_id, name, description)
            )
        return True
    except Exception as e:
        print(f"Error creating portfolio: {e}")
        return False


def delete_portfolio(user_id: int, name: str) -> bool:
    """Hard delete a portfolio: removes all data from every table, then drops the portfolios row.
    Returns True if successful."""
    try:
        with database.db() as conn:
            # 1. Collect raw_tx IDs for this portfolio (needed for fifo_lot_matches)
            tx_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM raw_transactions WHERE user_id = ? AND portfolio = ?",
                (user_id, name),
            ).fetchall()]

            # 2. Delete fifo_lot_matches referencing these transactions
            if tx_ids:
                placeholders = ",".join("?" * len(tx_ids))
                conn.execute(
                    f"DELETE FROM fifo_lot_matches WHERE sell_tx_id IN ({placeholders})",
                    tx_ids
                )

            # 3. Delete computed tables by portfolio column
            conn.execute("DELETE FROM fifo_results   WHERE user_id = ? AND portfolio = ?", (user_id, name))
            conn.execute("DELETE FROM open_positions  WHERE user_id = ? AND portfolio = ?", (user_id, name))
            conn.execute("DELETE FROM symbol_summary  WHERE user_id = ? AND portfolio = ?", (user_id, name))

            # 4. Delete raw transactions
            conn.execute("DELETE FROM raw_transactions WHERE user_id = ? AND portfolio = ?", (user_id, name))

            # 5. Delete watchlist for this portfolio
            conn.execute("DELETE FROM watchlist WHERE user_id = ? AND portfolio = ?", (user_id, name))

            # 6. Remove from portfolios table (hard delete)
            conn.execute("DELETE FROM portfolios WHERE user_id = ? AND name = ?", (user_id, name))

        return True
    except Exception as e:
        print(f"Error deleting portfolio: {e}")
        return False


def portfolio_filter_sql(table_alias: str = "", param_name: str = "portfolio"):
    """
    Return (where_clause, params_dict) for portfolio filtering.
    If portfolio is None → no filter.
    """
    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}portfolio = :{param_name}"


def get_tx_ids_for_portfolio(conn, user_id: int, portfolio: str):
    """Return set of raw_transaction IDs belonging to a portfolio."""
    rows = conn.execute(
        "SELECT id FROM raw_transactions WHERE user_id = ? AND portfolio = ?",
        (user_id, portfolio),
    ).fetchall()
    return {r["id"] for r in rows}
