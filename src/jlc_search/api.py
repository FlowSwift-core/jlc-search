"""FastAPI 搜索 API"""

from __future__ import annotations

import json
import re
import time
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException

from .db import get_db, DB_PATH
from .models import QueryRequest, AiSearchRequest, QueryResponse, SearchResponse
from .validators import validate_sql, enforce_limit
from .ai_search import generate_sql_with_ai


# 工具函数


def sanitize_fts_query(query: str) -> str:
    """清理 FTS5 查询"""
    query = query.strip()
    if any(c in query for c in ['"', ":", "AND", "OR", "NOT"]):
        return query

    words = query.split()
    sanitized = []
    for word in words:
        if re.search(r"[+\-()~]", word):
            sanitized.append(f'"{word}"')
        else:
            sanitized.append(word)
    return " ".join(sanitized)


def parse_price(price_json: str | None) -> float | None:
    """解析价格 JSON"""
    if not price_json:
        return None
    try:
        tiers = json.loads(price_json)
        if tiers and len(tiers) > 0:
            return round(tiers[0].get("price", 0), 6)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def extract_description(desc: str | None, extra_json: str | None) -> str:
    """从 description 或 extra JSON 中提取描述"""
    # 优先使用 description
    if desc:
        return desc

    # 从 extra JSON 中提取
    if extra_json:
        try:
            extra = json.loads(extra_json)
            # 优先使用 description 字段
            if "description" in extra and extra["description"]:
                return extra["description"]
            # 否则使用 title
            if "title" in extra and extra["title"]:
                return extra["title"]
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


def row_to_dict(row: tuple, extra_json: str | None = None) -> dict:
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

    # 提取描述
    description = extract_description(desc, extra_json)

    return {
        "lcsc": lcsc,
        "mfr": mfr,
        "package": package,
        "description": description,
        "stock": stock,
        "is_basic": basic == 1,
        "is_preferred": preferred == 1,
        "price_usd": parse_price(price_json),
        "datasheet": datasheet,
        "category": category or "",
        "subcategory": subcategory or "",
    }


# FastAPI 应用


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.exists():
        print(f"警告: 数据库不存在 {DB_PATH}")
    else:
        print(f"数据库: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    yield


app = FastAPI(
    title="JLC Search API",
    description="嘉立创元件库搜索 API（支持 AI 智能搜索）",
    version="0.3.0",
    lifespan=lifespan,
)


# API 端点


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
    简易搜索接口（FTS5 前缀匹配）

    示例:
    - /search?q=STM32
    - /search?q=10K resistor
    """
    start = time.time()

    fts_query = sanitize_fts_query(q)
    if not any(c in fts_query for c in ["*", '"', ":", " "]):
        fts_query = fts_query + "*"

    try:
        with get_db(readonly=True) as conn:
            cursor = conn.execute(
                """
                SELECT fts.lcsc, fts.mfr, fts.package, fts.description, 
                       c.stock, c.basic, c.preferred, c.price, fts.datasheet,
                       cat.category, cat.subcategory,
                       bm25(components_fts) as rank,
                       c.extra
                FROM components_fts fts
                LEFT JOIN components c ON c.lcsc = CAST(fts.lcsc AS INTEGER)
                LEFT JOIN categories cat ON c.category_id = cat.id
                WHERE components_fts MATCH ?
                ORDER BY c.basic DESC, c.preferred DESC, c.stock DESC, rank
                LIMIT ?
                """,
                (fts_query, min(limit, 100)),
            )

            results = []
            for row in cursor.fetchall():
                extra_json = row[-1]  # extra 是最后一列
                results.append(row_to_dict(row[:-1], extra_json))  # 传入不含 extra 的行
            elapsed = int((time.time() - start) * 1000)

            return SearchResponse(results=results, count=len(results), time_ms=elapsed)
    except sqlite3.OperationalError:
        # 降级到 LIKE 搜索
        return _fallback_search(conn, q, limit, start)


def _fallback_search(conn, q: str, limit: int, start: float) -> SearchResponse:
    """降级搜索：使用 LIKE"""
    like_query = f"%{q}%"
    cursor = conn.execute(
        """
        SELECT c.lcsc, c.mfr, c.package, '', 
               c.stock, c.basic, c.preferred, c.price, c.datasheet,
               cat.category, cat.subcategory,
               0 as rank,
               c.extra
        FROM components c
        LEFT JOIN categories cat ON c.category_id = cat.id
        WHERE c.mfr LIKE ? OR c.description LIKE ?
        ORDER BY c.basic DESC, c.preferred DESC, c.stock DESC
        LIMIT ?
        """,
        (like_query, like_query, min(limit, 100)),
    )

    results = []
    for row in cursor.fetchall():
        extra_json = row[-1]  # extra 是最后一列
        results.append(row_to_dict(row[:-1], extra_json))

    elapsed = int((time.time() - start) * 1000)

    return SearchResponse(results=results, count=len(results), time_ms=elapsed)


@app.post("/search/ai", response_model=SearchResponse)
async def search_ai(request: AiSearchRequest):
    """
    AI 智能搜索（自然语言查询 + 语义理解）

    示例请求：
    {
        "q": "USB-C 连接器",
        "limit": 5
    }

    AI 会理解查询意图、识别类别，生成优化的 SQL。
    """
    start = time.time()

    # 使用 AI 解析意图并生成 SQL
    sql, intent = generate_sql_with_ai(request.q)

    # 验证 SQL
    validate_sql(sql)
    sql = enforce_limit(sql, request.limit)

    try:
        with get_db(readonly=True) as conn:
            cursor = conn.execute(sql)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            results = []
            for row in rows:
                row_dict = dict(zip(columns, row))

                # 解析价格
                if "price" in row_dict:
                    row_dict["price_usd"] = parse_price(row_dict.pop("price"))
                if "basic" in row_dict:
                    row_dict["is_basic"] = row_dict.pop("basic") == 1
                if "preferred" in row_dict:
                    row_dict["is_preferred"] = row_dict.pop("preferred") == 1

                # 添加默认字段
                row_dict.setdefault("description", "")
                row_dict.setdefault("category", "")
                row_dict.setdefault("subcategory", "")
                row_dict.setdefault("datasheet", "")

                results.append(row_dict)

            elapsed = int((time.time() - start) * 1000)

            return SearchResponse(
                results=results,
                count=len(results),
                time_ms=elapsed,
                sql=sql,
            )
    except Exception as e:
        raise HTTPException(400, f"搜索错误: {e}\n生成的 SQL: {sql}")
