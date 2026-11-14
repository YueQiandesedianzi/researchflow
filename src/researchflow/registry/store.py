"""SQLite Registry 读写。写入经 BEGIN IMMEDIATE 序列化；读取走 WAL 支持并发。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from researchflow.util import now_iso

SCHEMA_VERSION = 1


class Store:
    def __init__(self, conn: sqlite3.Connection, db_path: Path):
        self.conn = conn
        self.db_path = db_path
        self.conn.row_factory = sqlite3.Row

    @classmethod
    def open(cls, rf_dir) -> "Store":
        rf_dir = Path(rf_dir)
        rf_dir.mkdir(parents=True, exist_ok=True)
        db_path = rf_dir / "registry.sqlite"
        conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        store = cls(conn, db_path)
        store._ensure_schema()
        return store

    def _ensure_schema(self):
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if row is None:
            sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
            # executescript 自行管理事务，不能放进 _write() 的 BEGIN IMMEDIATE 里
            self.conn.executescript(sql)
            with self._write():
                self.conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_iso()),
                )

    @contextmanager
    def _write(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def close(self):
        self.conn.close()

    # ---- runs ----

    def create_run(self, node_id, block_id, block_version, cache_key=None) -> str:
        with self._write():
            seq = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM runs").fetchone()[0]
            run_id = f"RUN-{seq:06d}"
            self.conn.execute(
                "INSERT INTO runs(run_id, seq, node_id, block_id, block_version, status, cache_key, started_at)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                (run_id, seq, node_id, block_id, block_version, cache_key, now_iso()),
            )
        return run_id

    def finish_run(self, run_id, status, run_json: dict):
        with self._write():
            self.conn.execute(
                "UPDATE runs SET status=?, finished_at=?, run_json=? WHERE run_id=?",
                (status, now_iso(), json.dumps(run_json, ensure_ascii=False, default=str), run_id),
            )

    def get_run(self, run_id):
        return self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()

    def latest_run(self, node_id, statuses=("validated",)):
        marks = ",".join("?" * len(statuses))
        return self.conn.execute(
            f"SELECT * FROM runs WHERE node_id=? AND status IN ({marks}) ORDER BY seq DESC LIMIT 1",
            (node_id, *statuses),
        ).fetchone()

    def latest_any(self, node_id):
        return self.conn.execute(
            "SELECT * FROM runs WHERE node_id=? ORDER BY seq DESC LIMIT 1", (node_id,)
        ).fetchone()

    def find_cache(self, cache_key):
        return self.conn.execute(
            "SELECT * FROM runs WHERE cache_key=? AND status='validated' ORDER BY seq DESC LIMIT 1",
            (cache_key,),
        ).fetchone()

    def runs(self, node_id=None, limit=100):
        if node_id:
            return self.conn.execute(
                "SELECT * FROM runs WHERE node_id=? ORDER BY seq DESC LIMIT ?", (node_id, limit)
            ).fetchall()
        return self.conn.execute("SELECT * FROM runs ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()

    def node_status_map(self) -> dict:
        """每个节点的最新 Run 状态（任意状态）。"""
        rows = self.conn.execute(
            "SELECT node_id, status FROM runs r WHERE seq=(SELECT MAX(seq) FROM runs WHERE node_id=r.node_id)"
        ).fetchall()
        return {r["node_id"]: r["status"] for r in rows}

    def mark_interrupted(self) -> int:
        with self._write():
            cur = self.conn.execute("UPDATE runs SET status='interrupted' WHERE status='running'")
            return cur.rowcount

    # ---- artifacts / metrics / validations ----

    def add_artifact(self, run_id, port, path, sha256, type_):
        with self._write():
            self.conn.execute(
                "INSERT INTO artifacts(run_id, port, path, sha256, type) VALUES (?, ?, ?, ?, ?)",
                (run_id, port, path, sha256, type_),
            )

    def artifacts_of(self, run_id):
        return self.conn.execute(
            "SELECT * FROM artifacts WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()

    def add_metrics(self, run_id, metrics: dict):
        numeric = {k: float(v) for k, v in metrics.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")}
        with self._write():
            for name, value in numeric.items():
                self.conn.execute(
                    "INSERT OR REPLACE INTO metrics(run_id, name, value) VALUES (?, ?, ?)",
                    (run_id, name, value),
                )

    def metrics_of(self, run_id) -> dict:
        rows = self.conn.execute("SELECT name, value FROM metrics WHERE run_id=?", (run_id,)).fetchall()
        return {r["name"]: r["value"] for r in rows}

    def add_validation(self, run_id, name, passed, detail=""):
        with self._write():
            self.conn.execute(
                "INSERT INTO validations(run_id, name, passed, detail) VALUES (?, ?, ?, ?)",
                (run_id, name, 1 if passed else 0, detail),
            )

    def validations_of(self, run_id):
        return self.conn.execute(
            "SELECT * FROM validations WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()

    # ---- decisions ----

    def add_decision(self, node_id, mode, expression, auto_result, final_result, actor, comment=None):
        with self._write():
            self.conn.execute(
                "INSERT INTO decisions(node_id, mode, expression, auto_result, final_result, actor, comment, decided_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (node_id, mode, expression,
                 None if auto_result is None else int(bool(auto_result)),
                 int(bool(final_result)), actor, comment, now_iso()),
            )

    def latest_decision(self, node_id):
        return self.conn.execute(
            "SELECT * FROM decisions WHERE node_id=? ORDER BY id DESC LIMIT 1", (node_id,)
        ).fetchone()

    def recent_decisions(self, limit=50):
        return self.conn.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # ---- exports ----

    def add_export(self, out_dir, nodes, verified):
        with self._write():
            self.conn.execute(
                "INSERT INTO exports(out_dir, nodes, verified, created_at) VALUES (?, ?, ?, ?)",
                (str(out_dir), json.dumps(list(nodes), ensure_ascii=False), 1 if verified else 0, now_iso()),
            )
