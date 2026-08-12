"""AI 数字交叉校验单测：提取、上下文收集、识破编造数字。"""

from __future__ import annotations

from core.ai_validation import (
    collect_context_numbers,
    extract_numbers,
    validate_report_numbers,
)


def test_extract_numbers_variants() -> None:
    text = "总计 1,234.50 元，环比增长 -12.5%，2024 年共 5 期，占比 94.5%。"
    assert extract_numbers(text) == [1234.5, -12.5, 2024.0, 5.0, 94.5]


def test_extract_numbers_no_numbers() -> None:
    assert extract_numbers("没有任何数字") == []


def test_extract_numbers_date_string_not_negative() -> None:
    """日期/周期串不误提取为负数（回归：2024-01 → [-1] 误报）。"""
    assert extract_numbers("2024-01") == [2024.0]
    assert extract_numbers("2024-01-05") == [2024.0]
    assert 2024.0 in extract_numbers("2024-Q1 销售额")


def test_extract_numbers_unicode_minus() -> None:
    """Unicode 减号（U+2212）归一化后正常提取。"""
    assert extract_numbers("增长 −12.5%") == [-12.5]


def test_extract_numbers_scientific_notation_skipped() -> None:
    """科学计数法不匹配（当前策略：按独立数字提取，不视为整体）。"""
    assert extract_numbers("数值 1e5") == [1.0, 5.0]


def test_collect_context_numbers_with_shares() -> None:
    context = {
        "dataset": {"row_count": 100, "column_count": 5},
        "analysis": {"total": 2100.0, "grouped": [{"label": "a", "value": 1000.0, "share": 0.5}]},
    }
    nums = collect_context_numbers(context)
    assert 100 in nums
    assert 5 in nums
    assert 2100.0 in nums
    assert 0.5 in nums
    assert 50.0 in nums  # 占比 ×100 口径（报告可能写 50%）


def test_collect_context_large_value_not_amplified() -> None:
    """大数值（金额）不登记 ×100，防止放大幻觉被放行。"""
    context = {"analysis": {"total": 5321862.0}}
    nums = collect_context_numbers(context)
    assert 5321862.0 in nums
    assert 532186200.0 not in nums


def test_collect_context_string_period_numbers() -> None:
    """字符串（如周期 "2024-01"）中的数字也登记。"""
    context = {"trends": [{"period": "2024-01", "value": 300.0}]}
    nums = collect_context_numbers(context)
    assert 2024.0 in nums


def test_validate_all_numbers_traceable() -> None:
    """报告数字全部来自上下文 → 无问题（含真实周期格式）。"""
    context = {
        "dataset": {"row_count": 6, "column_count": 4},
        "analysis": {"total": 2100.0},
        "rankings": [{"rank": 1, "label": "华东", "value": 1000.0, "share": 0.476}],
        "trends": [{"period": "2024-01", "value": 300.0, "change_pct": 12.5}],
    }
    report = (
        "数据共 6 行 4 列，总销售额 2100 元。华东排名第一，销售额 1000，"
        "占比 47.6%。2024-01 月销售额 300，环比增长 12.5%。"
    )
    assert validate_report_numbers(report, context) == []


def test_validate_catches_fabricated_number() -> None:
    """编造数字必须被识破（防幻觉核心用例）。"""
    context = {
        "dataset": {"row_count": 100, "column_count": 5},
        "analysis": {"total": 5321862.0},
    }
    report = "总销售额为 99999999 元，较上期增长 88.8%。"
    problems = validate_report_numbers(report, context)
    assert "99999999" in problems  # 编造的销售额（返回原文）
    assert "88.8" in problems  # 编造的增长率


def test_validate_catches_amplified_amount() -> None:
    """金额放大 100 倍必须被识破（回归：×100 放行缺陷）。"""
    context = {"analysis": {"total": 5321862.0}}
    problems = validate_report_numbers("总销售额为 532186200 元", context)
    assert "532186200" in problems


def test_validate_reports_percentage_share_ok() -> None:
    """报告以百分比书写占比（0.476 → 47.6%）不误报。"""
    context = {"rankings": [{"value": 1000.0, "share": 0.476}]}
    report = "该分类占比 47.6%，数值为 1000。"
    assert validate_report_numbers(report, context) == []


def test_validate_tolerance() -> None:
    context = {"analysis": {"total": 100.0}}
    # 精度差异（100.000001）在容差内 → 可溯源
    assert validate_report_numbers("总计 100.000001", context) == []
    # 大数四舍五入显示（267610.23 → 267610）在相对容差内 → 可溯源
    assert validate_report_numbers("总计 267610", {"analysis": {"total": 267610.23}}) == []
    # 超出相对容差（101 vs 100 = 1%）→ 报错
    assert validate_report_numbers("总计 101", context) == ["101"]


def test_validate_deduplicates_problems() -> None:
    context = {"analysis": {"total": 100.0}}
    problems = validate_report_numbers("金额 999 与 999 都编造", context)
    assert problems == ["999"]  # 去重保序


def test_validate_empty_report() -> None:
    assert validate_report_numbers("", {"analysis": {"total": 100.0}}) == []
