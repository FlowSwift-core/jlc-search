"""数据新鲜度验证"""

from __future__ import annotations

import sqlite3
import httpx
import time
from dataclasses import dataclass

JLCPCB_API = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail"


@dataclass
class VerifyResult:
    lcsc: int
    mfr: str
    db_stock: int
    api_stock: int | None
    match: bool
    error: str | None = None


def get_sample_components(conn: sqlite3.Connection, count: int = 10) -> list[tuple[int, str, int]]:
    """从数据库中随机选取典型元件（不同类别，库存>0）"""
    # 按类别随机选取
    query = """
        SELECT lcsc, mfr, stock
        FROM components
        WHERE stock > 100
        GROUP BY category_id
        ORDER BY RANDOM()
        LIMIT ?
    """
    return conn.execute(query, (count,)).fetchall()


def verify_component(conn: sqlite3.Connection, lcsc_id: int, client: httpx.Client) -> VerifyResult:
    """验证单个元件的库存"""
    row = conn.execute(
        "SELECT lcsc, mfr, stock FROM components WHERE lcsc = ?", (lcsc_id,)
    ).fetchone()

    if not row:
        return VerifyResult(lcsc_id, "N/A", 0, None, False, "数据库中不存在")

    db_stock = row[2] or 0

    try:
        resp = client.get(
            f"{JLCPCB_API}?componentCode=C{lcsc_id}",
            timeout=10
        )
        data = resp.json()
        if data.get("code") == 200:
            api_stock = data["data"].get("canPresaleNumber", 0)
            # 允许 15% 误差（实时库存波动）
            diff_pct = abs(api_stock - db_stock) / max(api_stock, 1) * 100
            match = diff_pct <= 15
            return VerifyResult(lcsc_id, row[1], db_stock, api_stock, match)
        else:
            return VerifyResult(lcsc_id, row[1], db_stock, None, False, f"API: {data.get('msg')}")
    except Exception as e:
        return VerifyResult(lcsc_id, row[1], db_stock, None, False, str(e))


def verify_freshness(db_path: str, sample_count: int = 10) -> list[VerifyResult]:
    """验证数据新鲜度"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    # 随机选取样本
    samples = get_sample_components(conn, sample_count)
    results = []

    with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}) as client:
        for lcsc_id, mfr, stock in samples:
            result = verify_component(conn, lcsc_id, client)
            results.append(result)
            time.sleep(0.2)

    conn.close()
    return results


def check_and_alert(db_path: str, bot_token: str, chat_id: str) -> bool:
    """检查新鲜度并发送报警"""
    print("  验证数据新鲜度...")
    results = verify_freshness(db_path)

    failed = [r for r in results if not r.match and not r.error]
    errors = [r for r in results if r.error]

    # 打印结果
    for r in results:
        status = "✅" if r.match else "⚠️"
        if r.error:
            status = "❌"
        stock_diff = ""
        if r.api_stock is not None and r.db_stock is not None:
            diff = r.api_stock - r.db_stock
            stock_diff = f" (diff: {diff:+d})"
        print(f"  {status} C{r.lcsc} {r.mfr[:25]:25} DB={r.db_stock} API={r.api_stock or 'ERR'}{stock_diff}")

    # 判断是否报警（超过 50% 不匹配）
    total = len(results)
    match_count = sum(1 for r in results if r.match)
    success_rate = match_count / total * 100 if total > 0 else 0

    should_alert = success_rate < 50

    if should_alert and bot_token and chat_id:
        msg = "⚠️ *数据新鲜度报警*\n\n"
        msg += f"匹配率: {success_rate:.0f}% ({match_count}/{total})\n\n"
        for r in failed:
            diff = (r.api_stock or 0) - r.db_stock
            msg += f"• C{r.lcsc} {r.mfr[:20]}: DB={r.db_stock} API={r.api_stock} ({diff:+d})\n"
        for r in errors[:3]:  # 最多显示3个错误
            msg += f"• C{r.lcsc}: {r.error}\n"

        try:
            httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=5
            )
            print("  已发送 Telegram 报警")
        except Exception as e:
            print(f"  发送报警失败: {e}")

    print(f"  匹配率: {success_rate:.0f}% ({match_count}/{total})")

    return not should_alert
