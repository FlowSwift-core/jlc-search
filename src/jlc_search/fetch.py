"""数据下载（CDFER 优化数据库，~1.5GB，每天更新）"""

import httpx
from pathlib import Path

# CDFER 每天自动更新的优化数据库
CDFER_DB_URL = "https://cdfer.github.io/jlcpcb-parts-database/jlcpcb-components.sqlite3"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def fetch_database() -> Path:
    """下载 CDFER 优化数据库（~1.5GB，仅库存≥5的元件）"""
    db_path = DATA_DIR / "jlc_search.db"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] 下载数据库 (~1.5GB)...")
    print(f"  来源: {CDFER_DB_URL}")

    with httpx.Client(follow_redirects=True, timeout=600) as client:
        with client.stream("GET", CDFER_DB_URL) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(db_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        mb = downloaded / 1024 / 1024
                        print(f"\r  进度: {pct}% ({mb:.0f} MB)", end="", flush=True)

    print(f"\n  完成: {db_path.stat().st_size / 1024 / 1024:.0f} MB")
    return db_path
