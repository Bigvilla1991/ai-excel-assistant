"""AI 上下文构造（见方案 §12.1）：最小必要信息 + 隐私模式裁剪 + 截断上限。

安全约定（§13.1）：
- 本地模式：不构造 AI 上下文（使用模板报告）；
- 安全 AI 模式（默认）：仅字段名、类型、汇总统计、趋势与异常摘要，**不含样例值**；
- 增强 AI 模式：经用户明确同意后，附加每字段少量（≤3 个）样例值。
"""

from __future__ import annotations

from typing import Literal

from models.schemas import AnalysisResult, ProfileResult, RankItem, TrendPoint

# 截断上限（防上下文膨胀，控制 token 成本；与页面展示上限对齐）
MAX_FIELDS = 30  # 字段数
MAX_RANKINGS = 20  # 排名条数（对齐页面 top_n 上限）
MAX_TREND_POINTS = 31  # 趋势点数（对齐日粒度最多 31 天）
MAX_ISSUES = 10  # 问题条数
MAX_GROUPED = 20  # 分组条目
MAX_SAMPLES = 3  # 增强模式：每字段样例值数

ContextMode = Literal["secure", "enhanced"]


def build_context(
    profile: ProfileResult,
    analysis: AnalysisResult,
    rankings: list[RankItem] | None = None,
    trends: list[TrendPoint] | None = None,
    mode: ContextMode = "secure",
) -> dict:
    """构造发送给模型的最小必要上下文（可 JSON 序列化）。

    mode：secure（默认）/ enhanced；未知值抛 ValueError（防隐私守卫静默失效）。
    本地模式请直接走模板报告，不调用本函数。
    rankings/trends 缺省时从 analysis 读取（页面已写回）。
    """
    if mode not in ("secure", "enhanced"):
        raise ValueError(f"未知 AI 模式: {mode}（仅支持 secure/enhanced）")

    rank_items = rankings if rankings is not None else analysis.rankings
    trend_items = trends if trends is not None else analysis.trends

    ctx: dict = {
        "dataset": {
            "row_count": profile.row_count,
            "column_count": profile.column_count,
        },
        "quality": {
            "health_score": profile.health_score,
            "missing_cells": profile.null_cells,
            "duplicate_rows": profile.duplicate_rows,
            "issues": [i.message for i in profile.issues[:MAX_ISSUES]],
        },
        "fields": [
            {"name": c.name, "type": c.inferred_type, "is_id": c.is_id_like}
            for c in profile.columns[:MAX_FIELDS]
        ],
        "analysis": {
            "metric": analysis.metric,
            "dimension": analysis.dimension,
            "agg": analysis.agg,
            "total": analysis.overview.get("指标合计"),
            "grouped": [
                {"label": g.label, "value": g.value, "share": g.share}
                for g in analysis.grouped[:MAX_GROUPED]
            ],
            "grouped_truncated": len(analysis.grouped) > MAX_GROUPED,
        },
        "rankings": [
            {"rank": r.rank, "label": r.label, "value": r.value, "share": r.share}
            for r in rank_items[:MAX_RANKINGS]
        ],
        "rankings_truncated": len(rank_items) > MAX_RANKINGS,
        "trends": [
            {"period": t.period, "value": t.value, "change_pct": t.change_pct}
            for t in trend_items[:MAX_TREND_POINTS]
        ],
        "trends_truncated": len(trend_items) > MAX_TREND_POINTS,
        "anomalies": [i.message for i in profile.issues if i.category == "anomaly"][:MAX_ISSUES],
    }

    if mode == "enhanced":
        # 增强模式：附加每字段少量样例值（脱敏由用户确认后提供）
        ctx["samples"] = {
            c.name: c.sample_values[:MAX_SAMPLES]
            for c in profile.columns[:MAX_FIELDS]
            if c.sample_values
        }
    return ctx
