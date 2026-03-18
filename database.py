import json
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "agentgrade.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                code_input TEXT NOT NULL,
                language VARCHAR(50) DEFAULT 'python',
                overall_score REAL,
                audit_agreement REAL,
                remediation_json TEXT,
                agent_prompt TEXT,
                status VARCHAR(20) DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS dimension_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eval_run_id INTEGER REFERENCES eval_runs(id),
                dimension VARCHAR(50) NOT NULL,
                primary_score INTEGER,
                primary_justification TEXT,
                primary_findings TEXT,
                audit_score INTEGER,
                audit_justification TEXT,
                audit_findings TEXT,
                confidence VARCHAR(10),
                score_gap INTEGER
            );
            """
        )


def create_eval_run(code_input: str, language: str = "python", status: str = "pending") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO eval_runs (code_input, language, status)
            VALUES (?, ?, ?)
            """,
            (code_input, language, status),
        )
        return int(cursor.lastrowid)


def update_eval_run(eval_run_id: int, **fields: Any) -> None:
    if not fields:
        return

    columns = ", ".join(f"{key} = ?" for key in fields.keys())
    values = list(fields.values()) + [eval_run_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE eval_runs SET {columns} WHERE id = ?", values)


def insert_dimension_score(
    eval_run_id: int,
    dimension: str,
    primary_score: int | None,
    primary_justification: str,
    primary_findings: list[dict[str, Any]],
    audit_score: int | None,
    audit_justification: str,
    audit_findings: list[dict[str, Any]],
    confidence: str,
    score_gap: int | None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO dimension_scores (
                eval_run_id, dimension, primary_score, primary_justification, primary_findings,
                audit_score, audit_justification, audit_findings, confidence, score_gap
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_run_id,
                dimension,
                primary_score,
                primary_justification,
                json.dumps(primary_findings),
                audit_score,
                audit_justification,
                json.dumps(audit_findings),
                confidence,
                score_gap,
            ),
        )


def get_eval_run(eval_run_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (eval_run_id,)).fetchone()
        return dict(row) if row else None


def get_dimension_scores(eval_run_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dimension_scores WHERE eval_run_id = ? ORDER BY id ASC", (eval_run_id,)
        ).fetchall()

    dimensions = []
    for row in rows:
        item = dict(row)
        item["primary_findings"] = json.loads(item["primary_findings"] or "[]")
        item["audit_findings"] = json.loads(item["audit_findings"] or "[]")
        dimensions.append(item)
    return dimensions

