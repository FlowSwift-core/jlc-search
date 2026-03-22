"""更新 Pipeline 入口"""

import argparse
import os
from pathlib import Path

from .fetch import fetch_database
from .datasheet import update_datasheet_urls
from .fts import rebuild_fts_index
from .verify import check_and_alert
from .db import get_writable_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description="JLC Search 数据更新")
    parser.add_argument("--output", "-o", default=None, help="输出数据库路径")
    parser.add_argument("--datasheet-batch", type=int, default=500, help="datasheet 采集批次大小")
    parser.add_argument("--skip-verify", action="store_true", help="跳过新鲜度验证")
    args = parser.parse_args()

    output_db = Path(args.output) if args.output else DB_PATH
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    # 1. 下载 CDFER 数据库
    fetch_database()

    # 2. 补充 datasheet URL
    print("[2/4] 补充 datasheet URL...")
    conn = get_writable_db()
    update_datasheet_urls(conn, batch_size=args.datasheet_batch)

    # 3. 重建 FTS5 索引
    print("[3/4] 重建 FTS5 索引...")
    rebuild_fts_index(conn)
    conn.close()

    # 4. 验证数据新鲜度
    if not args.skip_verify:
        print("[4/4] 验证数据新鲜度...")
        check_and_alert(str(output_db), bot_token, chat_id)
    else:
        print("[4/4] 跳过新鲜度验证")

    size_mb = output_db.stat().st_size / 1024 / 1024
    print(f"完成！数据库: {output_db} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
