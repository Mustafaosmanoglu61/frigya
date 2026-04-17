"""
SQLite connection, schema init, and FIFO recompute orchestration.
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

from fifo_engine import run_fifo, RawTx, CarryLot

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "tax.db")


def get_db_path() -> str:
    """Resolve SQLite path from environment or fall back to local db."""
    configured = os.getenv("DB_PATH", "").strip()
    db_path = configured or DEFAULT_DB_PATH
    return os.path.abspath(os.path.expanduser(db_path))


def ensure_db_path_ready() -> str:
    """
    Fail fast with a clear error when the configured SQLite path is invalid.
    Render should mount its persistent disk before app startup, so a missing
    parent directory usually indicates a bad disk mount or DB_PATH value.
    """
    db_path = get_db_path()
    db_dir = os.path.dirname(db_path) or "."

    if os.path.isdir(db_path):
        raise RuntimeError(
            f"DB_PATH must point to a SQLite file, but got a directory: {db_path}"
        )
    if not os.path.isdir(db_dir):
        raise RuntimeError(
            f"Database directory does not exist: {db_dir}. "
            "Create it or set DB_PATH to a writable file path."
        )
    if not os.access(db_dir, os.W_OK):
        raise RuntimeError(
            f"Database directory is not writable: {db_dir}. "
            "Set DB_PATH to a writable file path."
        )

    return db_path

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS raw_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_date     TEXT    NOT NULL,
    symbol      TEXT    NOT NULL COLLATE NOCASE,
    direction   TEXT    NOT NULL CHECK(direction IN ('Alış','Satış')),
    quantity    REAL    NOT NULL CHECK(quantity > 0),
    price       REAL    NOT NULL CHECK(price >= 0),
    total       REAL    NOT NULL,
    source_type TEXT    NOT NULL CHECK(source_type IN ('PDF','CSV','MANUAL','CARRY')),
    source_file TEXT,
    source_year INTEGER,
    portfolio   TEXT    NOT NULL DEFAULT '2025',
    dedup_key   TEXT    GENERATED ALWAYS AS (
                    tx_date||'|'||upper(symbol)||'|'||direction
                    ||'|'||CAST(ROUND(quantity,9) AS TEXT)
                    ||'|'||CAST(ROUND(price,4)    AS TEXT)
                ) STORED,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_dedup ON raw_transactions(dedup_key);
CREATE INDEX IF NOT EXISTS ix_raw_symbol_date  ON raw_transactions(symbol, tx_date);
CREATE INDEX IF NOT EXISTS ix_raw_date         ON raw_transactions(tx_date);
CREATE INDEX IF NOT EXISTS ix_raw_year         ON raw_transactions(source_year);

CREATE TABLE IF NOT EXISTS carry_forward_lots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    lot_date        TEXT    NOT NULL,
    quantity        REAL    NOT NULL CHECK(quantity > 0),
    price           REAL    NOT NULL,
    cost            REAL    NOT NULL,
    carry_into_year INTEGER NOT NULL,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_carry_sym_year ON carry_forward_lots(symbol, carry_into_year);

CREATE TABLE IF NOT EXISTS fifo_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
    tx_date       TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    quantity      REAL    NOT NULL,
    sale_price    REAL    NOT NULL,
    sale_proceeds REAL    NOT NULL,
    cost_basis    REAL    NOT NULL,
    pnl           REAL    GENERATED ALWAYS AS (sale_proceeds - cost_basis) STORED,
    pnl_pct       REAL    GENERATED ALWAYS AS (
                      CASE WHEN cost_basis > 0.001
                           THEN (sale_proceeds - cost_basis) / cost_basis
                           ELSE NULL END) STORED,
    status        TEXT    GENERATED ALWAYS AS (
                      CASE WHEN (sale_proceeds - cost_basis) >= 0
                           THEN 'KÂR' ELSE 'ZARAR' END) STORED,
    eksik_lot     INTEGER NOT NULL DEFAULT 0,
    tax_year      INTEGER NOT NULL,
    portfolio     TEXT    NOT NULL DEFAULT '',
    computed_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_fifo_symbol    ON fifo_results(symbol);
CREATE INDEX IF NOT EXISTS ix_fifo_date      ON fifo_results(tx_date);
CREATE INDEX IF NOT EXISTS ix_fifo_year      ON fifo_results(tax_year);
CREATE INDEX IF NOT EXISTS ix_fifo_year_date ON fifo_results(tax_year, tx_date);
CREATE INDEX IF NOT EXISTS ix_fifo_portfolio ON fifo_results(portfolio);

CREATE TABLE IF NOT EXISTS fifo_lot_matches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fifo_result_id INTEGER NOT NULL REFERENCES fifo_results(id),
    sell_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
    buy_tx_id      INTEGER REFERENCES raw_transactions(id),
    buy_date       TEXT,
    buy_price      REAL,
    consumed_qty   REAL    NOT NULL,
    consumed_cost  REAL    NOT NULL,
    is_carry_lot   INTEGER NOT NULL DEFAULT 0,
    computed_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_lot_match_result ON fifo_lot_matches(fifo_result_id);
CREATE INDEX IF NOT EXISTS ix_lot_match_sell   ON fifo_lot_matches(sell_tx_id);

CREATE TABLE IF NOT EXISTS open_positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT    NOT NULL COLLATE NOCASE,
    lot_seq      INTEGER NOT NULL,
    buy_date     TEXT    NOT NULL,
    quantity     REAL    NOT NULL,
    buy_price    REAL    NOT NULL,
    cost_basis   REAL    NOT NULL,
    is_carry_lot INTEGER NOT NULL DEFAULT 0,
    source_year  INTEGER,
    portfolio    TEXT    NOT NULL DEFAULT '',
    computed_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_pos_symbol    ON open_positions(symbol);
CREATE INDEX IF NOT EXISTS ix_pos_portfolio ON open_positions(portfolio);

CREATE TABLE IF NOT EXISTS symbol_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_year        INTEGER NOT NULL,
    symbol          TEXT    NOT NULL COLLATE NOCASE,
    last_sale_date  TEXT,
    last_sale_price REAL,
    total_trades    INTEGER NOT NULL DEFAULT 0,
    winning_trades  INTEGER NOT NULL DEFAULT 0,
    losing_trades   INTEGER NOT NULL DEFAULT 0,
    total_quantity  REAL    NOT NULL DEFAULT 0,
    total_proceeds  REAL    NOT NULL DEFAULT 0,
    total_cost      REAL    NOT NULL DEFAULT 0,
    net_pnl         REAL    NOT NULL DEFAULT 0,
    total_profit    REAL    NOT NULL DEFAULT 0,
    total_loss      REAL    NOT NULL DEFAULT 0,
    eksik_lot_count INTEGER NOT NULL DEFAULT 0,
    portfolio       TEXT    NOT NULL DEFAULT '',
    computed_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tax_year, symbol, portfolio)
);
CREATE INDEX IF NOT EXISTS ix_sym_year       ON symbol_summary(tax_year);
CREATE INDEX IF NOT EXISTS ix_sym_portfolio  ON symbol_summary(portfolio);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT    NOT NULL,
    file_type     TEXT    NOT NULL CHECK(file_type IN ('PDF','CSV','MANUAL')),
    rows_found    INTEGER,
    rows_inserted INTEGER,
    rows_skipped  INTEGER,
    status        TEXT    NOT NULL CHECK(status IN ('success','partial','error')),
    error_message TEXT,
    ingested_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_portfolio_name ON portfolios(name);

CREATE TABLE IF NOT EXISTS watchlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio  TEXT    NOT NULL COLLATE NOCASE,
    symbol     TEXT    NOT NULL COLLATE NOCASE,
    notes      TEXT,
    added_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(portfolio, symbol)
);
CREATE INDEX IF NOT EXISTS ix_watchlist_portfolio ON watchlist(portfolio);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_add_portfolio_columns() -> None:
    """
    Idempotent migration: add portfolio column to computed tables and
    update symbol_summary UNIQUE constraint.  Since SQLite cannot ALTER
    UNIQUE constraints, computed tables are dropped and recreated (they
    are fully recomputed by recompute_fifo anyway).
    """
    with db() as conn:
        # Check whether portfolio column already exists in fifo_results
        cols = {row[1] for row in conn.execute("PRAGMA table_info(fifo_results)")}
        if "portfolio" in cols:
            return  # migration already applied

        # Computed tables have no permanent data — drop and recreate
        conn.executescript("""
            DROP TABLE IF EXISTS fifo_lot_matches;
            DROP TABLE IF EXISTS fifo_results;
            DROP TABLE IF EXISTS open_positions;
            DROP TABLE IF EXISTS symbol_summary;
        """)

        # Recreate with updated schema (mirrors SCHEMA_SQL definitions)
        conn.executescript("""
CREATE TABLE fifo_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
    tx_date       TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    quantity      REAL    NOT NULL,
    sale_price    REAL    NOT NULL,
    sale_proceeds REAL    NOT NULL,
    cost_basis    REAL    NOT NULL,
    pnl           REAL    GENERATED ALWAYS AS (sale_proceeds - cost_basis) STORED,
    pnl_pct       REAL    GENERATED ALWAYS AS (
                      CASE WHEN cost_basis > 0.001
                           THEN (sale_proceeds - cost_basis) / cost_basis
                           ELSE NULL END) STORED,
    status        TEXT    GENERATED ALWAYS AS (
                      CASE WHEN (sale_proceeds - cost_basis) >= 0
                           THEN 'KÂR' ELSE 'ZARAR' END) STORED,
    eksik_lot     INTEGER NOT NULL DEFAULT 0,
    tax_year      INTEGER NOT NULL,
    portfolio     TEXT    NOT NULL DEFAULT '',
    computed_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_fifo_symbol    ON fifo_results(symbol);
CREATE INDEX ix_fifo_date      ON fifo_results(tx_date);
CREATE INDEX ix_fifo_year      ON fifo_results(tax_year);
CREATE INDEX ix_fifo_year_date ON fifo_results(tax_year, tx_date);
CREATE INDEX ix_fifo_portfolio ON fifo_results(portfolio);

CREATE TABLE fifo_lot_matches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fifo_result_id INTEGER NOT NULL REFERENCES fifo_results(id),
    sell_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
    buy_tx_id      INTEGER REFERENCES raw_transactions(id),
    buy_date       TEXT,
    buy_price      REAL,
    consumed_qty   REAL    NOT NULL,
    consumed_cost  REAL    NOT NULL,
    is_carry_lot   INTEGER NOT NULL DEFAULT 0,
    computed_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_lot_match_result ON fifo_lot_matches(fifo_result_id);
CREATE INDEX ix_lot_match_sell   ON fifo_lot_matches(sell_tx_id);

CREATE TABLE open_positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT    NOT NULL COLLATE NOCASE,
    lot_seq      INTEGER NOT NULL,
    buy_date     TEXT    NOT NULL,
    quantity     REAL    NOT NULL,
    buy_price    REAL    NOT NULL,
    cost_basis   REAL    NOT NULL,
    is_carry_lot INTEGER NOT NULL DEFAULT 0,
    source_year  INTEGER,
    portfolio    TEXT    NOT NULL DEFAULT '',
    computed_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_pos_symbol    ON open_positions(symbol);
CREATE INDEX ix_pos_portfolio ON open_positions(portfolio);

CREATE TABLE symbol_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_year        INTEGER NOT NULL,
    symbol          TEXT    NOT NULL COLLATE NOCASE,
    last_sale_date  TEXT,
    last_sale_price REAL,
    total_trades    INTEGER NOT NULL DEFAULT 0,
    winning_trades  INTEGER NOT NULL DEFAULT 0,
    losing_trades   INTEGER NOT NULL DEFAULT 0,
    total_quantity  REAL    NOT NULL DEFAULT 0,
    total_proceeds  REAL    NOT NULL DEFAULT 0,
    total_cost      REAL    NOT NULL DEFAULT 0,
    net_pnl         REAL    NOT NULL DEFAULT 0,
    total_profit    REAL    NOT NULL DEFAULT 0,
    total_loss      REAL    NOT NULL DEFAULT 0,
    eksik_lot_count INTEGER NOT NULL DEFAULT 0,
    portfolio       TEXT    NOT NULL DEFAULT '',
    computed_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tax_year, symbol, portfolio)
);
CREATE INDEX ix_sym_year      ON symbol_summary(tax_year);
CREATE INDEX ix_sym_portfolio ON symbol_summary(portfolio);
        """)


def migrate_add_watchlist() -> None:
    """Idempotent: watchlist tablosu yoksa oluşturur."""
    with db() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "watchlist" not in tables:
            conn.executescript("""
                CREATE TABLE watchlist (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio  TEXT    NOT NULL COLLATE NOCASE,
                    symbol     TEXT    NOT NULL COLLATE NOCASE,
                    notes      TEXT,
                    added_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(portfolio, symbol)
                );
                CREATE INDEX IF NOT EXISTS ix_watchlist_portfolio ON watchlist(portfolio);
            """)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _normalized_create_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    sql = row["sql"] if row and row["sql"] else ""
    return "".join(sql.lower().split())


def ensure_multitenant_schema(default_user_id: int) -> bool:
    """
    Make schema multi-tenant with user_id columns and user-scoped uniqueness.
    Returns True if schema/data shape changed.
    """
    changed = False

    with db() as conn:
        # 1) Add user_id where needed (raw + auxiliary tables)
        for table in ("raw_transactions", "carry_forward_lots", "ingestion_log"):
            if "user_id" not in _table_columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
                changed = True

        # 2) Rebuild portfolios for UNIQUE(user_id, name)
        portfolios_sql = _normalized_create_sql(conn, "portfolios")
        if "unique(user_id,name)" not in portfolios_sql:
            has_user_col = "user_id" in _table_columns(conn, "portfolios")
            conn.execute("ALTER TABLE portfolios RENAME TO portfolios_legacy")
            conn.executescript(
                """
                CREATE TABLE portfolios (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    name        TEXT    NOT NULL COLLATE NOCASE,
                    description TEXT,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, name)
                );
                CREATE INDEX IF NOT EXISTS ix_portfolio_name ON portfolios(name);
                CREATE INDEX IF NOT EXISTS ix_portfolio_user ON portfolios(user_id);
                """
            )
            if has_user_col:
                conn.execute(
                    """
                    INSERT INTO portfolios (id, user_id, name, description, is_active, created_at, updated_at)
                    SELECT id, COALESCE(user_id, ?), name, description, is_active, created_at, updated_at
                    FROM portfolios_legacy
                    """,
                    (default_user_id,),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO portfolios (id, user_id, name, description, is_active, created_at, updated_at)
                    SELECT id, ?, name, description, is_active, created_at, updated_at
                    FROM portfolios_legacy
                    """,
                    (default_user_id,),
                )
            conn.execute("DROP TABLE portfolios_legacy")
            changed = True

        # 3) Rebuild watchlist for UNIQUE(user_id, portfolio, symbol)
        watchlist_sql = _normalized_create_sql(conn, "watchlist")
        if "unique(user_id,portfolio,symbol)" not in watchlist_sql:
            has_user_col = "user_id" in _table_columns(conn, "watchlist")
            conn.execute("ALTER TABLE watchlist RENAME TO watchlist_legacy")
            conn.executescript(
                """
                CREATE TABLE watchlist (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    portfolio  TEXT    NOT NULL COLLATE NOCASE,
                    symbol     TEXT    NOT NULL COLLATE NOCASE,
                    notes      TEXT,
                    added_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, portfolio, symbol)
                );
                CREATE INDEX IF NOT EXISTS ix_watchlist_portfolio ON watchlist(portfolio);
                CREATE INDEX IF NOT EXISTS ix_watchlist_user ON watchlist(user_id);
                """
            )
            if has_user_col:
                conn.execute(
                    """
                    INSERT INTO watchlist (id, user_id, portfolio, symbol, notes, added_at)
                    SELECT id, COALESCE(user_id, ?), portfolio, symbol, notes, added_at
                    FROM watchlist_legacy
                    """,
                    (default_user_id,),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO watchlist (id, user_id, portfolio, symbol, notes, added_at)
                    SELECT id, ?, portfolio, symbol, notes, added_at
                    FROM watchlist_legacy
                    """,
                    (default_user_id,),
                )
            conn.execute("DROP TABLE watchlist_legacy")
            changed = True

        # 4) Add user_id to computed tables, rebuild if unique constraints are legacy
        need_rebuild_computed = False
        for table in ("fifo_results", "open_positions", "symbol_summary"):
            if "user_id" not in _table_columns(conn, table):
                need_rebuild_computed = True
        symbol_summary_sql = _normalized_create_sql(conn, "symbol_summary")
        if "unique(tax_year,symbol,portfolio,user_id)" not in symbol_summary_sql:
            need_rebuild_computed = True

        if need_rebuild_computed:
            conn.executescript(
                """
                DROP TABLE IF EXISTS fifo_lot_matches;
                DROP TABLE IF EXISTS fifo_results;
                DROP TABLE IF EXISTS open_positions;
                DROP TABLE IF EXISTS symbol_summary;

                CREATE TABLE fifo_results (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
                    tx_date       TEXT    NOT NULL,
                    symbol        TEXT    NOT NULL,
                    quantity      REAL    NOT NULL,
                    sale_price    REAL    NOT NULL,
                    sale_proceeds REAL    NOT NULL,
                    cost_basis    REAL    NOT NULL,
                    pnl           REAL    GENERATED ALWAYS AS (sale_proceeds - cost_basis) STORED,
                    pnl_pct       REAL    GENERATED ALWAYS AS (
                                      CASE WHEN cost_basis > 0.001
                                           THEN (sale_proceeds - cost_basis) / cost_basis
                                           ELSE NULL END) STORED,
                    status        TEXT    GENERATED ALWAYS AS (
                                      CASE WHEN (sale_proceeds - cost_basis) >= 0
                                           THEN 'KÂR' ELSE 'ZARAR' END) STORED,
                    eksik_lot     INTEGER NOT NULL DEFAULT 0,
                    tax_year      INTEGER NOT NULL,
                    portfolio     TEXT    NOT NULL DEFAULT '',
                    user_id       INTEGER NOT NULL,
                    computed_at   TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX ix_fifo_symbol        ON fifo_results(symbol);
                CREATE INDEX ix_fifo_date          ON fifo_results(tx_date);
                CREATE INDEX ix_fifo_year          ON fifo_results(tax_year);
                CREATE INDEX ix_fifo_year_date     ON fifo_results(tax_year, tx_date);
                CREATE INDEX ix_fifo_portfolio     ON fifo_results(portfolio);
                CREATE INDEX ix_fifo_user          ON fifo_results(user_id);
                CREATE INDEX ix_fifo_user_portfolio ON fifo_results(user_id, portfolio);

                CREATE TABLE fifo_lot_matches (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    fifo_result_id INTEGER NOT NULL REFERENCES fifo_results(id),
                    sell_tx_id     INTEGER NOT NULL REFERENCES raw_transactions(id),
                    buy_tx_id      INTEGER REFERENCES raw_transactions(id),
                    buy_date       TEXT,
                    buy_price      REAL,
                    consumed_qty   REAL    NOT NULL,
                    consumed_cost  REAL    NOT NULL,
                    is_carry_lot   INTEGER NOT NULL DEFAULT 0,
                    computed_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX ix_lot_match_result ON fifo_lot_matches(fifo_result_id);
                CREATE INDEX ix_lot_match_sell   ON fifo_lot_matches(sell_tx_id);

                CREATE TABLE open_positions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT    NOT NULL COLLATE NOCASE,
                    lot_seq      INTEGER NOT NULL,
                    buy_date     TEXT    NOT NULL,
                    quantity     REAL    NOT NULL,
                    buy_price    REAL    NOT NULL,
                    cost_basis   REAL    NOT NULL,
                    is_carry_lot INTEGER NOT NULL DEFAULT 0,
                    source_year  INTEGER,
                    portfolio    TEXT    NOT NULL DEFAULT '',
                    user_id      INTEGER NOT NULL,
                    computed_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX ix_pos_symbol         ON open_positions(symbol);
                CREATE INDEX ix_pos_portfolio      ON open_positions(portfolio);
                CREATE INDEX ix_pos_user           ON open_positions(user_id);
                CREATE INDEX ix_pos_user_portfolio ON open_positions(user_id, portfolio);

                CREATE TABLE symbol_summary (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tax_year        INTEGER NOT NULL,
                    symbol          TEXT    NOT NULL COLLATE NOCASE,
                    last_sale_date  TEXT,
                    last_sale_price REAL,
                    total_trades    INTEGER NOT NULL DEFAULT 0,
                    winning_trades  INTEGER NOT NULL DEFAULT 0,
                    losing_trades   INTEGER NOT NULL DEFAULT 0,
                    total_quantity  REAL    NOT NULL DEFAULT 0,
                    total_proceeds  REAL    NOT NULL DEFAULT 0,
                    total_cost      REAL    NOT NULL DEFAULT 0,
                    net_pnl         REAL    NOT NULL DEFAULT 0,
                    total_profit    REAL    NOT NULL DEFAULT 0,
                    total_loss      REAL    NOT NULL DEFAULT 0,
                    eksik_lot_count INTEGER NOT NULL DEFAULT 0,
                    portfolio       TEXT    NOT NULL DEFAULT '',
                    user_id         INTEGER NOT NULL,
                    computed_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(tax_year, symbol, portfolio, user_id)
                );
                CREATE INDEX ix_sym_year            ON symbol_summary(tax_year);
                CREATE INDEX ix_sym_portfolio       ON symbol_summary(portfolio);
                CREATE INDEX ix_sym_user            ON symbol_summary(user_id);
                CREATE INDEX ix_sym_user_portfolio  ON symbol_summary(user_id, portfolio);
                """
            )
            changed = True

        # 5) User-scoped dedup for raw transactions
        conn.execute("DROP INDEX IF EXISTS ux_raw_dedup")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_dedup_user ON raw_transactions(user_id, dedup_key)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_raw_user ON raw_transactions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_raw_user_portfolio ON raw_transactions(user_id, portfolio)")

        # 6) Backfill user_id NULL/0 with default admin user
        for table in (
            "raw_transactions",
            "carry_forward_lots",
            "ingestion_log",
            "portfolios",
            "watchlist",
        ):
            if "user_id" in _table_columns(conn, table):
                conn.execute(
                    f"UPDATE {table} SET user_id=? WHERE user_id IS NULL OR user_id=0",
                    (default_user_id,),
                )

    return changed


def migrate_add_symbol_targets() -> None:
    """Idempotent: symbol_targets tablosu yoksa oluşturur + stop_fiyat sütunu ekler."""
    with db() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "symbol_targets" not in tables:
            conn.executescript("""
                CREATE TABLE symbol_targets (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id             INTEGER NOT NULL,
                    portfolio           TEXT    NOT NULL COLLATE NOCASE,
                    symbol              TEXT    NOT NULL COLLATE NOCASE,
                    hedef_fiyat         REAL,
                    taban_fiyat         REAL,
                    hedef_dolar_kazanci REAL,
                    stop_fiyat          REAL,
                    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, portfolio, symbol)
                );
                CREATE INDEX IF NOT EXISTS ix_targets_portfolio ON symbol_targets(user_id, portfolio);
            """)
        else:
            # stop_fiyat sütunu yoksa ekle
            cols = {r[1] for r in conn.execute("PRAGMA table_info(symbol_targets)").fetchall()}
            if "stop_fiyat" not in cols:
                conn.execute("ALTER TABLE symbol_targets ADD COLUMN stop_fiyat REAL")


def upsert_symbol_target(user_id: int, portfolio: str, symbol: str,
                         hedef_fiyat=None, taban_fiyat=None,
                         hedef_dolar_kazanci=None, stop_fiyat=None) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO symbol_targets
                   (user_id, portfolio, symbol, hedef_fiyat, taban_fiyat, hedef_dolar_kazanci, stop_fiyat, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, portfolio, symbol) DO UPDATE SET
                   hedef_fiyat = excluded.hedef_fiyat,
                   taban_fiyat = excluded.taban_fiyat,
                   hedef_dolar_kazanci = excluded.hedef_dolar_kazanci,
                   stop_fiyat = excluded.stop_fiyat,
                   updated_at = datetime('now')""",
            (user_id, portfolio, symbol.upper(), hedef_fiyat, taban_fiyat, hedef_dolar_kazanci, stop_fiyat),
        )


def get_symbol_targets(user_id: int, portfolio: str) -> dict:
    """Returns {SYMBOL: {hedef_fiyat, taban_fiyat, hedef_dolar_kazanci}, ...}"""
    with db() as conn:
        rows = conn.execute(
            "SELECT symbol, hedef_fiyat, taban_fiyat, hedef_dolar_kazanci "
            "FROM symbol_targets WHERE user_id = ? AND portfolio = ?",
            (user_id, portfolio),
        ).fetchall()
    return {
        r["symbol"].upper(): {
            "hedef_fiyat": r["hedef_fiyat"],
            "taban_fiyat": r["taban_fiyat"],
            "hedef_dolar_kazanci": r["hedef_dolar_kazanci"],
        }
        for r in rows
    }


def get_symbol_target(user_id: int, portfolio: str, symbol: str):
    with db() as conn:
        row = conn.execute(
            "SELECT hedef_fiyat, taban_fiyat, hedef_dolar_kazanci "
            "FROM symbol_targets WHERE user_id = ? AND portfolio = ? AND symbol = ?",
            (user_id, portfolio, symbol.upper()),
        ).fetchone()
    if not row:
        return None
    return {
        "hedef_fiyat": row["hedef_fiyat"],
        "taban_fiyat": row["taban_fiyat"],
        "hedef_dolar_kazanci": row["hedef_dolar_kazanci"],
    }


def delete_symbol_target(user_id: int, portfolio: str, symbol: str) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM symbol_targets WHERE user_id = ? AND portfolio = ? AND symbol = ?",
            (user_id, portfolio, symbol.upper()),
        )


def init_db() -> None:
    ensure_db_path_ready()
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
    migrate_add_portfolio_columns()
    migrate_add_watchlist()
    migrate_add_symbol_targets()


def recompute_fifo() -> dict:
    """
    Full FIFO recompute, isolated per user + portfolio:
    1. Get all distinct (user_id, portfolio) tuples from raw_transactions.
    2. For each tuple, load only its transactions and run FIFO independently.
    3. Truncate + re-insert fifo_results, fifo_lot_matches, open_positions, symbol_summary
       with user_id + portfolio populated.
    Carry-forward lots are isolated by user_id.
    Returns aggregate summary stats.
    """
    from collections import defaultdict

    with db() as conn:
        # Get all distinct user + portfolio pairs
        portfolio_rows = conn.execute(
            """
            SELECT DISTINCT user_id, portfolio
            FROM raw_transactions
            ORDER BY user_id, portfolio
            """
        ).fetchall()
        portfolio_pairs = [(r["user_id"], r["portfolio"]) for r in portfolio_rows]

        # Truncate computed tables
        conn.execute("DELETE FROM fifo_lot_matches")
        conn.execute("DELETE FROM fifo_results")
        conn.execute("DELETE FROM open_positions")
        conn.execute("DELETE FROM symbol_summary")

        total_sells = 0
        total_open = 0
        total_symbols = 0

        for user_id, portfolio in portfolio_pairs:
            # Load carry lots for this user
            carry_rows = conn.execute(
                """
                SELECT symbol, lot_date, quantity, price, cost
                FROM carry_forward_lots
                WHERE user_id = ?
                ORDER BY carry_into_year, lot_date, id
                """,
                (user_id,),
            ).fetchall()
            carry_lots = [
                CarryLot(
                    symbol=r["symbol"],
                    lot_date=r["lot_date"],
                    quantity=r["quantity"],
                    price=r["price"],
                    cost=r["cost"],
                )
                for r in carry_rows
            ]

            # Load transactions for THIS user + portfolio only
            rows = conn.execute(
                "SELECT id, tx_date, symbol, direction, quantity, price, total "
                "FROM raw_transactions "
                "WHERE user_id = ? AND portfolio = ? "
                "ORDER BY tx_date, CASE WHEN direction='Alış' THEN 0 ELSE 1 END, id",
                (user_id, portfolio),
            ).fetchall()
            transactions = [
                RawTx(
                    tx_id=r["id"],
                    tx_date=r["tx_date"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    quantity=r["quantity"],
                    price=r["price"],
                    total=r["total"],
                )
                for r in rows
            ]

            if not transactions:
                continue

            # Run FIFO engine for this user + portfolio in isolation
            sell_results, open_lots = run_fifo(transactions, carry_lots)

            # Insert fifo_results with portfolio
            fifo_id_map: dict[int, int] = {}
            for sr in sell_results:
                year = int(sr.tx_date[:4])
                cur = conn.execute(
                    """INSERT INTO fifo_results
                       (raw_tx_id, tx_date, symbol, quantity, sale_price,
                        sale_proceeds, cost_basis, eksik_lot, tax_year, portfolio, user_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (sr.raw_tx_id, sr.tx_date, sr.symbol, sr.quantity,
                     sr.sale_price, sr.sale_proceeds, sr.cost_basis,
                     1 if sr.eksik_lot else 0, year, portfolio, user_id),
                )
                fifo_id = cur.lastrowid
                fifo_id_map[sr.raw_tx_id] = fifo_id

                for m in sr.lot_matches:
                    conn.execute(
                        """INSERT INTO fifo_lot_matches
                           (fifo_result_id, sell_tx_id, buy_tx_id, buy_date,
                            buy_price, consumed_qty, consumed_cost, is_carry_lot)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (fifo_id, sr.raw_tx_id, m.buy_tx_id, m.buy_date,
                         m.buy_price, m.consumed_qty, m.consumed_cost,
                         1 if m.is_carry_lot else 0),
                    )

            # Insert open positions with portfolio
            for ol in open_lots:
                year = None
                if ol.source_tx_id:
                    tx = next((t for t in transactions if t.tx_id == ol.source_tx_id), None)
                    if tx:
                        year = int(tx.tx_date[:4])
                conn.execute(
                    """INSERT INTO open_positions
                       (symbol, lot_seq, buy_date, quantity, buy_price,
                        cost_basis, is_carry_lot, source_year, portfolio, user_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (ol.symbol, ol.lot_seq, ol.buy_date, ol.quantity,
                     ol.buy_price, ol.cost_basis, 1 if ol.is_carry_lot else 0,
                     year, portfolio, user_id),
                )

            # Build symbol_summary for this portfolio
            summaries: dict[tuple, dict] = defaultdict(lambda: {
                "last_sale_date": None, "last_sale_price": None,
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "total_quantity": 0.0, "total_proceeds": 0.0, "total_cost": 0.0,
                "net_pnl": 0.0, "total_profit": 0.0, "total_loss": 0.0,
                "eksik_lot_count": 0,
            })

            for sr in sell_results:
                year = int(sr.tx_date[:4])
                key = (year, sr.symbol)
                s = summaries[key]
                pnl = sr.sale_proceeds - sr.cost_basis
                s["total_trades"] += 1
                s["total_quantity"] += sr.quantity
                s["total_proceeds"] += sr.sale_proceeds
                s["total_cost"] += sr.cost_basis
                s["net_pnl"] += pnl
                if pnl >= 0:
                    s["winning_trades"] += 1
                    s["total_profit"] += pnl
                else:
                    s["losing_trades"] += 1
                    s["total_loss"] += pnl
                if sr.eksik_lot:
                    s["eksik_lot_count"] += 1
                if s["last_sale_date"] is None or sr.tx_date > s["last_sale_date"]:
                    s["last_sale_date"] = sr.tx_date
                    s["last_sale_price"] = sr.sale_price

            for (year, sym), s in summaries.items():
                conn.execute(
                    """INSERT INTO symbol_summary
                       (tax_year, symbol, last_sale_date, last_sale_price,
                        total_trades, winning_trades, losing_trades,
                        total_quantity, total_proceeds, total_cost,
                        net_pnl, total_profit, total_loss, eksik_lot_count, portfolio, user_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (year, sym, s["last_sale_date"], s["last_sale_price"],
                     s["total_trades"], s["winning_trades"], s["losing_trades"],
                     s["total_quantity"], s["total_proceeds"], s["total_cost"],
                     s["net_pnl"], s["total_profit"], s["total_loss"],
                     s["eksik_lot_count"], portfolio, user_id),
                )

            total_sells += len(sell_results)
            total_open += len(open_lots)
            total_symbols += len(summaries)

        return {
            "sell_results": total_sells,
            "open_lots": total_open,
            "symbols": total_symbols,
        }
