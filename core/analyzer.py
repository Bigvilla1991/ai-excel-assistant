"""DataAnalyzer：基础统计、维度分组、排名与趋势（见方案 §11）。

口径约定（与 Excel 一致）：
- 指标列数值化（to_numeric），无法转换的值视为缺失，不参与求和/平均；
- sum/mean 忽略空值（等价 Excel SUM/AVERAGE 的 skipna 行为）；
- count = 组内行数；nunique = 组内指标去重数；
- 空维度默认排除（dropna=False 可选保留，页面提供勾选）；
- 趋势按时间周期汇总，环比 = (本期 - 上期) / 上期，无可比期/基期为 0 时为 None；
- 不修改传入 DataFrame。
"""

from __future__ import annotations

import pandas as pd

from models.schemas import (
    AggType,
    AnalysisResult,
    Granularity,
    GroupRow,
    RankItem,
    TrendPoint,
)
from utils.data_utils import clean_series, to_numeric


def _to_numeric(series: pd.Series) -> pd.Series:
    """指标列数值化（to_numeric 别名，语义聚焦）。"""
    return to_numeric(series)


def describe(
    df: pd.DataFrame,
    numeric_cols: list[str],
    exclude_cols: list[str] | None = None,
) -> dict[str, dict[str, float | None]]:
    """基础描述统计（见方案 §11.1），对指定数值列逐列计算。

    每列输出：数据量 / 总计 / 平均值 / 中位数 / 最小值 / 最大值 / 标准差 / 空值数量。
    exclude_cols：排除列（如疑似编号列，其总计/平均无业务意义）。
    """
    exclude = set(exclude_cols or [])
    out: dict[str, dict[str, float | None]] = {}
    for col in numeric_cols:
        if col not in df.columns or col in exclude:
            continue
        nums = _to_numeric(df[col])
        valid = nums.dropna()
        n = len(valid)
        stats: dict[str, float | None] = {
            "数据量": float(n),
            "总计": float(valid.sum()) if n else None,
            "平均值": float(valid.mean()) if n else None,
            "中位数": float(valid.median()) if n else None,
            "最小值": float(valid.min()) if n else None,
            "最大值": float(valid.max()) if n else None,
            "标准差": float(valid.std()) if n > 1 else None,
            "空值数量": float(int(nums.isna().sum())),
        }
        out[col] = stats
    return out


def analyze(
    df: pd.DataFrame,
    metric: str,
    dimension: str | None = None,
    agg: AggType = "sum",
    include_blank: bool = False,
    exclude_cols: list[str] | None = None,
) -> AnalysisResult:
    """维度分组汇总（等价 Excel 透视表），返回 AnalysisResult。

    include_blank=True 时保留空维度分组（label 为"（空）"）。
    指标列为文本类型时，只允许 count / nunique 聚合（页面层限制）。
    exclude_cols：排除列（疑似编号列不参与基础统计）。
    """
    if metric not in df.columns:
        raise ValueError(f"指标列「{metric}」不存在")
    if dimension is not None and dimension not in df.columns:
        raise ValueError(f"维度列「{dimension}」不存在")

    # ---- 分组 ----
    grouped: list[GroupRow] = []
    if dimension is None:
        grouped.append(GroupRow(label="全部", value=_aggregate_total(df, metric, agg)))
    else:
        dim = df[dimension].astype("string").str.strip().replace("", pd.NA)
        if agg in ("sum", "mean"):
            nums = _to_numeric(df[metric])
            table = pd.DataFrame({"dim": dim, "val": nums})
            if agg == "sum":
                # min_count=1：全空组返回 NaN（区分"值为 0"与"无有效值"）
                series = table.groupby("dim", dropna=not include_blank)["val"].sum(min_count=1)
            else:
                series = table.groupby("dim", dropna=not include_blank)["val"].mean()
        elif agg == "count":
            series = dim.groupby(dim, dropna=not include_blank).size()
        else:  # nunique
            series = df[metric].astype("string").groupby(dim, dropna=not include_blank).nunique()
        for label, value in series.items():
            label_str = "（空）" if pd.isna(label) else _format_group_label(label)
            grouped.append(GroupRow(label=label_str, value=_safe_float(value)))

    # ---- 占比（仅 sum 聚合有意义；mean/count 不填 share 防误导）----
    if agg == "sum":
        total = float(sum(g.value for g in grouped if g.value is not None))
        for g in grouped:
            g.share = g.value / total if g.value is not None and total else None

    # ---- 基础统计（仅数值列，排除编号列）----
    numeric_cols = detect_numeric_cols(df)
    statistics = describe(df, numeric_cols, exclude_cols=exclude_cols)

    overview: dict[str, float | int | str] = {
        "指标": metric,
        "维度": dimension or "全部",
        "聚合": agg,
        "总行数": int(len(df)),
        "指标合计": _safe_float(_aggregate_total(df, metric, agg)),
    }

    return AnalysisResult(
        metric=metric,
        dimension=dimension,
        agg=agg,
        overview=overview,
        statistics=statistics,
        grouped=grouped,
    )


def _safe_float(value: object) -> float | None:
    """数值转 float；NaN/NA 返回 None（防止 float(pd.NA) 崩溃）。"""
    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_group_label(label: object) -> str:
    """分组标签格式化：整数值不带 .0（Excel 显示习惯）。"""
    if isinstance(label, float) and label.is_integer():
        return str(int(label))
    return str(label)


def _aggregate_total(df: pd.DataFrame, metric: str, agg: AggType) -> float | None:
    """总体聚合（无分组时）；全空时返回 None。"""
    if agg == "count":
        return float(len(df))
    if agg == "nunique":
        return float(df[metric].astype("string").nunique())
    nums = _to_numeric(df[metric])
    if not nums.notna().any():
        return None
    if agg == "mean":
        return float(nums.mean())
    return float(nums.sum())


def detect_numeric_cols(df: pd.DataFrame) -> list[str]:
    """数值列探测：整列可转数值且非全空（轻量，供 describe 用）。"""
    cols: list[str] = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(str(col))
            continue
        if df[col].dtype != "string" and df[col].dtype != "object":
            continue
        nums = pd.to_numeric(clean_series(df[col]), errors="coerce")
        if nums.notna().mean() >= 0.95 and nums.notna().any():
            cols.append(str(col))
    return cols


# ---------------------------------------------------------------- 排名（§11.3）


def build_rankings(result: AnalysisResult, top_n: int = 10, bottom: bool = False) -> list[RankItem]:
    """从分组结果生成 TOP / BOTTOM 排名（与分组表同一份数据源）。

    - 仅对 sum 聚合有意义（value 为 None 的组跳过）；
    - rank 从 1 开始，share 为该组占总计比例。
    """
    items = [g for g in result.grouped if g.value is not None]
    items.sort(key=lambda g: g.value, reverse=not bottom)
    total = sum(g.value for g in items)
    rankings = [
        RankItem(
            label=g.label,
            value=g.value,
            share=g.value / total if total else 0.0,
            rank=i,
        )
        for i, g in enumerate(items[:top_n], start=1)
    ]
    return rankings


# ---------------------------------------------------------------- 趋势（§11.4）

_PERIOD_FREQ: dict[Granularity, str] = {
    "day": "D",
    "week": "W",
    "month": "M",
    "quarter": "Q",
}


def _period_label(period: pd.Period, granularity: Granularity) -> str:
    """周期标签（Excel 显示习惯）：2024-01、2024-W03、2024-Q1、2024-01-05。"""
    if granularity == "day":
        return period.strftime("%Y-%m-%d")
    if granularity == "month":
        return period.strftime("%Y-%m")
    if granularity == "week":
        return f"{period.year}-W{period.week:02d}"
    return f"{period.year}-Q{period.quarter}"


def trend(
    df: pd.DataFrame,
    metric: str,
    date_col: str,
    granularity: Granularity = "month",
) -> list[TrendPoint]:
    """按时间周期汇总趋势（见方案 §11.4），返回按时间升序的 TrendPoint。

    环比 = (本期 − 上期) / 上期 × 100；首期或基期为 0 时 change_pct 为 None。
    周期内指标全空时该点 value 为 None（不崩溃、不参与环比链）。
    """
    dates = pd.to_datetime(clean_series(df[date_col]), errors="coerce", format="mixed")
    nums = _to_numeric(df[metric])
    table = pd.DataFrame({"period": dates.dt.to_period(_PERIOD_FREQ[granularity]), "val": nums})
    grouped = table.groupby("period")["val"].sum(min_count=1)

    points: list[TrendPoint] = []
    prev: float | None = None
    for period, value in grouped.items():
        point_value = _safe_float(value)
        change: float | None = None
        if point_value is not None and prev is not None and prev != 0:
            change = round((point_value - prev) / prev * 100, 2)
        points.append(
            TrendPoint(
                period=_period_label(period, granularity),
                value=point_value,
                change_pct=change,
            )
        )
        if point_value is not None:
            prev = point_value  # prev 只跟踪有效值，NA 不沿环比链传播
    return points
