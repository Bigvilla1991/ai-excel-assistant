"""ChartEngine 单元测试：四类图生成、标题规则、分类截断、同源数据。"""

from __future__ import annotations

import pandas as pd

from core.analyzer import analyze, build_rankings, trend
from core.chart_engine import (
    bar_chart,
    hbar_ranking,
    line_chart,
    scatter_chart,
)

SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售额": ["100", "200", "300", "400", "500", "600"],
        "数量": ["1", "2", "3", "4", "5", "6"],
        "日期": [
            "2024-01-05",
            "2024-01-20",
            "2024-02-10",
            "2024-02-15",
            "2024-03-05",
            "2024-03-12",
        ],
    }
)


def test_bar_chart_type_and_title() -> None:
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    fig = bar_chart(result)
    assert fig.data[0].type == "bar"
    assert "销售额" in fig.layout.title.text
    assert "地区" in fig.layout.title.text
    # 数据与分组结果同源（plotly 存储为 tuple）
    assert list(fig.data[0].x) == ["华东", "华北", "华南"]
    assert list(fig.data[0].y) == [1000.0, 700.0, 400.0]


def test_bar_chart_category_truncation() -> None:
    df = pd.DataFrame({"类别": [f"c{i}" for i in range(30)], "数值": [float(i) for i in range(30)]})
    result = analyze(df, "数值", dimension="类别", agg="sum")
    fig = bar_chart(result)  # 默认截断 20
    assert len(fig.data[0].x) == 20
    # 截断取的是数值最大的 20 类（c10~c29）
    assert list(fig.data[0].x)[0] == "c29"
    assert "c10" in list(fig.data[0].x)
    assert "c9" not in list(fig.data[0].x)


def test_bar_chart_sorted_by_value() -> None:
    """柱状图按值降序（与排名图一致）。"""
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    fig = bar_chart(result)
    assert list(fig.data[0].x) == ["华东", "华北", "华南"]
    assert list(fig.data[0].y) == [1000.0, 700.0, 400.0]


def test_hbar_ranking_order() -> None:
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    rankings = build_rankings(result, top_n=3)
    fig = hbar_ranking(rankings, "销售额")
    assert fig.data[0].type == "bar"
    assert fig.data[0].orientation == "h"
    # 横向条形图从下到上显示，第 1 名应在顶部
    assert list(fig.data[0].y) == ["华南", "华北", "华东"]  # 底部→顶部
    assert list(fig.data[0].x) == [400.0, 700.0, 1000.0]


def test_hbar_ranking_bottom_title() -> None:
    """BOTTOM 模式标题应为 BOTTOM N。"""
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    rankings = build_rankings(result, top_n=2, bottom=True)
    fig = hbar_ranking(rankings, "销售额", bottom=True)
    assert "BOTTOM 2" in fig.layout.title.text
    assert "TOP" not in fig.layout.title.text


def test_hbar_ranking_empty() -> None:
    """空排名输入不崩溃。"""
    fig = hbar_ranking([], "销售额")
    assert fig.data[0].type == "bar"
    assert len(fig.data[0].y) == 0


def test_line_chart_peak_low_markers() -> None:
    points = trend(SALES, "销售额", "日期", granularity="month")
    fig = line_chart(points, "销售额", "月")
    assert fig.data[0].type == "scatter"
    assert "趋势" in fig.layout.title.text
    annotations = [a.text for a in fig.layout.annotations]
    assert "峰值" in annotations
    assert "低点" in annotations


def test_scatter_chart() -> None:
    fig = scatter_chart(SALES, "销售额", "数量")
    assert fig.data[0].type == "scatter"
    assert fig.data[0].mode == "markers"
    assert len(fig.data[0].x) == 6  # 全部有效点
    assert "销售额" in fig.layout.title.text


def test_scatter_chart_sampling() -> None:
    df = pd.DataFrame(
        {"x": [float(i) for i in range(5000)], "y": [float(i * 2) for i in range(5000)]}
    )
    fig = scatter_chart(df, "x", "y")
    assert len(fig.data[0].x) == 2000  # 采样上限


def test_scatter_chart_missing_values_skipped() -> None:
    df = pd.DataFrame({"x": ["1", None, "3"], "y": ["4", "5", None]})
    fig = scatter_chart(df, "x", "y")
    assert len(fig.data[0].x) == 1  # 仅 (1,4) 有效
