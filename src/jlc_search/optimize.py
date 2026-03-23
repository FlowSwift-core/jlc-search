"""数据库优化"""

import sqlite3
from pathlib import Path


def optimize_database(source_db: Path, target_db: Path):
    """优化数据库：复制 + 清理"""

    print("[3/5] 优化数据库...")

    # 复制源库到目标
    src = sqlite3.connect(str(source_db))
    dst = sqlite3.connect(str(target_db))
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA synchronous=NORMAL")

    src.backup(dst)
    src.close()

    # CDFER 数据库已有 datasheet 列，无需添加

    # 删除过期元件
    try:
        dst.execute(
            "DELETE FROM components WHERE stock = 0 AND last_update < datetime('now', '-1 year')"
        )
    except sqlite3.OperationalError:
        pass

    dst.commit()
    dst.execute("VACUUM")

    count = dst.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    print(f"  优化完成：{count} 个元件")

    dst.close()
