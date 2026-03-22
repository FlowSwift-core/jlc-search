"""jlcparts 数据下载与解压"""

import httpx
import zipfile
import shutil
from pathlib import Path
from io import BytesIO

JLCPARTS_BASE = "https://yaqwsx.github.io/jlcparts/data/"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"


def download_jlcparts_cache() -> Path:
    """下载 jlcparts 缓存文件（zip 分卷）"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(40):
        if i == 0:
            filename = "cache.zip"
        else:
            filename = f"cache.z{i:02d}"

        url = JLCPARTS_BASE + filename
        local_path = CACHE_DIR / filename

        if local_path.exists():
            continue

        print(f"  下载 {filename}...")
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=300)
            if resp.status_code != 200:
                if i == 0:
                    raise Exception(f"无法下载 {url}")
                break
            local_path.write_bytes(resp.content)
        except httpx.ConnectError:
            if i == 0:
                raise
            break

    return CACHE_DIR / "cache.zip"


def extract_cache() -> Path:
    """解压缓存文件"""
    zip_path = CACHE_DIR / "cache.zip"
    db_path = DATA_DIR / "cache.sqlite3"

    if db_path.exists():
        print("  缓存已存在，跳过解压")
        return db_path

    print("  解压数据库...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(str(DATA_DIR))

    return db_path


def fetch_jlcparts() -> Path:
    """完整流程：下载 + 解压"""
    print("[1/5] 下载 jlcparts 数据...")
    download_jlcparts_cache()

    print("[2/5] 解压数据库...")
    return extract_cache()
