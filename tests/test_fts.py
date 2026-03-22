"""FTS5 搜索模块测试"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from jlc_search.fts import create_fts_index, rebuild_fts_index


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
            description TEXT,
            datasheet TEXT,
            category_id INTEGER,
            basic INTEGER,
            stock INTEGER
        );

        INSERT INTO components VALUES (1, 'RC0603FR-0710KL', '0603', '10K Resistor', '', 1, 1, 1000);
        INSERT INTO components VALUES (2, 'CC0603KRX7R9BB104', '0603', '100nF Capacitor', '', 2, 1, 500);
        INSERT INTO components VALUES (3, 'STM32F103C8T6', 'LQFP-48', 'ARM MCU', 'http://example.com/ds.pdf', 3, 0, 100);
        INSERT INTO components VALUES (4, 'INA333AIDGKR', 'MSOP-8', 'Instrumentation Amp', '', 4, 0, 50);
        INSERT INTO components VALUES (5, 'LED-0805-RED', '0803', 'Red LED', '', 5, 1, 2000);
    """)
    conn.commit()

    yield db_path, conn

    conn.close()
    db_path.unlink(missing_ok=True)


class TestFtsIndex:
    """FTS5 索引测试"""

    def test_create_fts_index(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        # 检查 FTS5 表存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='components_fts'"
        ).fetchall()
        assert len(tables) == 1

    def test_fts_index_populated(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        count = conn.execute("SELECT COUNT(*) FROM components_fts").fetchone()[0]
        assert count == 5

    def test_fts_search_by_mfr(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        result = conn.execute(
            "SELECT lcsc, mfr FROM components_fts WHERE components_fts MATCH ?", ("STM32*",)
        ).fetchall()
        assert len(result) == 1
        assert result[0][1] == "STM32F103C8T6"

    def test_fts_search_by_description(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        result = conn.execute(
            "SELECT lcsc FROM components_fts WHERE components_fts MATCH ?", ("Resistor",)
        ).fetchall()
        assert len(result) == 1

    def test_fts_search_package(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        result = conn.execute(
            "SELECT lcsc FROM components_fts WHERE components_fts MATCH ?", ("0603",)
        ).fetchall()
        assert len(result) >= 2  # RC 和 CC 都是 0603

    def test_rebuild_fts_index(self, test_db):
        db_path, conn = test_db
        create_fts_index(conn)

        # 添加新数据（避免连字符，FTS5 会将其作为分隔符）
        conn.execute(
            "INSERT INTO components VALUES (6, 'NEWPART123', '0805', 'New Part', '', 1, 1, 100)"
        )
        conn.commit()

        # 重建索引
        rebuild_fts_index(conn)

        # 检查新数据被索引
        result = conn.execute(
            "SELECT lcsc FROM components_fts WHERE components_fts MATCH ?", ("NEWPART*",)
        ).fetchall()
        assert len(result) == 1
