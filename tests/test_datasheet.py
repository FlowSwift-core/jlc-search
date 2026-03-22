"""Datasheet URL 采集模块测试"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from jlc_search.datasheet import fetch_datasheet_url, update_datasheet_urls


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
            datasheet_url TEXT
        );

        INSERT INTO components VALUES (1001, 'PART-A', NULL);
        INSERT INTO components VALUES (1002, 'PART-B', '');
        INSERT INTO components VALUES (1003, 'PART-C', 'http://example.com/ds.pdf');
    """)
    conn.commit()

    yield db_path, conn

    conn.close()
    db_path.unlink(missing_ok=True)


class TestFetchDatasheetUrl:
    """单个 datasheet URL 获取测试"""

    def test_fetch_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 200,
            "data": {"dataManualUrl": "http://example.com/datasheet.pdf"},
        }

        with patch("jlc_search.datasheet.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            lcsc_id, url = fetch_datasheet_url(
                1001, mock_client.return_value.__enter__.return_value
            )

            assert lcsc_id == 1001
            assert url == "http://example.com/datasheet.pdf"

    def test_fetch_api_error(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 404, "msg": "Not found"}

        with patch("jlc_search.datasheet.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            lcsc_id, url = fetch_datasheet_url(
                9999, mock_client.return_value.__enter__.return_value
            )

            assert lcsc_id == 9999
            assert url is None

    def test_fetch_exception(self):
        with patch("jlc_search.datasheet.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception(
                "Network error"
            )

            lcsc_id, url = fetch_datasheet_url(
                1001, mock_client.return_value.__enter__.return_value
            )

            assert url is None


class TestUpdateDatasheetUrls:
    """批量更新 datasheet URL 测试"""

    def test_update_empty_batch(self, test_db):
        db_path, conn = test_db

        # 所有元件都有 datasheet
        conn.execute("UPDATE components SET datasheet_url = 'http://example.com'")
        conn.commit()

        count = update_datasheet_urls(conn, batch_size=10)
        assert count == 0

    def test_update_with_mock(self, test_db):
        db_path, conn = test_db

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 200,
            "data": {"dataManualUrl": "http://new-datasheet.pdf"},
        }

        with patch("jlc_search.datasheet.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            count = update_datasheet_urls(conn, batch_size=1)

            # 应该更新了 2 个 (NULL 和空字符串)
            assert count >= 1
