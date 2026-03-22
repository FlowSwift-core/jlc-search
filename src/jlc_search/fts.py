"""FTS5 全文搜索索引管理"""

import sqlite3


def create_fts_index(conn: sqlite3.Connection):
    """创建 FTS5 虚拟表"""
    conn.executescript("""
        DROP TABLE IF EXISTS components_fts;

        CREATE VIRTUAL TABLE components_fts USING fts5(
            lcsc,
            mfr,
            description,
            category,
            package,
            attributes,
            content='components',
            content_rowid='rowid'
        );
    """)
    conn.commit()
    rebuild_fts_index(conn)


def rebuild_fts_index(conn: sqlite3.Connection):
    """重建 FTS5 索引"""
    conn.execute("INSERT INTO components_fts(components_fts) VALUES('rebuild')")
    conn.commit()
