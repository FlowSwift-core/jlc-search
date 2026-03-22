"""数据库模块测试"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from jlc_search.db import regexp, get_db, get_writable_db, DB_PATH


class TestRegexp:
    """正则表达式函数测试"""

    def test_basic_match(self):
        assert regexp("ABC", "XXABCXX") is True

    def test_no_match(self):
        assert regexp("XYZ", "ABCDEF") is False

    def test_empty_pattern(self):
        assert regexp("", "anything") is True

    def test_empty_text(self):
        assert regexp("something", "") is False

    def test_both_empty(self):
        assert regexp("", "") is True

    def test_invalid_regex(self):
        assert regexp("[invalid", "text") is False

    def test_none_text(self):
        assert regexp("test", None) is False

    def test_complex_pattern(self):
        assert regexp(r"^RC0603.*1K0$", "RC0603FR-071K07L") is False
        assert regexp(r"^RC0603.*1K0", "RC0603FR-071K07L") is True

    def test_case_sensitive(self):
        assert regexp("ABC", "abc") is False
        assert regexp("(?i)ABC", "abc") is True


class TestDatabaseConnection:
    """数据库连接测试"""

    def test_db_path_exists(self):
        """测试数据库路径"""
        # DB_PATH 可能不存在，但应该是一个有效的 Path 对象
        assert isinstance(DB_PATH, Path)

    def test_readonly_connection(self):
        """测试只读连接"""
        if not DB_PATH.exists():
            pytest.skip("Database not found")

        with get_db(readonly=True) as conn:
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

    def test_regexp_in_connection(self):
        """测试连接中的 regexp 函数"""
        if not DB_PATH.exists():
            pytest.skip("Database not found")

        with get_db(readonly=True) as conn:
            result = conn.execute("SELECT 'ABC123' REGEXP '[0-9]'").fetchone()
            assert result[0] == 1

    def test_writable_connection(self):
        """测试可写连接"""
        if not DB_PATH.exists():
            pytest.skip("Database not found")

        conn = get_writable_db()
        try:
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1
        finally:
            conn.close()
