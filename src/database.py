"""
SQLite database management module for Crypto-Pilot metrics persistence.

Provides the Database class wrapping a local SQLite file with three tables:
  - predictions  -- per-prediction records with backfill support
  - benchmarks   -- aggregated benchmark results
  - test_runs    -- automated test run history

Database file default: data/metrics.db (auto-created alongside its directory).
"""

import sqlite3
from pathlib import Path

# ──────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    predicted_at    TEXT    NOT NULL,
    target_at       TEXT    NOT NULL,
    current_price   REAL    NOT NULL,
    predicted_price REAL    NOT NULL,
    expected_return REAL    NOT NULL,
    signal          TEXT    NOT NULL,
    actual_price    REAL,
    actual_return   REAL,
    direction_correct INTEGER,
    cold_start_ms   INTEGER,
    inference_ms    INTEGER,
    data_fetch_ms   INTEGER
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at            TEXT    NOT NULL,
    symbol            TEXT    NOT NULL,
    sample_count      INTEGER,
    direction_accuracy REAL,
    avg_return        REAL,
    win_rate          REAL,
    mae               REAL,
    avg_inference_ms  INTEGER,
    report_path       TEXT
);

CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT    NOT NULL,
    unit_passed INTEGER NOT NULL,
    unit_total  INTEGER NOT NULL,
    e2e_passed  INTEGER NOT NULL,
    e2e_total   INTEGER NOT NULL,
    success     INTEGER NOT NULL
);
"""

# ──────────────────────────────────────────────────────────
# Default database path
# ──────────────────────────────────────────────────────────

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "metrics.db"


# ──────────────────────────────────────────────────────────
# Database class
# ──────────────────────────────────────────────────────────

class Database:
    """SQLite-backed metrics database with WAL journal mode for concurrent access."""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize the database, auto-creating the directory and tables.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to data/metrics.db relative to the project root.
        """
        if db_path is None:
            self.db_path = _DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)

        # Ensure the parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create tables on first connection
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ── Connection helper ─────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Return a new connection with WAL mode and Row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ══════════════════════════════════════════════════════════
    # Predictions
    # ══════════════════════════════════════════════════════════

    def insert_prediction(
        self,
        symbol: str,
        predicted_at: str,
        target_at: str,
        current_price: float,
        predicted_price: float,
        expected_return: float,
        signal: str,
        cold_start_ms: int,
        inference_ms: int,
        data_fetch_ms: int,
    ) -> int:
        """Insert a new prediction row and return its id."""
        sql = """
            INSERT INTO predictions
                (symbol, predicted_at, target_at, current_price,
                 predicted_price, expected_return, signal,
                 cold_start_ms, inference_ms, data_fetch_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (
                    symbol,
                    predicted_at,
                    target_at,
                    current_price,
                    predicted_price,
                    expected_return,
                    signal,
                    cold_start_ms,
                    inference_ms,
                    data_fetch_ms,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # ── Backfill ──────────────────────────────────────────────

    def backfill_prediction(self, pred_id: int, actual_price: float):
        """
        Update a prediction with the realized price.

        Sets actual_price, computed actual_return, and direction_correct.
        direction_correct = 1 when the sign of (predicted_price - current_price)
        matches the sign of (actual_price - current_price), otherwise 0.
        """
        with self._connect() as conn:
            # Fetch the original row so we can compute derived fields
            row = conn.execute(
                "SELECT current_price, predicted_price FROM predictions WHERE id = ?",
                (pred_id,),
            ).fetchone()

            if row is None:
                raise ValueError(f"No prediction found with id={pred_id}")

            current_price = row["current_price"]
            predicted_price = row["predicted_price"]

            actual_return = (
                (actual_price - current_price) / current_price
                if current_price != 0
                else 0.0
            )

            pred_delta = predicted_price - current_price
            actual_delta = actual_price - current_price

            # direction_correct = 1 if both deltas have the same sign
            # (both positive or both negative); 0 otherwise (or 0 for zero delta).
            if pred_delta > 0 and actual_delta > 0:
                direction_correct = 1
            elif pred_delta < 0 and actual_delta < 0:
                direction_correct = 1
            else:
                direction_correct = 0

            conn.execute(
                """UPDATE predictions
                   SET actual_price = ?,
                       actual_return = ?,
                       direction_correct = ?
                   WHERE id = ?""",
                (actual_price, actual_return, direction_correct, pred_id),
            )
            conn.commit()

    # ── Queries ───────────────────────────────────────────────

    def get_pending_backfills(self, symbol: str | None = None) -> list[dict]:
        """
        Return predictions whose actual_price is still NULL and whose
        target_at timestamp is <= now (i.e. the prediction window has closed).
        """
        if symbol is not None:
            sql = """
                SELECT * FROM predictions
                WHERE actual_price IS NULL
                  AND target_at <= datetime('now')
                  AND symbol = ?
                ORDER BY target_at ASC
            """
            params = (symbol,)
        else:
            sql = """
                SELECT * FROM predictions
                WHERE actual_price IS NULL
                  AND target_at <= datetime('now')
                ORDER BY target_at ASC
            """
            params = ()

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_direction_accuracy(
        self, symbol: str | None = None, days: int = 30
    ) -> dict:
        """
        Return {sample_count, correct_count, accuracy_pct} for backfilled
        predictions within the given number of days.

        accuracy_pct is rounded to 1 decimal place, or None if sample_count == 0.
        """
        date_filter = f"datetime('now', '-{days} days')"

        if symbol is not None:
            sql = """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(direction_correct), 0) AS correct
                FROM predictions
                WHERE direction_correct IS NOT NULL
                  AND predicted_at >= ?
                  AND symbol = ?
            """
            params = (date_filter, symbol)
        else:
            sql = """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(direction_correct), 0) AS correct
                FROM predictions
                WHERE direction_correct IS NOT NULL
                  AND predicted_at >= ?
            """
            params = (date_filter,)

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            total = int(row["total"])
            correct = int(row["correct"])
            accuracy_pct = (
                round(correct / total * 100, 1) if total > 0 else None
            )
            return {
                "sample_count": total,
                "correct_count": correct,
                "accuracy_pct": accuracy_pct,
            }

    def get_win_rate(
        self, symbol: str | None = None, days: int = 30
    ) -> dict:
        """
        Return {sample_count, win_count, win_rate_pct}.

        A win is defined as:
          - signal = 'Bullish' AND actual_return > 0
          - signal = 'Bearish'  AND actual_return < 0

        Only records with signal != 'Neutral' and actual_return IS NOT NULL
        are counted.
        """
        date_filter = f"datetime('now', '-{days} days')"

        base_where = """
            WHERE signal != 'Neutral'
              AND actual_return IS NOT NULL
              AND predicted_at >= ?
        """

        if symbol is not None:
            base_where += " AND symbol = ?"
            params_total = (date_filter, symbol)
            params_win = (date_filter, symbol)
        else:
            params_total = (date_filter,)
            params_win = (date_filter,)

        with self._connect() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS total FROM predictions {base_where}",
                params_total,
            ).fetchone()
            total = int(total_row["total"])

            win_row = conn.execute(
                f"""SELECT COUNT(*) AS wins FROM predictions {base_where}
                    AND (
                        (signal = 'Bullish' AND actual_return > 0)
                        OR
                        (signal = 'Bearish' AND actual_return < 0)
                    )""",
                params_win,
            ).fetchone()
            wins = int(win_row["wins"])

            win_rate_pct = (
                round(wins / total * 100, 1) if total > 0 else None
            )
            return {
                "sample_count": total,
                "win_count": wins,
                "win_rate_pct": win_rate_pct,
            }

    def get_avg_timing(self, days: int = 30) -> dict:
        """
        Return {cold_start_ms, inference_ms, data_fetch_ms, sample_count}.

        cold_start_ms is the AVG of cold_start_ms WHERE cold_start_ms > 0
        (excludes cached/warm-start runs).
        """
        date_filter = f"datetime('now', '-{days} days')"

        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) AS sample_count,
                       AVG(cold_start_ms) FILTER (WHERE cold_start_ms > 0)
                           AS cold_start_ms,
                       AVG(inference_ms) AS inference_ms,
                       AVG(data_fetch_ms) AS data_fetch_ms
                   FROM predictions
                   WHERE predicted_at >= ?""",
                (date_filter,),
            ).fetchone()

            return {
                "sample_count": int(row["sample_count"]) if row["sample_count"] is not None else 0,
                "cold_start_ms": round(row["cold_start_ms"], 1) if row["cold_start_ms"] is not None else None,
                "inference_ms": round(row["inference_ms"], 1) if row["inference_ms"] is not None else None,
                "data_fetch_ms": round(row["data_fetch_ms"], 1) if row["data_fetch_ms"] is not None else None,
            }

    def get_prediction_stats(self) -> dict:
        """Return {total, backfilled, pending} counts across all predictions."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM predictions"
            ).fetchone()["n"]

            backfilled = conn.execute(
                "SELECT COUNT(*) AS n FROM predictions WHERE actual_price IS NOT NULL"
            ).fetchone()["n"]

            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM predictions WHERE actual_price IS NULL"
            ).fetchone()["n"]

            return {
                "total": int(total) if total is not None else 0,
                "backfilled": int(backfilled) if backfilled is not None else 0,
                "pending": int(pending) if pending is not None else 0,
            }

    # ══════════════════════════════════════════════════════════
    # Benchmarks
    # ══════════════════════════════════════════════════════════

    def insert_benchmark(
        self,
        run_at: str,
        symbol: str,
        sample_count: int | None,
        direction_accuracy: float | None,
        avg_return: float | None,
        win_rate: float | None,
        mae: float | None,
        avg_inference_ms: int | None,
        report_path: str | None,
    ) -> int:
        """Insert a new benchmark row and return its id."""
        sql = """
            INSERT INTO benchmarks
                (run_at, symbol, sample_count, direction_accuracy,
                 avg_return, win_rate, mae, avg_inference_ms, report_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (
                    run_at,
                    symbol,
                    sample_count,
                    direction_accuracy,
                    avg_return,
                    win_rate,
                    mae,
                    avg_inference_ms,
                    report_path,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_latest_benchmark(self, symbol: str | None = None) -> list[dict]:
        """
        Return the latest benchmark(s).

        - If *symbol* is provided: all benchmarks for that symbol,
          ordered by run_at DESC.
        - If *symbol* is None: only the single most recent benchmark
          for **each** symbol (i.e. the max run_at per symbol).
        """
        with self._connect() as conn:
            if symbol is not None:
                rows = conn.execute(
                    """SELECT * FROM benchmarks
                       WHERE symbol = ?
                       ORDER BY run_at DESC""",
                    (symbol,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM benchmarks
                       WHERE (symbol, run_at) IN (
                           SELECT symbol, MAX(run_at)
                           FROM benchmarks
                           GROUP BY symbol
                       )
                       ORDER BY symbol ASC"""
                ).fetchall()

            return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════
    # Test runs
    # ══════════════════════════════════════════════════════════

    def insert_test_run(
        self,
        run_at: str,
        unit_passed: int,
        unit_total: int,
        e2e_passed: int,
        e2e_total: int,
        success: int,
    ) -> int:
        """Insert a new test_run row and return its id."""
        sql = """
            INSERT INTO test_runs
                (run_at, unit_passed, unit_total, e2e_passed, e2e_total, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cursor = conn.execute(
                sql,
                (run_at, unit_passed, unit_total, e2e_passed, e2e_total, success),
            )
            conn.commit()
            return cursor.lastrowid

    def get_latest_test_run(self) -> dict | None:
        """Return the most recent test run, or None if the table is empty."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM test_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

            if row is None:
                return None
            return dict(row)
