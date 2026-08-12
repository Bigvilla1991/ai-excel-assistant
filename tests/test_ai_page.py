"""AI 洞察页 AppTest：守卫、本地模式生成、模板展示、模式切换。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.analyzer import analyze
from core.profiler import profile

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "5_AI洞察.py"

_SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售额": ["100", "200", "300", "400", "500", "600"],
        "订单号": ["A1", "A2", "A3", "A4", "A5", "A6"],
    }
)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def _load(at: AppTest) -> None:
    at.session_state["uploaded_name"] = "sales.csv"
    at.session_state["raw_df"] = _SALES
    at.session_state["profile"] = profile(_SALES)
    at.session_state["analysis"] = analyze(_SALES, "销售额", dimension="地区", agg="sum")
    at.run()


def test_guard_without_upload(at: AppTest) -> None:
    at.run()
    assert not at.exception
    assert any("文件上传" in str(i.value) for i in at.info)


def test_guard_without_analysis(at: AppTest) -> None:
    at.session_state["raw_df"] = _SALES
    at.session_state["profile"] = profile(_SALES)
    at.run()
    assert not at.exception
    assert any("数据分析" in str(i.value) for i in at.info)


def test_local_mode_generates_template_report(at: AppTest) -> None:
    """本地模式（无密钥）：模板报告生成且数字可溯源。"""
    _load(at)
    # 切到本地模式
    radio = at.radio[0]
    radio.set_value("local").run()
    assert not at.exception

    gen_btn = [b for b in at.button if b.label == "生成 AI 报告"]
    assert gen_btn and not gen_btn[0].disabled  # 本地模式不依赖密钥
    gen_btn[0].click().run()
    assert not at.exception

    report = at.session_state["ai_report"]
    assert report is not None
    assert report.source == "template"
    assert report.overview
    assert report.findings


def test_template_report_displayed(at: AppTest) -> None:
    """模板报告 7 段全部渲染。"""
    _load(at)
    at.radio[0].set_value("local").run()
    [b for b in at.button if b.label == "生成 AI 报告"][0].click().run()
    assert not at.exception
    headers = [h.value for h in at.markdown if h.value and h.value.startswith("### ")]
    for expected in [
        "数据概况",
        "核心发现",
        "趋势变化",
        "异常情况",
        "可能原因",
        "建议关注事项",
        "数据质量提醒",
    ]:
        assert any(expected in h for h in headers), f"缺少段落: {expected}"
    # 模板来源提示
    assert any("本地模板" in str(i.value) for i in at.info)


def test_clear_report(at: AppTest) -> None:
    _load(at)
    at.radio[0].set_value("local").run()
    [b for b in at.button if b.label == "生成 AI 报告"][0].click().run()
    assert at.session_state["ai_report"] is not None
    [b for b in at.button if b.label == "清空报告"][0].click().run()
    assert at.session_state["ai_report"] is None
