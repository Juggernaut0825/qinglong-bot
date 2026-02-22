import sqlite3, json, os
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat_history.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS summaries (
        chat_id TEXT PRIMARY KEY,
        summary TEXT NOT NULL,
        up_to_id INTEGER NOT NULL
    )""")
    return conn


def save_message(chat_id: str, role: str, content: str):
    conn = _conn()
    conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                 (chat_id, role, content))
    conn.commit()
    conn.close()


def get_recent_messages(chat_id: str, limit: int = 20) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def count_messages(chat_id: str) -> int:
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,)).fetchone()[0]
    conn.close()
    return n


def get_old_messages(chat_id: str, before_last_n: int = 20) -> list[dict]:
    """Get messages older than the most recent `before_last_n`."""
    conn = _conn()
    rows = conn.execute(
        """SELECT id, role, content FROM messages WHERE chat_id = ?
           ORDER BY id DESC LIMIT -1 OFFSET ?""",
        (chat_id, before_last_n)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2]} for r in reversed(rows)]


def save_summary(chat_id: str, summary: str, up_to_id: int):
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO summaries (chat_id, summary, up_to_id) VALUES (?, ?, ?)",
        (chat_id, summary, up_to_id)
    )
    conn.commit()
    conn.close()


def get_summary(chat_id: str) -> str | None:
    conn = _conn()
    row = conn.execute("SELECT summary FROM summaries WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return row[0] if row else None
