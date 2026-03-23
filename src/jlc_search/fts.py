"""FTS5 全文搜索索引管理"""

from __future__ import annotations

import json
import sqlite3


def create_fts_index(conn: sqlite3.Connection):
    """创建 FTS5 虚拟表"""
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


def _extract_description(desc: str, extra: str) -> str:
    """从 description 或 extra JSON 中提取描述"""
    # 优先用 description
    if desc:
        return desc

    # 从 extra JSON 中提取
    if extra:
        try:
            data = json.loads(extra)
            parts = []

            # 标题
            if "title" in data:
                parts.append(data["title"])

            # 描述
            if "description" in data:
                parts.append(data["description"])

            # 类别
            if "category" in data:
                cat = data["category"]
                if "name1" in cat:
                    parts.append(cat["name1"])
                if "name2" in cat:
                    parts.append(cat["name2"])

            # 属性
            if "attributes" in data:
                for key, val in data["attributes"].items():
                    parts.append(f"{key} {val}")

            return " ".join(parts)
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


def _populate_fts_index(conn: sqlite3.Connection):
    """从 components 表填充 FTS5 索引"""
    print("  填充 FTS5 索引...")

    conn.execute("BEGIN")
    count = 0

    for row in conn.execute("""
        SELECT lcsc, mfr, package, description, datasheet, category_id, basic, stock, extra
        FROM components
    """):
        lcsc, mfr, package, desc, datasheet, cat_id, basic, stock, extra = row

        # 提取完整描述
        full_desc = _extract_description(desc, extra)

        conn.execute(
            "INSERT INTO components_fts (lcsc, mfr, package, description, datasheet, category_id, basic, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(lcsc),
                mfr or "",
                package or "",
                full_desc,
                datasheet or "",
                str(cat_id or 0),
                str(basic or 0),
                str(stock or 0),
            ),
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
