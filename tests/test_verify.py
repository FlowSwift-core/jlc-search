"""数据验证模块测试"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from jlc_search.verify import (
    VerifyResult,
    get_sample_components,
    verify_component,
    verify_freshness,
)


@pytest.fixture
def test_db():
    """创建测试数据库"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE components (
            lcsc INTEGER PRIMARY KEY,
            mfr TEXT,
            package TEXT,
            stock INTEGER,
            category_id INTEGER
        );

        INSERT INTO components VALUES (1001, 'PART-A', '0603', 1000, 1);
        INSERT INTO components VALUES (1002, 'PART-B', '0805', 500, 2);
        INSERT INTO components VALUES (1003, 'PART-C', '0402', 200, 3);
        INSERT INTO components VALUES (1004, 'PART-D', '1206', 0, 4);
    """)
    conn.commit()

    yield db_path, conn

    conn.close()
    db_path.unlink(missing_ok=True)


class TestVerifyResult:
    """VerifyResult 数据类测试"""

    def test_create_result(self):
        result = VerifyResult(lcsc=1001, mfr="TEST-PART", db_stock=100, api_stock=95, match=True)
        assert result.lcsc == 1001
        assert result.match is True
        assert result.error is None

    def test_create_result_with_error(self):
        result = VerifyResult(
            lcsc=1001, mfr="TEST-PART", db_stock=100, api_stock=None, match=False, error="API error"
        )
        assert result.error == "API error"


class TestGetSampleComponents:
    """采样函数测试"""

    def test_get_samples(self, test_db):
        db_path, conn = test_db
        samples = get_sample_components(conn, count=2)
        assert len(samples) <= 2
        for lcsc, mfr, stock in samples:
            assert stock > 100

    def test_get_all_samples(self, test_db):
        db_path, conn = test_db
        samples = get_sample_components(conn, count=100)
        # 有 3 个元件库存 > 100 (1000, 500, 200)，按 category_id 分组
        assert len(samples) == 3
        # 检查库存都 > 100
        for _, _, stock in samples:
            assert stock > 100


class TestVerifyComponent:
    """元件验证测试"""

    def test_verify_existing_component(self, test_db):
        db_path, conn = test_db

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 200,
            "data": {"canPresaleNumber": 990},  # 接近 1000
        }

        with patch("jlc_search.verify.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            result = verify_component(conn, 1001, mock_client.return_value.__enter__.return_value)

            assert result.lcsc == 1001
            assert result.db_stock == 1000
            assert result.api_stock == 990
            assert result.match is True  # 1% 差异，在 15% 容差内

    def test_verify_nonexistent_component(self, test_db):
        db_path, conn = test_db

        with patch("jlc_search.verify.httpx.Client") as mock_client:
            result = verify_component(conn, 9999, mock_client.return_value.__enter__.return_value)

            assert result.match is False
            assert "不存在" in result.error


class TestVerifyFreshness:
    """新鲜度验证测试"""

    def test_verify_freshness(self, test_db):
        db_path, conn = test_db

        # Mock API responses
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 200, "data": {"canPresaleNumber": 100}}

        with patch("jlc_search.verify.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            results = verify_freshness(str(db_path), sample_count=2)

            assert len(results) == 2
            for r in results:
                assert r.api_stock == 100
