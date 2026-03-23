"""FastAPI 搜索 API"""

from __future__ import annotations

import json
import re
import time
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .db import get_db, DB_PATH

# 请求模型


class QueryRequest(BaseModel):
    sql: str = Field(..., description="SQL 查询语句（只允许 SELECT）")
    timeout: int = Field(default=5000, ge=100, le=30000, description="超时（毫秒）")
    limit: int = Field(default=100, ge=1, le=1000, description="返回行数上限")


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    count: int
    time_ms: int


class SearchResponse(BaseModel):
    results: list[dict]
    count: int
    time_ms: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.exists():
        print(f"警告: 数据库不存在 {DB_PATH}")
    else:
        print(f"数据库: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    yield


app = FastAPI(
    title="JLC Search API",
    description="嘉立创元件库搜索 API（只读 SQL 查询）",
    version="0.2.0",
    lifespan=lifespan,
)


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


def sanitize_fts_query(query: str) -> str:
    """
    清理 FTS5 查询，处理特殊字符

    FTS5 特殊字符: " : * + - ( )
    策略：用引号包裹包含特殊字符的词
    """
    query = query.strip()

    # 如果已经是 FTS5 语法，不处理
    if any(c in query for c in ['"', ":", "AND", "OR", "NOT"]):
        return query

    # 分词处理
    words = query.split()
    sanitized = []

    for word in words:
        # 检查是否包含 FTS5 特殊字符
        if re.search(r"[+\-()~]", word):
            # 用引号包裹
            sanitized.append(f'"{word}"')
        else:
            sanitized.append(word)

    return " ".join(sanitized)


def parse_price(price_json: str | None) -> float | None:
    """解析价格 JSON，返回第一档价格"""
    if not price_json:
        return None
    try:
        tiers = json.loads(price_json)
        if tiers and len(tiers) > 0:
            return round(tiers[0].get("price", 0), 6)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def row_to_dict(row: tuple) -> dict:
    """将查询结果行转换为字典"""
    (
        lcsc,
        mfr,
        package,
        desc,
        stock,
        basic,
        preferred,
        price_json,
        datasheet,
        category,
        subcategory,
        rank,
    ) = row
    return {
        "lcsc": lcsc,
        "mfr": mfr,
        "package": package,
        "description": desc,
        "stock": stock,
        "is_basic": basic == 1,
        "is_preferred": preferred == 1,
        "price_usd": parse_price(price_json),
        "datasheet": datasheet,
        "category": category or "",
        "subcategory": subcategory or "",
    }


@app.get("/health")
async def health():
    """健康检查"""
    try:
        with get_db(readonly=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
        return {"status": "ok", "components": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """执行只读 SQL 查询"""
    start = time.time()

    validate_sql(request.sql)
    sql = enforce_limit(request.sql, request.limit)

    try:
        with get_db(readonly=True) as conn:
            conn.execute(f"PRAGMA busy_timeout={request.timeout}")

            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            elapsed = int((time.time() - start) * 1000)

            return QueryResponse(
                columns=columns,
                rows=[list(row) for row in rows],
                count=len(rows),
                time_ms=elapsed,
            )
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"查询错误: {e}")


@app.get("/search", response_model=SearchResponse)
async def search(q: str, limit: int = 20):
    """
    简易搜索接口（FTS5 前缀匹配，基础库优先）

    示例:
    - /search?q=STM32
    - /search?q=10K resistor
    - /search?q="100nF" capacitor
    """
    start = time.time()

    # 清理查询
    fts_query = sanitize_fts_query(q)

    # 自动添加 * 支持前缀匹配
    if not any(c in fts_query for c in ["*", '"', ":", " "]):
        fts_query = fts_query + "*"

    try:
        with get_db(readonly=True) as conn:
            cursor = conn.execute(
                """
                SELECT fts.lcsc, fts.mfr, fts.package, fts.description, 
                       c.stock, c.basic, c.preferred, c.price, fts.datasheet,
                       cat.category, cat.subcategory,
                       bm25(components_fts) as rank
                FROM components_fts fts
                LEFT JOIN components c ON c.lcsc = CAST(fts.lcsc AS INTEGER)
                LEFT JOIN categories cat ON c.category_id = cat.id
                WHERE components_fts MATCH ?
                ORDER BY c.basic DESC, c.preferred DESC, c.stock DESC, rank
                LIMIT ?
                """,
                (fts_query, min(limit, 100)),
            )

            results = [row_to_dict(row) for row in cursor.fetchall()]
            elapsed = int((time.time() - start) * 1000)

            return SearchResponse(results=results, count=len(results), time_ms=elapsed)
    except sqlite3.OperationalError as e:
        # FTS5 错误，尝试降级到 LIKE 搜索
        try:
            return _fallback_search(conn, q, limit, start)
        except Exception:
            raise HTTPException(400, f"搜索错误: {e}")


def _fallback_search(conn: sqlite3.Connection, q: str, limit: int, start: float) -> SearchResponse:
    """降级搜索：使用 LIKE"""
    like_query = f"%{q}%"
    cursor = conn.execute(
        """
        SELECT c.lcsc, c.mfr, c.package, '', 
               c.stock, c.basic, c.preferred, c.price, c.datasheet,
               cat.category, cat.subcategory,
               0 as rank
        FROM components c
        LEFT JOIN categories cat ON c.category_id = cat.id
        WHERE c.mfr LIKE ? OR c.description LIKE ?
        ORDER BY c.basic DESC, c.preferred DESC, c.stock DESC
        LIMIT ?
        """,
        (like_query, like_query, min(limit, 100)),
    )

    results = [row_to_dict(row) for row in cursor.fetchall()]
    elapsed = int((time.time() - start) * 1000)

    return SearchResponse(results=results, count=len(results), time_ms=elapsed)


@app.get("/search/params", response_model=SearchResponse)
async def search_params(
    q: Optional[str] = None,
    package: Optional[str] = None,
    resistance: Optional[str] = None,
    capacitance: Optional[str] = None,
    voltage: Optional[str] = None,
    tolerance: Optional[str] = None,
    basic_only: bool = False,
    min_stock: int = 0,
    limit: int = 20,
):
    """
    参数化搜索接口

    示例:
    - /search/params?resistance=10K&package=0603&tolerance=1%
    - /search/params?capacitance=100nF&voltage=50V&basic_only=true
    - /search/params?q=STM32&package=LQFP-48
    """
    start = time.time()

    # 构建 WHERE 条件
    conditions = []
    params = []

    if q:
        like_q = f"%{q}%"
        conditions.append("(c.mfr LIKE ? OR c.description LIKE ?)")
        params.extend([like_q, like_q])

    if package:
        conditions.append("c.package LIKE ?")
        params.append(f"%{package}%")

    if resistance:
        # 搜索电阻值
        conditions.append("(c.description LIKE ? OR c.mfr LIKE ? OR c.extra LIKE ?)")
        res_pattern = f"%{resistance}%"
        params.extend([res_pattern, res_pattern, res_pattern])

    if capacitance:
        # 搜索电容值
        conditions.append("(c.description LIKE ? OR c.mfr LIKE ? OR c.extra LIKE ?)")
        cap_pattern = f"%{capacitance}%"
        params.extend([cap_pattern, cap_pattern, cap_pattern])

    if voltage:
        conditions.append("(c.description LIKE ? OR c.extra LIKE ?)")
        volt_pattern = f"%{voltage}%"
        params.extend([volt_pattern, volt_pattern])

    if tolerance:
        conditions.append("(c.description LIKE ? OR c.extra LIKE ?)")
        tol_pattern = f"%{tolerance}%"
        params.extend([tol_pattern, tol_pattern])

    if basic_only:
        conditions.append("c.basic = 1")

    if min_stock > 0:
        conditions.append("c.stock >= ?")
        params.append(min_stock)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    try:
        with get_db(readonly=True) as conn:
            sql = f"""
                SELECT c.lcsc, c.mfr, c.package, c.description,
                       c.stock, c.basic, c.preferred, c.price, c.datasheet,
                       cat.category, cat.subcategory,
                       0 as rank
                FROM components c
                LEFT JOIN categories cat ON c.category_id = cat.id
                WHERE {where_clause}
                ORDER BY c.basic DESC, c.preferred DESC, c.stock DESC
                LIMIT ?
            """
            params.append(min(limit, 100))

            cursor = conn.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                (
                    lcsc,
                    mfr,
                    package,
                    desc,
                    stock,
                    basic,
                    preferred,
                    price_json,
                    datasheet,
                    category,
                    subcategory,
                    rank,
                ) = row
                results.append(
                    {
                        "lcsc": lcsc,
                        "mfr": mfr,
                        "package": package,
                        "description": desc or "",
                        "stock": stock,
                        "is_basic": basic == 1,
                        "is_preferred": preferred == 1,
                        "price_usd": parse_price(price_json),
                        "datasheet": datasheet,
                        "category": category or "",
                        "subcategory": subcategory or "",
                    }
                )

            elapsed = int((time.time() - start) * 1000)

            return SearchResponse(results=results, count=len(results), time_ms=elapsed)
    except Exception as e:
        raise HTTPException(400, f"搜索错误: {e}")
