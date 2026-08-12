"""DataCleaner 单元测试：8 类动作、日志统计、原数据不变。"""

from __future__ import annotations

import pandas as pd

from core.cleaner import apply_plan, build_plan
from core.profiler import profile
from models.schemas import CleaningAction, CleaningPlan


def _df_with_issues() -> pd.DataFrame:
    """含空白行/列、空格、重复、金额、异常值的脏数据。

    第 5 行为第 4 行的完整副本（用于去重），末行为异常值行。
    """
    return pd.DataFrame(
        {
            "销售日期": [
                "2024/1/5",
                "2024-01-06",
                "2024年2月1日",
                "20240108",
                "20240108",
                "2024/3/3",
            ],
            "订单号": ["ORD-001", "ORD-002", "ORD-003", "ORD-004", "ORD-004", "ORD-005"],
            "地区": [" 华东 ", "华北", "华东", "华南", "华南", "西南"],
            "销售额": ["￥1,234.50", "567", "1,000", None, None, "999"],
            "数量": ["2", "5", "8", "12", "12", "999"],
            "备注": ["正常", "加急", "", "正常", "正常", "加急"],
        }
    )


def test_drop_blank_rows_and_columns() -> None:
    df = pd.DataFrame(
        {"姓名": ["张三", None, "李四"], "城市": ["北京", "", "上海"], "空列": [None, None, None]}
    )
    plan = CleaningPlan(
        actions=[
            CleaningAction(action="删除空白行", description="x"),
            CleaningAction(action="删除空白列", description="x"),
        ]
    )
    clean, log = apply_plan(df, plan)
    assert log.rows_before == 3
    assert log.rows_after == 2  # 空白行（第 2 行）被删
    assert "空列" not in clean.columns
    assert log.actions[0].rows_affected == 1


def test_strip_text() -> None:
    df = pd.DataFrame({"地区": [" 华东 ", "\x00华北 ", "华南"]})
    plan = CleaningPlan(actions=[CleaningAction(action="清理文本", description="x")])
    clean, log = apply_plan(df, plan)
    assert clean["地区"].tolist() == ["华东", "华北", "华南"]
    assert log.actions[0].cells_affected == 2  # 2 个单元格发生变化


def test_deduplicate() -> None:
    df = pd.DataFrame({"姓名": ["A", "A", "B"], "城市": ["x", "x", "y"]})
    plan = CleaningPlan(actions=[CleaningAction(action="删除重复行", description="x")])
    clean, log = apply_plan(df, plan)
    assert len(clean) == 2
    assert log.actions[0].rows_affected == 1


def test_normalize_amount() -> None:
    df = pd.DataFrame({"销售额": ["￥1,234.50", "567", "1,000", "无法转"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="金额归一化", columns=["销售额"], description="x")]
    )
    clean, log = apply_plan(df, plan)
    assert clean["销售额"].tolist()[:3] == [1234.5, 567.0, 1000.0]
    assert clean["销售额"].tolist()[3] == "无法转"  # 失败保留原样
    assert log.actions[0].cells_affected == 3


def test_parse_dates() -> None:
    df = pd.DataFrame({"日期": ["2024/1/5", "2024年2月1日", "20240108", "不是日期"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="统一日期", columns=["日期"], description="x")]
    )
    clean, log = apply_plan(df, plan)
    assert clean["日期"].iloc[0] == pd.Timestamp("2024-01-05")
    assert clean["日期"].iloc[1] == pd.Timestamp("2024-02-01")
    assert clean["日期"].iloc[3] == "不是日期"  # 失败保留原样
    assert log.actions[0].cells_affected == 3


def test_fill_missing_numeric_strategies() -> None:
    df = pd.DataFrame({"数值": ["1", None, "3"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["数值"], description="x")],
        fill_strategies={"数值": "填充 0"},
    )
    clean, log = apply_plan(df, plan)
    assert clean["数值"].tolist() == [1.0, 0.0, 3.0]
    assert log.actions[0].cells_affected == 1


def test_fill_missing_mean() -> None:
    df = pd.DataFrame({"数值": ["1", None, "3"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["数值"], description="x")],
        fill_strategies={"数值": "均值"},
    )
    clean, _ = apply_plan(df, plan)
    assert clean["数值"].tolist() == [1.0, 2.0, 3.0]


def test_fill_missing_mode_and_text() -> None:
    df = pd.DataFrame({"地区": ["华东", None, "华东"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["地区"], description="x")],
        fill_strategies={"地区": "众数"},
    )
    clean, _ = apply_plan(df, plan)
    assert clean["地区"].tolist() == ["华东", "华东", "华东"]

    df2 = pd.DataFrame({"备注": ["a", None, "b"]})
    plan2 = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["备注"], description="x")],
        fill_strategies={"备注": "未填写"},
    )
    clean2, _ = apply_plan(df2, plan2)
    assert clean2["备注"].tolist() == ["a", "未填写", "b"]


def test_fill_missing_drop_row() -> None:
    df = pd.DataFrame({"日期": ["2024/1/5", None, "2024/1/7"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["日期"], description="x")],
        fill_strategies={"日期": "删除该行"},
    )
    clean, log = apply_plan(df, plan)
    assert len(clean) == 2
    assert log.actions[0].rows_affected == 1


def test_drop_anomalies() -> None:
    df = pd.DataFrame({"数值": [str(i) for i in range(1, 101)] + ["10000", "20000"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="删除异常值", columns=["数值"], description="x")]
    )
    clean, log = apply_plan(df, plan)
    assert len(clean) == 100
    assert log.actions[0].rows_affected == 2


def test_apply_plan_does_not_modify_original() -> None:
    df = _df_with_issues()
    snapshot = df.copy(deep=True)
    plan = CleaningPlan(
        actions=[
            CleaningAction(action="清理文本", description="x"),
            CleaningAction(action="删除重复行", description="x"),
        ]
    )
    apply_plan(df, plan)
    pd.testing.assert_frame_equal(df, snapshot)


def test_full_plan_roundtrip() -> None:
    """build_plan → apply_plan 全链路：计划预估与执行一致。"""
    df = _df_with_issues()
    prof = profile(df)
    choices = {
        "drop_blank_rows": True,
        "drop_blank_columns": True,
        "strip_text": True,
        "deduplicate": True,
        "normalize_amount": ["销售额"],
        "parse_dates": ["销售日期"],
        "drop_anomalies": [],
        "fill_missing": {"备注": "未填写"},
    }
    plan = build_plan(prof, choices)
    assert len(plan.actions) == 7  # 空白行/列、清理、金额、日期、填充、去重
    assert plan.rows_before == 6

    clean, log = apply_plan(df, plan)
    assert log.rows_before == 6
    assert log.rows_after == 5  # 去重删除 1 行完整重复
    assert len(log.actions) == 7
    # 顺序：空白行 → 空白列 → 清理 → 金额 → 日期 → 填充 → 去重
    assert [a.action for a in log.actions] == [
        "删除空白行",
        "删除空白列",
        "清理文本",
        "金额归一化",
        "统一日期",
        "填充缺失值",
        "删除重复行",
    ]


def test_empty_plan_returns_copy() -> None:
    df = _df_with_issues()
    plan = CleaningPlan()
    clean, log = apply_plan(df, plan)
    assert len(log.actions) == 0
    assert len(clean) == len(df)


def test_fill_missing_keeps_unparsable_text() -> None:
    """数值填充不得静默改写非数值原文（如 "N/A"）。"""
    df = pd.DataFrame({"数值": ["1", "N/A", "3"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["数值"], description="x")],
        fill_strategies={"数值": "填充 0"},
    )
    clean, _ = apply_plan(df, plan)
    assert clean["数值"].tolist() == [1.0, "N/A", 3.0]  # N/A 保留原文


def test_fill_estimate_split_rows_vs_cells() -> None:
    """删除该行策略预估记行数，其余记单元格数。"""
    df = pd.DataFrame({"日期": ["2024/1/5", None, "2024/1/7"], "备注": ["a", None, "b"]})
    prof = profile(df)
    plan = build_plan(
        prof,
        {"fill_missing": {"日期": "删除该行", "备注": "未填写"}},
    )
    fill_action = [a for a in plan.actions if a.action == "填充缺失值"][0]
    assert fill_action.rows_affected == 1  # 日期缺失 1 行
    assert fill_action.cells_affected == 1  # 备注缺失 1 单元格


def test_estimate_amount_matches_execution() -> None:
    """金额/日期预估与执行一致（非空可转数口径）。"""
    df = pd.DataFrame(
        {
            "销售额": ["100", "200", None, "400"],
            "日期": ["2024/1/1", "2024-01-02", None, "2024-01-04"],
        }
    )
    prof = profile(df)
    plan = build_plan(
        prof,
        {"normalize_amount": ["销售额"], "parse_dates": ["日期"]},
    )
    _, log = apply_plan(df, plan)
    for planned, actual in zip(plan.actions, log.actions, strict=True):
        assert planned.cells_affected == actual.cells_affected


def test_drop_anomalies_small_sample_guard() -> None:
    """样本 <5 行时不删除任何行（IQR 守卫）。"""
    df = pd.DataFrame({"数值": ["1", "2", "3", "4"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="删除异常值", columns=["数值"], description="x")]
    )
    clean, log = apply_plan(df, plan)
    assert len(clean) == 4
    assert log.actions[0].rows_affected == 0
