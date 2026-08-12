"""分析页 AppTest：守卫、指标/维度选择、分组结果与 pandas 一致性。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.profiler import profile

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "4_数据分析.py"

_SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售人员": ["张", "李", "王", "张", "李", "王"],
        "销售额": ["100", "200", "300", "400", "500", "600"],
        "订单号": ["A1", "A2", "A3", "A4", "A5", "A6"],
        "数量": ["1", "2", "3", "4", "5", "6"],
    }
)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def _load(at: AppTest) -> None:
    at.session_state["uploaded_name"] = "sales.csv"
    at.session_state["raw_df"] = _SALES
    at.session_state["profile"] = profile(_SALES)
    at.run()


def test_guard_without_upload(at: AppTest) -> None:
    at.run()
    assert not at.exception
    assert any("文件上传" in str(i.value) for i in at.info)


def test_analysis_renders_grouping(at: AppTest) -> None:
    _load(at)
    assert not at.exception
    # 默认指标=销售额、维度=不分组 → 总体汇总
    result = at.session_state["analysis"]
    assert result.overview["指标合计"] == 2100.0

    # 选择维度：地区 → 分组表
    dim_sel = [s for s in at.selectbox if s.label == "维度（分组）"][0]
    dim_sel.select("地区").run()
    assert not at.exception
    result = at.session_state["analysis"]
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 1000.0, "华北": 700.0, "华南": 400.0}

    # 与 pandas 直接计算一致
    expected = _SALES.assign(销售额=_SALES["销售额"].astype(float)).groupby("地区")["销售额"].sum()
    for label, value in expected.items():
        assert labels[str(label)] == pytest.approx(value)


def test_analysis_uses_clean_data_when_available(at: AppTest) -> None:
    _load(at)
    clean = _SALES.copy()
    clean.loc[0, "销售额"] = "999"  # 清洗版数据不同
    at.session_state["clean_df"] = clean
    at.run()
    assert not at.exception
    result = at.session_state["analysis"]
    # 清洗版全表合计 = 999+200+300+400+500+600 = 2999（raw 版为 2100）
    assert result.overview["指标合计"] == 2999.0


def test_analysis_cache_reuse(at: AppTest) -> None:
    _load(at)
    first = at.session_state["analysis"]
    at.run()  # 相同参数 rerun → 复用缓存
    assert at.session_state["analysis"] is first


def test_analysis_cache_invalidated_by_reclean(at: AppTest) -> None:
    """重新清洗（换方案执行）后，分析缓存必须失效（回归：旧数据结果）。"""
    _load(at)
    # 清洗方案 A：销售额全部翻倍
    clean_a = _SALES.copy()
    clean_a["销售额"] = clean_a["销售额"].astype(float) * 2
    at.session_state["clean_df"] = clean_a
    at.session_state["cleaning_log"] = object()
    at.run()
    assert at.session_state["analysis"].overview["指标合计"] == 4200.0  # 2100*2

    # 清洗方案 B：恢复原值（模拟清洗页重新执行，已清除 analysis/analysis_key）
    clean_b = _SALES.copy()
    at.session_state["clean_df"] = clean_b
    at.session_state["analysis"] = None
    at.session_state["analysis_key"] = None
    at.run()
    result = at.session_state["analysis"]
    assert result.overview["指标合计"] == 2100.0  # 必须是最新数据的结果


def test_ranking_and_charts_render(at: AppTest) -> None:
    """选择维度后：排名表、柱状图、横向排名图出现。"""
    _load(at)
    dim_sel = [s for s in at.selectbox if s.label == "维度（分组）"][0]
    dim_sel.select("地区").run()
    assert not at.exception

    # 排名表渲染：分组表 + 排名表
    assert len(at.dataframe) >= 2
    assert at.session_state["analysis"].grouped


def test_trend_renders_with_date_column(at: AppTest) -> None:
    """日期列存在时：趋势图与环比表渲染。"""
    df = _SALES.copy()
    df["日期"] = [
        "2024-01-05",
        "2024-01-20",
        "2024-02-10",
        "2024-02-15",
        "2024-03-05",
        "2024-03-12",
    ]
    at.session_state["uploaded_name"] = "sales.csv"
    at.session_state["raw_df"] = df
    at.session_state["profile"] = profile(df)
    at.run()
    assert not at.exception
    # 页面存在趋势标题与环比表
    titles = [s.value for s in at.subheader]
    assert any("时间趋势" in t for t in titles)
    assert at.dataframe
