"""DataAnalyzer 单元测试：基础统计、分组汇总、排名与趋势。"""

from __future__ import annotations

import pandas as pd
import pytest

from core.analyzer import analyze, build_rankings, describe, trend

SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售人员": ["张", "李", "王", "张", "李", "王"],
        "销售额": ["100", "200", "300", "400", "500", None],  # 含文本空值
        "订单号": ["A1", "A2", "A3", "A4", "A5", "A6"],
        "数量": ["1", "2", "3", "4", "5", "6"],
    }
)


# ---------------------------------------------------------------- 基础统计


def test_describe_matches_manual() -> None:
    stats = describe(SALES, ["销售额", "数量"])
    s = stats["销售额"]
    # 有效值 [100,200,300,400,500]（None 排除）
    assert s["数据量"] == 5.0
    assert s["总计"] == 1500.0
    assert s["平均值"] == 300.0
    assert s["中位数"] == 300.0
    assert s["最小值"] == 100.0
    assert s["最大值"] == 500.0
    assert s["空值数量"] == 1.0
    # 标准差 = sqrt(mean((x-300)^2)) = sqrt(20000) ≈ 158.11（样本标准差）
    assert s["标准差"] == pytest.approx(158.1139, abs=0.01)

    q = stats["数量"]
    assert q["总计"] == 21.0
    assert q["平均值"] == 3.5


def test_describe_empty_column() -> None:
    df = pd.DataFrame({"空列": [None, None, None], "正常": ["1", "2", "3"]})
    stats = describe(df, ["空列", "正常"])
    assert stats["空列"]["数据量"] == 0.0
    assert stats["空列"]["总计"] is None
    assert stats["正常"]["总计"] == 6.0


def test_describe_text_column_excluded() -> None:
    stats = describe(SALES, ["地区"])  # 非数值列传参时统计为空值数据
    assert stats["地区"]["数据量"] == 0.0


# ---------------------------------------------------------------- 维度分组


def test_groupby_sum_matches_excel() -> None:
    """华东 = 100+300 = 400（None 不参与求和，等价 Excel SUM）。"""
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 400.0, "华北": 700.0, "华南": 400.0}
    assert result.overview["指标合计"] == 1500.0
    # 占比
    shares = {g.label: g.share for g in result.grouped}
    assert shares["华东"] == pytest.approx(400 / 1500)
    assert sum(s for s in shares.values() if s) == pytest.approx(1.0)


def test_groupby_mean() -> None:
    result = analyze(SALES, "销售额", dimension="地区", agg="mean")
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 200.0, "华北": 350.0, "华南": 400.0}


def test_groupby_count() -> None:
    """count = 组内行数（含空值行）。"""
    result = analyze(SALES, "销售额", dimension="地区", agg="count")
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 3.0, "华北": 2.0, "华南": 1.0}


def test_groupby_nunique() -> None:
    """nunique = 组内订单号去重数。"""
    df = SALES.copy()
    df.loc[0, "订单号"] = "A6"  # 华东（行 0,2,5）出现重复订单号
    result = analyze(df, "订单号", dimension="地区", agg="nunique")
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 2.0, "华北": 2.0, "华南": 1.0}


def test_include_blank_dimension() -> None:
    df = pd.DataFrame({"地区": ["华东", None, "华北"], "销售额": ["1", "2", "3"]})
    # 默认排除空维度
    result = analyze(df, "销售额", dimension="地区", agg="sum")
    assert "（空）" not in [g.label for g in result.grouped]
    # 包含空维度
    result2 = analyze(df, "销售额", dimension="地区", agg="sum", include_blank=True)
    labels = {g.label: g.value for g in result2.grouped}
    assert labels == {"华东": 1.0, "（空）": 2.0, "华北": 3.0}


def test_no_dimension_overall() -> None:
    result = analyze(SALES, "销售额", agg="sum")
    assert len(result.grouped) == 1
    assert result.grouped[0].label == "全部"
    assert result.grouped[0].value == 1500.0
    assert result.dimension is None


def test_text_metric_count_ok() -> None:
    result = analyze(SALES, "地区", agg="count")
    assert result.grouped[0].value == 6.0


# ---------------------------------------------------------------- 边界


def test_analyze_does_not_modify_df() -> None:
    snapshot = SALES.copy(deep=True)
    analyze(SALES, "销售额", dimension="地区", agg="sum")
    pd.testing.assert_frame_equal(SALES, snapshot)


def test_analyze_unknown_columns() -> None:
    with pytest.raises(ValueError, match="指标列"):
        analyze(SALES, "不存在")
    with pytest.raises(ValueError, match="维度列"):
        analyze(SALES, "销售额", dimension="不存在")


def test_cleaned_numeric_column() -> None:
    """清洗后数值列（Float64）直接可分析。"""
    df = pd.DataFrame({"地区": ["华东", "华北"], "销售额": [100.5, 200.0]})
    result = analyze(df, "销售额", dimension="地区", agg="sum")
    assert result.grouped[0].value == 100.5


# ---------------------------------------------------------------- reviewer 补测


def test_mean_empty_group_no_crash() -> None:
    """组内指标全空：mean 不崩溃，该组 value 为 None（回归：float(pd.NA)）。"""
    df = pd.DataFrame({"地区": ["华东", "华东", "华南"], "销售额": ["100", None, None]})
    result = analyze(df, "销售额", dimension="地区", agg="mean")
    labels = {g.label: g.value for g in result.grouped}
    assert labels["华东"] == 100.0
    assert labels["华南"] is None
    # mean 聚合不填 share（防误导）
    assert all(g.share is None for g in result.grouped)


def test_aggregate_total_empty_all_none() -> None:
    """指标列全空：sum/mean 合计为 None 不崩溃。"""
    df = pd.DataFrame({"地区": ["华东", "华北"], "销售额": [None, None]})
    result = analyze(df, "销售额", agg="sum")
    assert result.grouped[0].value is None
    assert result.overview["指标合计"] is None

    result_mean = analyze(df, "销售额", agg="mean")
    assert result_mean.grouped[0].value is None


def test_aggregate_total_branches() -> None:
    df = pd.DataFrame({"地区": ["华东", "华北"], "订单号": ["A1", "A1"]})
    r_count = analyze(df, "地区", agg="count")
    assert r_count.grouped[0].value == 2.0
    r_nunique = analyze(df, "订单号", agg="nunique")
    assert r_nunique.grouped[0].value == 1.0


def test_include_blank_with_count() -> None:
    df = pd.DataFrame({"地区": ["华东", None, "华北"], "订单号": ["A1", "A2", "A3"]})
    result = analyze(df, "订单号", dimension="地区", agg="count", include_blank=True)
    labels = {g.label: g.value for g in result.grouped}
    assert labels == {"华东": 1.0, "（空）": 1.0, "华北": 1.0}


def test_id_column_excluded_from_statistics() -> None:
    """编号列不进入基础统计（总计/平均无业务意义）。"""
    df = pd.DataFrame({"订单号": ["1001", "1002", "1003"], "销售额": ["1", "2", "3"]})
    result = analyze(df, "销售额", agg="sum", exclude_cols=["订单号"])
    assert "订单号" not in result.statistics
    assert "销售额" in result.statistics


def test_numeric_dimension_label_no_decimal() -> None:
    """整数值维度标签不带 .0（Excel 显示习惯）。"""
    df = pd.DataFrame({"编号": [1, 2, 1], "销售额": ["10", "20", "30"]})
    result = analyze(df, "销售额", dimension="编号", agg="sum")
    assert [g.label for g in result.grouped] == ["1", "2"]


# ---------------------------------------------------------------- 排名


def test_rankings_top() -> None:
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    rankings = build_rankings(result, top_n=10)
    assert [r.label for r in rankings] == ["华北", "华东", "华南"]
    assert [r.rank for r in rankings] == [1, 2, 3]
    assert rankings[0].value == 700.0
    assert rankings[0].share == pytest.approx(700 / 1500)
    assert sum(r.share for r in rankings) == pytest.approx(1.0)


def test_rankings_bottom_and_limit() -> None:
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    bottom = build_rankings(result, top_n=2, bottom=True)
    # SALES 中华东 400 与华南 400 并列；升序取前 2（并列保持原顺序）
    assert [r.label for r in bottom] == ["华东", "华南"]
    assert [r.value for r in bottom] == [400.0, 400.0]
    assert len(bottom) == 2


def test_rankings_skip_none_groups() -> None:
    df = pd.DataFrame({"地区": ["华东", "华南"], "销售额": ["100", None]})
    result = analyze(df, "销售额", dimension="地区", agg="sum")
    rankings = build_rankings(result)
    assert [r.label for r in rankings] == ["华东"]  # 华南（None）被跳过


# ---------------------------------------------------------------- 趋势

TREND_DF = pd.DataFrame(
    {
        "日期": ["2024-01-05", "2024-01-20", "2024-02-10", "2024-03-05", "2024-04-12"],
        "销售额": ["100", "200", "300", "150", "450"],
    }
)


def test_trend_monthly_with_change() -> None:
    points = trend(TREND_DF, "销售额", "日期", granularity="month")
    assert [p.period for p in points] == ["2024-01", "2024-02", "2024-03", "2024-04"]
    assert [p.value for p in points] == [300.0, 300.0, 150.0, 450.0]
    # 环比：02 vs 01 = 0%；03 vs 02 = -50%；04 vs 03 = +200%
    assert points[0].change_pct is None  # 首期无可比
    assert points[1].change_pct == 0.0
    assert points[2].change_pct == -50.0
    assert points[3].change_pct == 200.0


def test_trend_quarterly() -> None:
    points = trend(TREND_DF, "销售额", "日期", granularity="quarter")
    assert [p.period for p in points] == ["2024-Q1", "2024-Q2"]
    assert points[0].value == 750.0
    assert points[1].change_pct is not None


def test_trend_weekly_labels() -> None:
    points = trend(TREND_DF, "销售额", "日期", granularity="week")
    assert points[0].period.startswith("2024-W")


def test_trend_empty_dates() -> None:
    df = pd.DataFrame({"日期": [None, None], "销售额": ["1", "2"]})
    points = trend(df, "销售额", "日期", granularity="month")
    assert points == []  # 无有效日期 → 空趋势


def test_trend_division_by_zero() -> None:
    df = pd.DataFrame({"日期": ["2024-01-05", "2024-02-05"], "销售额": ["0", "100"]})
    points = trend(df, "销售额", "日期", granularity="month")
    # 上期为 0 时环比为 None（不崩溃）
    assert points[0].change_pct is None
    assert points[1].change_pct is None


def test_trend_empty_period_no_crash() -> None:
    """某周期内指标全空：该点 value=None，环比链不断（回归：float(pd.NA)）。"""
    df = pd.DataFrame(
        {
            "日期": ["2024-01-05", "2024-02-05", "2024-03-05", "2024-03-20"],
            "销售额": ["100", None, "300", "150"],
        }
    )
    points = trend(df, "销售额", "日期", granularity="month")
    assert [p.period for p in points] == ["2024-01", "2024-02", "2024-03"]
    assert points[0].value == 100.0
    assert points[1].value is None  # 2 月全空
    assert points[2].value == 450.0
    # 环比链跳过空周期：3 月环比 = (450-100)/100 = 350%
    assert points[2].change_pct == 350.0


def test_trend_text_metric_no_crash() -> None:
    """指标为文本列：返回全空周期（value=None），不崩溃。"""
    df = pd.DataFrame({"日期": ["2024-01-05", "2024-02-05"], "销售额": ["正常", "加急"]})
    points = trend(df, "销售额", "日期", granularity="month")
    assert len(points) == 2
    assert all(p.value is None for p in points)


def test_trend_negative_base() -> None:
    """负值基期环比：数学正确（亏损收窄场景）。"""
    df = pd.DataFrame({"日期": ["2024-01-05", "2024-02-05"], "销售额": ["-100", "50"]})
    points = trend(df, "销售额", "日期", granularity="month")
    assert points[1].change_pct == -150.0


def test_trend_year_boundary_week_label() -> None:
    """跨年周标签：2024-12-30 归属 2025-W01（ISO 周）。"""
    df = pd.DataFrame({"日期": ["2024-12-30", "2025-01-01"], "销售额": ["1", "2"]})
    points = trend(df, "销售额", "日期", granularity="week")
    assert points[0].period == "2025-W01"
