"""Pydantic 数据模型"""

from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    sql: str = Field(..., description="SQL 查询语句（只允许 SELECT）")
    timeout: int = Field(default=5000, ge=100, le=30000, description="超时（毫秒）")
    limit: int = Field(default=100, ge=1, le=1000, description="返回行数上限")


class AiSearchRequest(BaseModel):
    q: str = Field(..., description="自然语言搜索查询")
    limit: int = Field(default=20, ge=1, le=100)


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    count: int
    time_ms: int


class SearchResponse(BaseModel):
    results: list[dict]
    count: int
    time_ms: int
    sql: Optional[str] = None
