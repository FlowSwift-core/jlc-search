"""FTS5 全文搜索索引管理"""

import sqlite3


def create_fts_index(conn: sqlite3.Connection):
    """创建 FTS5 虚拟表（自包含，不依赖外部表）"""
    conn.executescript("""
        DROP TABLE IF EXISTS components_fts;

        CREATE VIRTUAL TABLE components_fts USING fts5(
            lcsc,
            mfr,
            package,
            description,
            datasheet,
            category_id UNINDEXED,
            basic UNINDEXED,
            stock UNINDEXED
        );
    """)
    conn.commit()
    _populate_fts_index(conn)


def _populate_fts_index(conn: sqlite3.Connection):
    """从 components 表填充 FTS5 索引"""
    print("  填充 FTS5 索引...")

    # 获取 category 表映射
    categories = {}
    try:
        for row in conn.execute("SELECT id, name FROM categories"):
            categories[row[0]] = row[1]
    except Exception:
        pass

    # 批量插入
    conn.execute("BEGIN")
    count = 0
    for row in conn.execute("""
        SELECT lcsc, mfr, package, description, datasheet, category_id, basic, stock
        FROM components
    """):
        lcsc, mfr, package, desc, datasheet, cat_id, basic, stock = row
        cat_name = categories.get(cat_id, "")

        conn.execute(
            "INSERT INTO components_fts (lcsc, mfr, package, description, datasheet, category_id, basic, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(lcsc), mfr or "", package or "", desc or "", datasheet or "", str(cat_id or 0), str(basic or 0), str(stock or 0))
        )
        count += 1
        if count % 100000 == 0:
            conn.execute("COMMIT")
            conn.execute("BEGIN")
            print(f"    {count:,} 条...")

    conn.execute("COMMIT")
    print(f"  FTS5 索引完成: {count:,} 条")


def rebuild_fts_index(conn: sqlite3.Connection):
    """重建 FTS5 索引"""
    create_fts_index(conn)
