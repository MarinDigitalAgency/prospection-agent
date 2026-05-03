"""Gestion de la base SQLite — utilisateurs et audits."""

import json
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                name       TEXT,
                website    TEXT,
                score      INTEGER,
                pdf_path   TEXT,
                html_slug  TEXT,
                issues     TEXT,
                error      TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# ── Audits ────────────────────────────────────────

def save_audit(user_email: str, result: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audits
               (user_email, name, website, score, pdf_path, html_slug, issues, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_email.lower(),
                result.get("name"),
                result.get("website"),
                result.get("score"),
                result.get("pdf"),
                result.get("html_slug"),
                json.dumps(result.get("issues") or {}),
                result.get("error"),
            ),
        )
        conn.commit()


def get_user_audits(user_email: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audits WHERE user_email = ? ORDER BY created_at DESC",
            (user_email.lower(),),
        ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        r["issues"] = json.loads(r["issues"] or "{}")
        if r.get("pdf_path"):
            r["pdf_filename"] = Path(r["pdf_path"]).name
        else:
            r["pdf_filename"] = None
        results.append(r)
    return results


def get_user_by_email(email: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        return dict(row) if row else None


def create_user(email: str, password: str) -> dict:
    h = generate_password_hash(password)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.lower(), h),
        )
        conn.commit()
    return get_user_by_email(email)


def verify_password(email: str, password: str) -> bool:
    user = get_user_by_email(email)
    if not user:
        return False
    return check_password_hash(user["password_hash"], password)
