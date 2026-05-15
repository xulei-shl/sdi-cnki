"""Unit tests for dedup service and normalize utility."""

import pytest

from app.utils.normalize import normalize
from app.services.excel_parser import CNKI_COLUMN_MAP


class TestNormalize:

    def test_normalize_fullwidth(self):
        """全角转半角"""
        assert normalize("ａｂｃ") == "abc"

    def test_normalize_whitespace(self):
        """去空格"""
        assert normalize("hello world") == "helloworld"

    def test_normalize_punctuation(self):
        """去标点"""
        assert normalize("标题（附说明）") == "标题附说明"

    def test_normalize_lowercase(self):
        """转小写"""
        assert normalize("ABC") == "abc"

    def test_normalize_mixed(self):
        result = normalize("人工智能在智慧医疗中的应用与研究（附：数据来源说明）")
        assert "（" not in result
        assert "）" not in result
        assert "：" not in result
        assert ":" not in result
        assert "附" in result
        assert "数据来源说明" in result

    def test_normalize_empty(self):
        assert normalize("") == ""

    def test_normalize_special_chars(self):
        result = normalize("浅析【深度学习】技术在···图像识别中的应用~")
        assert "【" not in result
        assert "】" not in result
        assert "·" not in result
        assert "~" not in result


class TestDedup:

    @pytest.mark.asyncio
    async def test_batch_check_single(self, db_session):
        """简单验证批量检查函数可运行（需要 mock）"""
        records = [{"title": "测试文章", "source_journal": "测试期刊", "publish_year": 2024}]
        from app.services.dedup_service import batch_check_and_mark
        from sqlalchemy import select, func
        from app.models.meta_task import MetaTask

        result = await db_session.execute(select(func.count(MetaTask.id)))
        count = result.scalar()
        if count == 0:
            pytest.skip("No meta_tasks in DB; cannot test dedup without data")

        # Get first meta task
        from sqlalchemy import select
        mt_result = await db_session.execute(select(MetaTask).limit(1))
        mt = mt_result.scalar_one()
        from app.models.task_instance import TaskInstance
        ti_result = await db_session.execute(select(TaskInstance).where(TaskInstance.meta_task_id == mt.id).limit(1))
        ti = ti_result.scalar_one_or_none()
        if not ti:
            pytest.skip("No instances for meta task")

        marked, dup_count = await batch_check_and_mark(db_session, records, mt.id, ti.id)
        assert len(marked) == 1
        assert "title_normalized" in marked[0]
        assert "source_journal_normalized" in marked[0]


class TestExcelParser:

    def test_column_map_coverage(self):
        """验证 CNKI_COLUMN_MAP 覆盖了所有必映射列"""
        required = {"title", "authors", "source_journal", "keywords", "abstract", "publish_year", "doi", "original_url"}
        mapped = set(CNKI_COLUMN_MAP.values())
        for r in required:
            assert r in mapped, f"Missing column mapping: {r}"
