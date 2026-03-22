"""更新 Pipeline 入口"""

import argparse
import sys
from pathlib import Path

from .fetch import fetch_jlcparts
from .optimize import optimize_database
from .datasheet import update_datasheet_urls
from .fts import create_fts_index
from .db import get_writable_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description="JLC Search 数据更新")
    parser.add_argument("--output", "-o", default=None, help="输出数据库路径")
    parser.add_argument("--datasheet-batch", type=int, default=500, help="datasheet 采集批次大小")
    args = parser.parse_args()

    output_db = Path(args.output) if args.output else DB_PATH

    # 1. 下载 jlcparts
    source_db = fetch_jlcparts()

    # 2. 优化数据库
    optimize_database(source_db, output_db)

    # 3. 采集 datasheet URL
    print("[4/5] 采集 datasheet URL...")
    conn = get_writable_db()
    update_datasheet_urls(conn, batch_size=args.datasheet_batch)

    # 4. 建立 FTS5 索引
    print("[5/5] 建立 FTS5 索引...")
    create_fts_index(conn)
    conn.close()

    size_mb = output_db.stat().st_size / 1024 / 1024
    print(f"完成！数据库: {output_db} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
