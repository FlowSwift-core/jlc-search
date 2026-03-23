"""FTS5 全文搜索索引管理"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


def _extract_description(desc: str, extra: str) -> str:
    """从 description 或 extra JSON 中提取描述"""
    if desc:
        return desc

    if extra:
        try:
            data = json.loads(extra)
            parts = []

            if "title" in data:
                parts.append(data["title"])
            if "description" in data:
                parts.append(data["description"])
            if "category" in data:
                cat = data["category"]
                if "name1" in cat:
                    parts.append(cat["name1"])
                if "name2" in cat:
                    parts.append(cat["name2"])
            if "attributes" in data:
                for key, val in data["attributes"].items():
                    parts.append(f"{key} {val}")

            return " ".join(parts)
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


def _build_fts_on_connection(conn: sqlite3.Connection):
    """在连接上创建并填充 FTS5 索引"""
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

    print("  填充 FTS5 索引...")
    conn.execute("BEGIN")
    count = 0

    for row in conn.execute("""
        SELECT lcsc, mfr, package, description, datasheet, category_id, basic, stock, extra
        FROM components
    """):
        lcsc, mfr, package, desc, datasheet, cat_id, basic, stock, extra = row
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


def create_fts_index(conn: sqlite3.Connection):
    """创建 FTS5 索引（直接修改，会锁库）"""
    _build_fts_on_connection(conn)


def rebuild_fts_index_atomic(db_path: str | Path, keep_backup: bool = False):
    """
    原子重建 FTS5 索引

    使用临时文件重建，完成后原子替换，避免 API 停机。

    Args:
        db_path: 数据库文件路径
        keep_backup: 是否保留备份文件
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    # 1. 在临时目录创建新数据库
    tmp_dir = db_path.parent
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=tmp_dir, prefix="jlc_fts_")
    os.close(tmp_fd)
    tmp_path = Path(tmp_path)

    print(f"[FTS重建] 临时文件: {tmp_path}")

    try:
        # 2. 复制原始数据库到临时文件（只读打开源库）
        print("[FTS重建] 复制数据库...")
        src_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(str(tmp_path))

        src_conn.backup(dst_conn)
        src_conn.close()

        # 3. 在临时库上重建 FTS5 索引
        print("[FTS重建] 重建 FTS5 索引...")
        _build_fts_on_connection(dst_conn)
        dst_conn.close()

        # 4. 原子替换文件
        print("[FTS重建] 原子替换...")
        if keep_backup:
            backup_path = db_path.with_suffix(".db.bak")
            shutil.copy2(db_path, backup_path)
            print(f"[FTS重建] 备份: {backup_path}")

        # os.replace 是原子操作（同文件系统内）
        os.replace(str(tmp_path), str(db_path))
        print("[FTS重建] 完成！")

    except Exception as e:
        # 清理临时文件
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"FTS5 重建失败: {e}") from e


def rebuild_fts_index(conn: sqlite3.Connection):
    """重建 FTS5 索引（兼容旧接口，会锁库）"""
    _build_fts_on_connection(conn)
