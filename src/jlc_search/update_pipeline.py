"""更新 Pipeline 入口"""

import argparse
from pathlib import Path

from .fetch import fetch_database
from .datasheet import update_datasheet_urls
from .fts import rebuild_fts_index
from .db import get_writable_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description="JLC Search 数据更新")
    parser.add_argument("--output", "-o", default=None, help="输出数据库路径")
    parser.add_argument("--datasheet-batch", type=int, default=500, help="datasheet 采集批次大小")
    args = parser.parse_args()

    output_db = Path(args.output) if args.output else DB_PATH

    # 1. 下载 CDFER 数据库（已有 FTS5 + datasheet 列）
    fetch_database()

    # 2. 补充 datasheet URL（CDFER 可能有缺失的）
    print("[2/3] 补充 datasheet URL...")
    conn = get_writable_db()
    update_datasheet_urls(conn, batch_size=args.datasheet_batch)

    # 3. 重建 FTS5 索引（确保完整）
    print("[3/3] 重建 FTS5 索引...")
    rebuild_fts_index(conn)
    conn.close()

    size_mb = output_db.stat().st_size / 1024 / 1024
    print(f"完成！数据库: {output_db} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
