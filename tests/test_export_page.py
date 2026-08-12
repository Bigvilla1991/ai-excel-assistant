"""导出页 AppTest：守卫、下载按钮可用性、导出内容生成。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.analyzer import analyze
from core.profiler import profile

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "6_结果导出.py"

_SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东"],
        "销售额": ["100", "200", "300"],
        "订单号": ["A1", "A2", "A3"],
    }
)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def test_guard_without_upload(at: AppTest) -> None:
    at.run()
    assert not at.exception
    assert any("文件上传" in str(i.value) for i in at.info)


def test_export_buttons_available(at: AppTest) -> None:
    """上传+体检后：清洗数据与分析工作簿下载按钮可用。"""
    at.session_state["raw_df"] = _SALES
    at.session_state["profile"] = profile(_SALES)
    at.session_state["analysis"] = analyze(_SALES, "销售额", dimension="地区", agg="sum")
    at.run()
    assert not at.exception
    buttons = [b.label for b in at.download_button]
    assert any("清洗数据" in label for label in buttons)
    assert any("分析工作簿" in label for label in buttons)


def test_ai_report_export_after_generation(at: AppTest) -> None:
    """生成 AI 报告后：md/html 下载按钮出现。"""
    from models.schemas import AIReport

    at.session_state["raw_df"] = _SALES
    at.session_state["profile"] = profile(_SALES)
    at.session_state["analysis"] = analyze(_SALES, "销售额", dimension="地区", agg="sum")
    at.session_state["ai_report"] = AIReport(overview="概况", findings=["发现1"], source="template")
    at.run()
    assert not at.exception
    labels = [b.label for b in at.download_button]
    assert any(".md" in label for label in labels)
    assert any(".html" in label for label in labels)
