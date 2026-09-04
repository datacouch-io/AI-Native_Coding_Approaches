import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "tasks.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            priority INTEGER NOT NULL DEFAULT 3,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def reset_db():
    conn = get_conn()
    conn.execute("DROP TABLE IF EXISTS tasks")
    conn.commit()
    conn.close()
    init_db()
