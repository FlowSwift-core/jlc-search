"""SQL 验证工具"""

from fastapi import HTTPException


def validate_sql(sql: str):
    """验证 SQL 安全性"""
    sql_upper = sql.upper().strip()

    if not sql_upper.startswith("SELECT"):
        raise HTTPException(400, "只允许 SELECT 查询")

    forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "ATTACH",
        "DETACH",
        "REPLACE",
        "TRUNCATE",
        "PRAGMA",
    ]
    for word in forbidden:
        if word in sql_upper:
            raise HTTPException(400, f"禁止使用 {word}")


def enforce_limit(sql: str, max_limit: int) -> str:
    """强制添加 LIMIT"""
    if "LIMIT" not in sql.upper():
        return f"{sql.rstrip(';')} LIMIT {max_limit}"
    return sql
