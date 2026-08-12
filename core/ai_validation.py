"""AI 报告数字交叉校验（防幻觉，方案 §12.3）。

机制：报告文本中出现的所有数字，必须能在 AI 上下文中溯源；
无法溯源的数字（原文）返回给调用方（UI 展示"请人工核对"），
或直接触发模板回退（由 AIEngine 决策）。
"""

from __future__ import annotations

import re
from typing import Any

# 匹配数字：整数/小数/千分位/负号（如 1,234.50、-12.5、2024）
_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
# 日期/周期串中的 "-MM(-DD)" 部分（2024-01、2024-01-05）：
# 剔除后半段，防止 "-01" 被当作负数；年份保留以便溯源
_DATE_SUFFIX_PATTERN = re.compile(r"(?<=\d{4})-(\d{1,2})(-\d{1,2})?")
# Unicode 减号（U+2212）归一化为 ASCII 负号
_UNICODE_MINUS = "\u2212"


def _normalize(text: str) -> str:
    """提取前归一化：Unicode 减号 → ASCII；日期段 -MM(-DD) → 空格。"""
    cleaned = text.replace(_UNICODE_MINUS, "-")
    return _DATE_SUFFIX_PATTERN.sub(" ", cleaned)


def extract_numbers(text: str) -> list[float]:
    """从文本中提取所有数字（千分位归一，保留小数）。

    日期/周期串（2024-01）只剔除 -MM(-DD) 段，防止 "-01" 被误提取为 -1.0。
    """
    out: list[float] = []
    for token in _NUMBER_PATTERN.findall(_normalize(text)):
        normalized = token.replace(",", "")
        try:
            out.append(float(normalized))
        except ValueError:
            continue
    return out


def collect_context_numbers(context: dict[str, Any]) -> set[float]:
    """收集上下文中所有数值（递归），含占比的 ×100 口径。

    - 占比/比率类数值（值域 (0,1)，如 share=0.476）同时登记 ×100（"47.6%"）；
    - 大数值（金额等）不登记 ×100，防止"金额放大 100 倍"的幻觉被放行；
    - 字符串（如周期 "2024-01"）中的数字也登记（与报告侧同一口径）。
    """
    numbers: set[float] = set()

    def register(n: float) -> None:
        rounded = round(n, 2)
        numbers.add(rounded)
        if 0 < n < 1:  # 占比/比率：允许百分比书写
            numbers.add(round(n * 100, 2))

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            register(float(value))
        elif isinstance(value, str):
            for n in extract_numbers(value):
                register(n)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(context)
    return numbers


def _within_tolerance(number: float, allowed: float, tolerance: float) -> bool:
    """匹配判定：绝对容差 + 相对容差（0.1%）。

    报告通常四舍五入显示（如 267610.23 显示为 267,610），
    纯绝对容差会对大数误报。
    """
    return abs(number - allowed) <= max(tolerance, abs(allowed) * 0.001)


def validate_report_numbers(
    report_text: str, context: dict[str, Any], tolerance: float = 0.01
) -> list[str]:
    """校验报告中的数字是否均可在上下文中溯源。

    返回无法溯源的数字**原文**列表（去重、保序）；空列表 = 全部可溯源。
    tolerance：绝对容差下限；大数另加 0.1% 相对容差（容忍四舍五入显示）。
    """
    allowed = collect_context_numbers(context)
    problems: list[str] = []
    seen: set[str] = set()

    for token in _NUMBER_PATTERN.findall(_normalize(report_text)):
        normalized = token.replace(",", "")
        try:
            number = float(normalized)
        except ValueError:
            continue
        if any(_within_tolerance(number, a, tolerance) for a in allowed):
            continue
        if token not in seen:
            seen.add(token)
            problems.append(token)
    return problems
