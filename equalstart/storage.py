import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from equalstart.catalog import ROOT


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getenv("EQUALSTART_DB_PATH") or ROOT / "runtime" / "equalstart.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS saved (id TEXT PRIMARY KEY, tasks TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, reserved REAL NOT NULL, actual REAL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, events TEXT NOT NULL);
            """)
            if "plan" not in {row[1] for row in con.execute("PRAGMA table_info(saved)")}:
                con.execute("ALTER TABLE saved ADD COLUMN plan TEXT")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        try:
            with con:
                yield con
        finally:
            con.close()

    def save(self, opportunity_id: str):
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO saved(id) VALUES (?)", (opportunity_id,))

    def saved(self) -> dict[str, list[str]]:
        with self.connect() as con:
            return {row[0]: json.loads(row[1]) for row in con.execute("SELECT id,tasks FROM saved")}

    def tasks(self, opportunity_id: str, completed: list[str]):
        with self.connect() as con:
            con.execute("UPDATE saved SET tasks=? WHERE id=?", (json.dumps(completed), opportunity_id))

    def remove(self, opportunity_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM saved WHERE id=?", (opportunity_id,))

    def save_plan(self, opportunity_id: str, tasks: list[dict]):
        self.save(opportunity_id)
        with self.connect() as con:
            con.execute("UPDATE saved SET plan=? WHERE id=?", (json.dumps(tasks), opportunity_id))

    def plan(self, opportunity_id: str) -> list[dict] | None:
        with self.connect() as con:
            row = con.execute("SELECT plan FROM saved WHERE id=?", (opportunity_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None

    def log_run(self, run_id: str, events: list[dict]):
        # Store stage metadata only: never profile inputs, credentials, or model payloads.
        safe = [{k: event[k] for k in ("stage", "mode", "status", "summary", "elapsed_ms")} for event in events]
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO runs(id,events) VALUES (?,?)", (run_id, json.dumps(safe)))

    def recent_runs(self) -> list[dict]:
        with self.connect() as con:
            return [{"id": row[0], "created_utc": row[1], "events": json.loads(row[2])} for row in con.execute("SELECT id,created,events FROM runs ORDER BY created DESC LIMIT 10")]

    def clear_saved(self):
        with self.connect() as con:
            con.execute("DELETE FROM saved")

    def spent(self) -> float:
        with self.connect() as con:
            return float(con.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage").fetchone()[0])

    def reserve(self, amount: float, cap: float = 15) -> int:
        if amount <= 0 or not 0 < cap <= 15:
            raise ValueError("Invalid budget reservation")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            used = con.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage").fetchone()[0]
            if used + amount > cap:
                raise RuntimeError("Inference budget reached. Local matching remains available.")
            return con.execute("INSERT INTO usage(reserved,status) VALUES (?, 'reserved')", (amount,)).lastrowid

    def settle(self, call_id: int, actual: float | None):
        with self.connect() as con:
            con.execute("UPDATE usage SET actual=?,status=? WHERE id=?", (actual, "settled" if actual is not None else "uncertain; reservation retained", call_id))
