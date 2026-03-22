"""FastAPI 搜索 API"""

from __future__ import annotations

import time
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
    version="0.1.0",
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


@app.get("/health")
async def health():
    """健康检查"""
    try:
        with get_db(readonly=True) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": str(DB_PATH)}
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


@app.get("/search")
async def search(q: str, limit: int = 20):
    """简易搜索接口（FTS5 前缀匹配）"""
    start = time.time()

    # 自动添加 * 支持前缀匹配
    fts_query = q.strip()
    if not any(c in fts_query for c in ["*", '"', ":", " "]):
        fts_query = fts_query + "*"

    try:
        with get_db(readonly=True) as conn:
            # FTS5 搜索，JOIN components 获取 stock/basic
            cursor = conn.execute(
                """
                SELECT fts.lcsc, fts.mfr, fts.package, fts.description, 
                       c.stock, c.basic, fts.datasheet,
                       bm25(components_fts) as rank
                FROM components_fts fts
                LEFT JOIN components c ON c.lcsc = CAST(fts.lcsc AS INTEGER)
                WHERE components_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, min(limit, 100)),
            )

            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            elapsed = int((time.time() - start) * 1000)

            return {"results": rows, "count": len(rows), "time_ms": elapsed}
    except Exception as e:
        raise HTTPException(400, f"搜索错误: {e}")
