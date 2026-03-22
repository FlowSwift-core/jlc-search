"""API 模块测试"""

import pytest
from fastapi.testclient import TestClient

from jlc_search.api import app, validate_sql, enforce_limit
from fastapi import HTTPException


client = TestClient(app)


class TestHealthEndpoint:
    """健康检查端点测试"""

    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestSearchEndpoint:
    """搜索端点测试"""

    def test_search_basic(self):
        response = client.get("/search?q=resistor&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data
        assert "time_ms" in data

    def test_search_with_limit(self):
        response = client.get("/search?q=0603&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 3

    def test_search_empty_query(self):
        response = client.get("/search?q=")
        # 空查询可能返回错误，这是可接受的行为
        assert response.status_code in [200, 400]


class TestQueryEndpoint:
    """SQL 查询端点测试"""

    def test_valid_select(self):
        response = client.post("/query", json={"sql": "SELECT lcsc, mfr FROM components LIMIT 3"})
        assert response.status_code == 200
        data = response.json()
        assert "columns" in data
        assert "rows" in data
        assert len(data["rows"]) <= 3

    def test_reject_insert(self):
        response = client.post("/query", json={"sql": "INSERT INTO components VALUES (1)"})
        assert response.status_code == 400

    def test_reject_delete(self):
        response = client.post("/query", json={"sql": "DELETE FROM components"})
        assert response.status_code == 400

    def test_reject_drop(self):
        response = client.post("/query", json={"sql": "DROP TABLE components"})
        assert response.status_code == 400

    def test_auto_limit(self):
        response = client.post("/query", json={"sql": "SELECT * FROM components"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) <= 100  # default limit


class TestSqlValidation:
    """SQL 验证函数测试"""

    def test_valid_select(self):
        # Should not raise
        validate_sql("SELECT * FROM components")

    def test_reject_insert(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_sql("INSERT INTO components VALUES (1)")
        assert exc_info.value.status_code == 400

    def test_reject_update(self):
        with pytest.raises(HTTPException):
            validate_sql("UPDATE components SET stock = 0")

    def test_reject_delete(self):
        with pytest.raises(HTTPException):
            validate_sql("DELETE FROM components")

    def test_reject_drop(self):
        with pytest.raises(HTTPException):
            validate_sql("DROP TABLE components")

    def test_reject_pragma(self):
        with pytest.raises(HTTPException):
            validate_sql("PRAGMA table_info(components)")


class TestEnforceLimit:
    """LIMIT 强制添加测试"""

    def test_add_limit_when_missing(self):
        result = enforce_limit("SELECT * FROM t", 50)
        assert "LIMIT 50" in result

    def test_keep_existing_limit(self):
        result = enforce_limit("SELECT * FROM t LIMIT 10", 50)
        assert "LIMIT 10" in result
        assert "LIMIT 50" not in result

    def test_remove_trailing_semicolon(self):
        result = enforce_limit("SELECT * FROM t;", 50)
        assert not result.endswith(";")
