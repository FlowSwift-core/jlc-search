"""SQLite 数据库连接与工具函数"""

import sqlite3
import re
import os
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent.parent.parent / "data" / "jlc_search.db"))


def regexp(pattern: str, text: str) -> bool:
    """SQLite REGEXP 函数"""
    try:
        return bool(re.search(pattern, text or ""))
    except re.error:
        return False


@contextmanager
def get_db(readonly: bool = True):
    """获取数据库连接（只读或读写）"""
    uri = f"file:{DB_PATH}"
    if readonly:
        uri += "?mode=ro"

    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, regexp)

    try:
        yield conn
    finally:
        conn.close()


def get_writable_db() -> sqlite3.Connection:
    """获取可写连接（用于更新）"""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.create_function("REGEXP", 2, regexp)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
