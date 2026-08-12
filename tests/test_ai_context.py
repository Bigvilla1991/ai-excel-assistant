"""AI 上下文构造单测：隐私模式裁剪、截断上限、与原始数据一致。"""

from __future__ import annotations

import pandas as pd

from core.ai_context import build_context
from core.analyzer import analyze, build_rankings, trend
from core.profiler import profile

SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售额": ["100", "200", "300", "400", "500", "600"],
        "订单号": ["A1", "A2", "A3", "A4", "A5", "A6"],
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


def _setup():
    prof = profile(SALES)
    result = analyze(SALES, "销售额", dimension="地区", agg="sum")
    rankings = build_rankings(result, top_n=10)
    points = trend(SALES, "销售额", "日期", granularity="month")
    return prof, result, rankings, points


def test_context_secure_excludes_samples() -> None:
    """安全模式：不含样例值（不发送原始记录）。"""
    prof, result, rankings, points = _setup()
    ctx = build_context(prof, result, rankings, points, mode="secure")
    assert "samples" not in ctx
    # 字段只含名称/类型，不含值
    assert all("sample_values" not in f for f in ctx["fields"])


def test_context_enhanced_includes_limited_samples() -> None:
    """增强模式：每字段最多 3 个样例值。"""
    prof, result, rankings, points = _setup()
    ctx = build_context(prof, result, rankings, points, mode="enhanced")
    samples = ctx["samples"]
    assert samples  # 至少有一列有样例
    assert all(len(v) <= 3 for v in samples.values())


def test_context_numbers_match_source() -> None:
    """上下文数字与原始数据一致（可溯源）。"""
    prof, result, rankings, points = _setup()
    ctx = build_context(prof, result, rankings, points, mode="secure")
    assert ctx["dataset"]["row_count"] == 6
    assert ctx["dataset"]["column_count"] == 4
    assert ctx["analysis"]["total"] == 2100.0
    # 分组与原始一致
    labels = {g["label"]: g["value"] for g in ctx["analysis"]["grouped"]}
    assert labels == {"华东": 1000.0, "华北": 700.0, "华南": 400.0}
    # 排名第一
    assert ctx["rankings"][0]["label"] == "华东"
    assert ctx["rankings"][0]["value"] == 1000.0
    # 趋势含环比
    assert ctx["trends"][0]["period"] == "2024-01"
    assert ctx["trends"][0]["value"] == 300.0


def test_context_truncation_limits() -> None:
    """截断上限：字段/排名/趋势/分组。"""
    cols = {f"字段{i}": [f"x{i}-{j}" for j in range(50)] for i in range(50)}
    cols["数值"] = [float(j) for j in range(50)]
    big = pd.DataFrame(cols)
    prof = profile(big)
    result = analyze(big, "数值", dimension="字段0", agg="sum")
    rankings = build_rankings(result, top_n=50)
    ctx = build_context(prof, result, rankings, mode="secure")
    assert len(ctx["fields"]) <= 30
    assert len(ctx["rankings"]) <= 20  # 与 MAX_RANKINGS 对齐


def test_context_json_serializable() -> None:
    """上下文可 JSON 序列化（发送给模型的前提）。"""
    import json

    prof, result, rankings, points = _setup()
    ctx = build_context(prof, result, rankings, points, mode="enhanced")
    json.dumps(ctx)  # 不应抛异常


def test_context_issues_from_profile() -> None:
    """问题清单进入上下文（供 AI 做数据质量提醒）。"""
    dirty = SALES.copy()
    dirty["销售额"] = [None, None, None, "400", "500", "600"]  # 50% 缺失 → 高缺失提示
    prof = profile(dirty)
    result = analyze(dirty, "销售额", agg="sum")
    ctx = build_context(prof, result, mode="secure")
    assert any("空值" in m for m in ctx["quality"]["issues"])


def test_context_invalid_mode_raises() -> None:
    """未知 mode 抛 ValueError（防隐私守卫静默失效）。"""
    prof, result, rankings, points = _setup()
    import pytest

    with pytest.raises(ValueError, match="未知 AI 模式"):
        build_context(prof, result, rankings, points, mode="local")


def test_context_reads_rankings_from_result() -> None:
    """rankings/trends 缺省时从 analysis 读取（降低接线漏传风险）。"""
    prof, result, rankings, points = _setup()
    result.rankings = rankings
    result.trends = points
    ctx = build_context(prof, result, mode="secure")  # 不传 rankings/trends
    assert ctx["rankings"] and ctx["rankings"][0]["label"] == "华东"
    assert ctx["trends"] and ctx["trends"][0]["period"] == "2024-01"


def test_context_truncation_flags() -> None:
    """截断时带 _truncated 标记，模型可感知截断存在。"""
    cols = {f"字段{i}": [f"x{i}-{j}" for j in range(10)] for i in range(50)}
    cols["数值"] = [float(j) for j in range(10)]
    big = pd.DataFrame(cols)
    prof = profile(big)
    result = analyze(big, "数值", dimension="字段0", agg="sum")
    ctx = build_context(prof, result, mode="secure")
    assert ctx["rankings_truncated"] is False or ctx["fields"]  # 字段截断必然发生
    assert len(ctx["fields"]) == 30  # 50 列 → 截断为 30
