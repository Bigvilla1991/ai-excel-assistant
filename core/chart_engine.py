"""ChartEngine：交互式图表生成（见方案 §8.5 / §11.5）。

规则：
- 图表标题必须说明指标与维度；坐标轴带单位与数字格式；
- 默认仅展示最有意义的前 10~20 类（分类截断）；
- 图表与底层汇总表使用同一份计算结果（result.grouped / rankings / trends）；
- 导出报告中的数字可追溯到分析结果。
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from models.schemas import AnalysisResult, RankItem, TrendPoint
from utils.data_utils import to_numeric

# 分类截断上限（§11.5）
MAX_CATEGORIES: int = 20
_SCATTER_SAMPLE_LIMIT: int = 2000

# 品牌样式（现代 SaaS 简洁风）
BRAND_COLORS: list[str] = [
    "#4F46E5",
    "#0EA5E9",
    "#10B981",
    "#F59E0B",
    "#EF4444",
    "#8B5CF6",
    "#14B8A6",
    "#F97316",
    "#6366F1",
    "#22C55E",
]
_FONT_FAMILY = '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
_GRID_COLOR = "#EEF2F7"


def _style(fig: go.Figure, height: int = 420) -> go.Figure:
    """统一图表样式：字体、网格、背景、圆角。"""
    fig.update_layout(
        font=dict(family=_FONT_FAMILY, size=12, color="#334155"),
        title_font=dict(size=15, color="#0F172A"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=height,
        margin=dict(l=40, r=20, t=60, b=40),
        hoverlabel=dict(bgcolor="#0F172A", font_color="#FFFFFF"),
    )
    fig.update_xaxes(
        gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, title_font=dict(color="#64748B")
    )
    fig.update_yaxes(
        gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, title_font=dict(color="#64748B")
    )
    return fig


def _bar_color() -> list[str]:
    """品牌色循环（按分类数量）。"""
    return BRAND_COLORS


def bar_chart(result: AnalysisResult, max_categories: int = MAX_CATEGORIES) -> go.Figure:
    """柱状图：维度分组结果（分类 + 数值）。

    先按值降序排序再截断，保证展示的是"最有意义"的前 N 类（§11.5）。
    """
    items = [g for g in result.grouped if g.value is not None]
    items.sort(key=lambda g: g.value, reverse=True)
    items = items[:max_categories]
    fig = go.Figure(
        go.Bar(
            x=[g.label for g in items],
            y=[g.value for g in items],
            text=[f"{g.value:,.0f}" for g in items],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,.2f}<extra></extra>",
            marker_color=_bar_color(),
        )
    )
    _style(fig)
    fig.update_layout(
        title=f"{result.metric} 按{result.dimension or '全部'}汇总",
        xaxis_title=result.dimension or "分类",
        yaxis_title=result.metric,
    )
    fig.update_xaxes(tickangle=-30)
    return fig


def hbar_ranking(rankings: list[RankItem], metric: str, bottom: bool = False) -> go.Figure:
    """横向条形图：TOP/BOTTOM 排名（§8.5 排名推荐图）。"""
    labels = [r.label for r in reversed(rankings)]
    values = [r.value for r in reversed(rankings)]
    shares = [r.share for r in reversed(rankings)]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            text=[f"{s:.1%}" for s in shares],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,.2f}（占比 %{text}）<extra></extra>",
            marker_color=_bar_color(),
        )
    )
    title_mode = "BOTTOM" if bottom else "TOP"
    _style(fig, height=60 + 34 * len(rankings))
    fig.update_layout(
        title=f"{metric} 排名（{title_mode} {len(rankings)}）",
        xaxis_title=metric,
        yaxis_title="",
        margin=dict(l=120, r=60, t=60, b=40),
    )
    return fig


def line_chart(trends: list[TrendPoint], metric: str, granularity: str = "") -> go.Figure:
    """折线图：时间趋势（含峰值/低点标记）。"""
    valid = [t for t in trends if t.value is not None]
    fig = go.Figure()
    if not valid:
        return fig  # 无有效数据 → 空图（调用方自行提示）

    periods = [t.period for t in valid]
    values = [t.value for t in valid]
    markers = []
    if values:
        peak_i = values.index(max(values))
        low_i = values.index(min(values))
        markers = [{"index": peak_i, "label": "峰值"}, {"index": low_i, "label": "低点"}]

    fig.add_trace(
        go.Scatter(
            x=periods,
            y=values,
            mode="lines+markers",
            hovertemplate="%{x}<br>%{y:,.2f}<extra></extra>",
            line=dict(color="#4F46E5", width=2.5),
            marker=dict(size=6, color="#4F46E5"),
        )
    )
    for m in markers:
        fig.add_annotation(
            x=periods[m["index"]],
            y=values[m["index"]],
            text=m["label"],
            showarrow=True,
            arrowhead=1,
            yshift=10,
            font=dict(size=11, color="crimson"),
        )
    _style(fig)
    fig.update_layout(
        title=f"{metric} 趋势（{granularity}）" if granularity else f"{metric} 趋势",
        xaxis_title="周期",
        yaxis_title=metric,
    )
    return fig


def scatter_chart(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """散点图：两个数值列（超采样上限时随机抽样，提示抽样）。"""
    x = to_numeric(df[x_col])
    y = to_numeric(df[y_col])
    mask = x.notna() & y.notna()
    xs, ys = x[mask], y[mask]
    if len(xs) > _SCATTER_SAMPLE_LIMIT:
        # 超采样上限时随机抽样（seed 固定保证可复现）
        idx = xs.sample(_SCATTER_SAMPLE_LIMIT, random_state=42).index
        xs, ys = xs.loc[idx], ys.loc[idx]

    fig = go.Figure(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(size=6, opacity=0.65, color="#4F46E5"),
            hovertemplate="%{x:,.2f}<br>%{y:,.2f}<extra></extra>",
        )
    )
    _style(fig)
    fig.update_layout(
        title=f"{x_col} × {y_col} 散点图",
        xaxis_title=x_col,
        yaxis_title=y_col,
    )
    return fig
