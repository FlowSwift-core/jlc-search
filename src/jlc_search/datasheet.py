"""Datasheet URL 采集（JLCPCB API）"""

from __future__ import annotations

import httpx
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

JLCPCB_API = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail"


def fetch_datasheet_url(lcsc_id: int, client: httpx.Client) -> tuple[int, str | None]:
    """获取单个元件的 datasheet URL"""
    url = f"{JLCPCB_API}?componentCode=C{lcsc_id}"
    try:
        resp = client.get(url, timeout=10)
        data = resp.json()
        if data.get("code") == 200:
            return lcsc_id, data["data"].get("dataManualUrl")
    except Exception:
        pass
    return lcsc_id, None


def fetch_batch_datasheets(
    lcsc_ids: list[int], max_workers: int = 5
) -> dict[int, str]:
    """批量获取 datasheet URL"""
    results = {}

    with httpx.Client(
        headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
    ) as client:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_datasheet_url, lcsc_id, client): lcsc_id
                for lcsc_id in lcsc_ids
            }

            for future in as_completed(futures):
                lcsc_id, url = future.result()
                if url:
                    results[lcsc_id] = url
                time.sleep(0.1)

    return results


def update_datasheet_urls(
    conn: sqlite3.Connection, batch_size: int = 500
) -> int:
    """更新数据库中缺少 datasheet URL 的元件"""
    cursor = conn.execute(
        "SELECT lcsc FROM components WHERE datasheet_url IS NULL OR datasheet_url = '' LIMIT ?",
        (batch_size,),
    )

    lcsc_ids = [row[0] for row in cursor.fetchall()]

    if not lcsc_ids:
        print("  没有需要更新的 datasheet URL")
        return 0

    print(f"  采集 {len(lcsc_ids)} 个 datasheet URL...")
    urls = fetch_batch_datasheets(lcsc_ids)

    for lcsc_id, url in urls.items():
        conn.execute(
            "UPDATE components SET datasheet_url = ? WHERE lcsc = ?",
            (url, lcsc_id),
        )
    conn.commit()

    print(f"  更新了 {len(urls)} 个 datasheet URL")
    return len(urls)
