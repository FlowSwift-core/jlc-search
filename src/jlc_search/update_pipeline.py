"""更新 Pipeline 入口（支持原子更新）"""

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from .fetch import fetch_database
from .datasheet import update_datasheet_urls
from .fts import rebuild_fts_index_atomic, _build_fts_on_connection
from .verify import check_and_alert
from .db import get_writable_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description="JLC Search 数据更新")
    parser.add_argument("--output", "-o", default=None, help="输出数据库路径")
    parser.add_argument("--datasheet-batch", type=int, default=500, help="datasheet 采集批次大小")
    parser.add_argument("--skip-verify", action="store_true", help="跳过新鲜度验证")
    parser.add_argument("--atomic", action="store_true", default=True, help="原子更新（默认）")
    args = parser.parse_args()

    output_db = Path(args.output) if args.output else DB_PATH
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if args.atomic:
        _update_atomic(output_db, args, bot_token, chat_id)
    else:
        _update_inplace(output_db, args, bot_token, chat_id)


def _update_atomic(output_db: Path, args, bot_token: str, chat_id: str):
    """原子更新流程（不停机）"""
    tmp_dir = output_db.parent
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=tmp_dir, prefix="jlc_update_")
    os.close(tmp_fd)
    tmp_path = Path(tmp_path)

    print(f"[原子更新] 临时文件: {tmp_path}")

    try:
        # 1. 下载到临时文件
        print("[1/4] 下载数据库...")
        # 修改 fetch 目标为临时文件
        _download_to_tmp(tmp_path)

        # 2. 补充 datasheet URL
        print("[2/4] 补充 datasheet URL...")
        conn = get_writable_db_at(tmp_path)
        update_datasheet_urls(conn, batch_size=args.datasheet_batch)
        conn.close()

        # 3. 重建 FTS5 索引
        print("[3/4] 重建 FTS5 索引...")
        conn = get_writable_db_at(tmp_path)
        _build_fts_on_connection(conn)
        conn.close()

        # 4. 原子替换
        print("[4/4] 原子替换...")
        backup = output_db.with_suffix(".db.bak")
        if output_db.exists():
            shutil.copy2(output_db, backup)
        os.replace(str(tmp_path), str(output_db))
        print(f"[原子更新] 完成！旧版本备份: {backup}")

        # 5. 验证
        if not args.skip_verify:
            print("[验证] 数据新鲜度...")
            check_and_alert(str(output_db), bot_token, chat_id)

        size_mb = output_db.stat().st_size / 1024 / 1024
        print(f"完成！数据库: {output_db} ({size_mb:.1f} MB)")

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"原子更新失败: {e}") from e


def _update_inplace(output_db: Path, args, bot_token: str, chat_id: str):
    """就地更新流程（会短暂停机）"""
    # 1. 下载数据库
    fetch_database()

    # 2. 补充 datasheet URL
    print("[2/4] 补充 datasheet URL...")
    conn = get_writable_db()
    update_datasheet_urls(conn, batch_size=args.datasheet_batch)

    # 3. 重建 FTS5 索引（原子）
    print("[3/4] 重建 FTS5 索引（原子）...")
    conn.close()
    rebuild_fts_index_atomic(output_db, keep_backup=True)

    # 4. 验证
    if not args.skip_verify:
        print("[4/4] 验证数据新鲜度...")
        check_and_alert(str(output_db), bot_token, chat_id)

    size_mb = output_db.stat().st_size / 1024 / 1024
    print(f"完成！数据库: {output_db} ({size_mb:.1f} MB)")


def _download_to_tmp(tmp_path: Path):
    """下载数据库到临时文件"""
    import httpx

    url = "https://cdfer.github.io/jlcpcb-parts-database/jlcpcb-components.sqlite3"
    print(f"  下载: {url}")

    with httpx.Client(follow_redirects=True, timeout=600) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and downloaded % (50 * 1024 * 1024) == 0:
                        pct = downloaded * 100 // total
                        print(f"  进度: {pct}% ({downloaded // 1024 // 1024} MB)")

    print(f"  完成: {tmp_path.stat().st_size // 1024 // 1024} MB")


def get_writable_db_at(path: Path) -> sqlite3.Connection:
    """获取指定路径的可写连接"""
    import sqlite3
    from .db import regexp

    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.create_function("REGEXP", 2, regexp)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


if __name__ == "__main__":
    main()
