"""SQLite store for matrix runs. One row per (defense, item, repeat), so every number in a report
can be traced back to the exact answer that produced it."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    model       TEXT NOT NULL,
    k           INTEGER NOT NULL,
    repeats     INTEGER NOT NULL,
    defenses    TEXT NOT NULL,       -- JSON list
    git_commit  TEXT,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS attack_results (
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    defense     TEXT NOT NULL,
    attack_id   TEXT NOT NULL,
    category    TEXT NOT NULL,
    repeat      INTEGER NOT NULL,
    seed        INTEGER NOT NULL,
    outcome     TEXT NOT NULL,       -- succeeded | mixed | resisted | not_delivered
    fired       TEXT NOT NULL,       -- JSON list of detectors that fired
    delivered   INTEGER NOT NULL,
    blocked_by  TEXT,
    dropped     TEXT NOT NULL,       -- JSON list
    gold_grade  TEXT,
    answer      TEXT NOT NULL,
    retrieved   TEXT NOT NULL,       -- JSON list
    seconds     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS gold_results (
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    defense     TEXT NOT NULL,
    gold_id     TEXT NOT NULL,
    difficulty  TEXT,
    verified    INTEGER NOT NULL,
    repeat      INTEGER NOT NULL,
    seed        INTEGER NOT NULL,
    grade       TEXT NOT NULL,       -- correct | wrong | abstained | no_number | blocked
    page_hit    INTEGER NOT NULL,
    blocked_by  TEXT,
    answer      TEXT NOT NULL,
    retrieved   TEXT NOT NULL,
    seconds     REAL NOT NULL
);
"""


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                               timeout=5, check=False).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def new_run(self, model: str, k: int, repeats: int, defenses: list[str],
                note: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO runs (started_at, model, k, repeats, defenses, git_commit, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), model, k, repeats,
             json.dumps(defenses), _git_commit(), note))
        self.db.commit()
        return cur.lastrowid

    def add_attack(self, run_id: int, row: dict) -> None:
        self._insert("attack_results", run_id, row,
                     json_cols=("fired", "dropped", "retrieved"))

    def add_gold(self, run_id: int, row: dict) -> None:
        self._insert("gold_results", run_id, row, json_cols=("retrieved",))

    def _insert(self, table: str, run_id: int, row: dict, json_cols: tuple[str, ...]) -> None:
        row = {**row, "run_id": run_id}
        for c in json_cols:
            row[c] = json.dumps(row[c])
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        self.db.commit()

    def latest_run(self) -> int | None:
        r = self.db.execute("SELECT max(id) FROM runs").fetchone()
        return r[0]

    def query(self, sql: str, *params) -> list[sqlite3.Row]:
        return self.db.execute(sql, params).fetchall()
