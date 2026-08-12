"""类型化模型（Pydantic v2）。

约定（见方案 §15.3）：
- 输入输出可序列化，便于测试与导出；
- 模块间只通过模型传递结果，不使用裸 dict；
- 数字字段按业务语义设约束（如占比 0~1），防非法值向下游扩散。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 字段类型（inferred_type）
TypeName = Literal["text", "int", "float", "bool", "date", "category", "id"]

# 问题严重级别与类别（UI 分级展示 + 评分口径）
Severity = Literal["error", "warning", "info"]
IssueCategory = Literal[
    "missing", "duplicate", "type", "date", "anomaly", "constant", "blank", "limit"
]


# ---------------------------------------------------------------- 数据体检


class ColumnProfile(BaseModel):
    """单列体检结果。"""

    name: str
    inferred_type: TypeName
    unique_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    null_rate: float = Field(ge=0, le=1)
    anomaly_count: int = Field(default=0, ge=0)  # IQR 异常值数量（仅数值列）
    is_constant: bool = False
    is_id_like: bool = False  # 疑似编号列，不应参与数值聚合
    high_missing: bool = False  # 空值率 ≥ 50%
    type_conflict: bool = False  # 混合类型，解析失败样本 > 5%
    date_issues: int = Field(default=0, ge=0)  # 日期列中无法解析的数量
    sample_values: list[str] = Field(default_factory=list)  # 前 5 个非空样例（展示用）


class IssueItem(BaseModel):
    """问题清单条目（可读中文 + 机器分类）。"""

    severity: Severity
    category: IssueCategory
    message: str = Field(min_length=1)
    columns: list[str] = Field(default_factory=list)


class ProfileResult(BaseModel):
    """DataProfiler 输出（见方案 §9）。"""

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    null_cells: int = Field(ge=0)
    null_rate_total: float = Field(ge=0, le=1)
    duplicate_rows: int = Field(ge=0)
    blank_rows: int = Field(ge=0)
    blank_columns: list[str] = Field(default_factory=list)
    columns: list[ColumnProfile] = Field(default_factory=list)
    health_score: int = Field(ge=0, le=100)
    issues: list[IssueItem] = Field(default_factory=list)


# ---------------------------------------------------------------- 数据清洗（Day 5）


class CleaningAction(BaseModel):
    """单条清洗动作记录。"""

    action: str  # 动作名：去重 / 去空白行 / 统一日期 …
    columns: list[str] = Field(default_factory=list)
    rows_affected: int = Field(default=0, ge=0)
    cells_affected: int = Field(default=0, ge=0)
    description: str  # 可读说明


class CleaningLog(BaseModel):
    """清洗日志（见方案 §10.4）。"""

    actions: list[CleaningAction] = Field(default_factory=list)
    rows_before: int = Field(default=0, ge=0)
    rows_after: int = Field(default=0, ge=0)
    executed_at: datetime | None = None


class CleaningPlan(BaseModel):
    """清洗计划（build_plan 输出）：用户确认后由 apply_plan 执行。

    actions 中的 rows_affected / cells_affected 为**预估**值，
    执行后以 CleaningLog 的实际值（apply_plan 重新统计）为准。
    """

    actions: list[CleaningAction] = Field(default_factory=list)
    rows_before: int = Field(default=0, ge=0)
    fill_strategies: dict[str, str] = Field(default_factory=dict)  # 列名 → 缺失值策略


# ---------------------------------------------------------------- 分析（Day 6-7 细化）


class RankItem(BaseModel):
    """排名条目。"""

    label: str
    value: float
    share: float = Field(ge=0, le=1)  # 占总计比例
    rank: int = Field(ge=1)


class TrendPoint(BaseModel):
    """趋势点：周期、数值、环比变化（无可比期时为 None）。"""

    period: str
    value: float
    change_pct: float | None = None  # 相对上一周期变化（%），跨期不可比时为 None


# 聚合方式与时间粒度（Literal 约束，防止拼写错误静默扩散）
AggType = Literal["sum", "mean", "count", "nunique"]
Granularity = Literal["day", "week", "month", "quarter"]


class AnalysisResult(BaseModel):
    """DataAnalyzer 输出（见方案 §15.2，字段随 Day 6-7 细化）。

    原则：图表与汇总表共用同一份结果，导出数字可追溯。
    """

    metric: str
    dimension: str | None = None
    agg: AggType = "sum"
    granularity: Granularity | None = None
    overview: dict[str, float | int | str] = Field(default_factory=dict)
    statistics: dict[str, dict[str, float]] = Field(default_factory=dict)
    rankings: list[RankItem] = Field(default_factory=list)
    trends: list[TrendPoint] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    charts: list[dict] = Field(default_factory=list)  # 图表配置（Day 7）
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- AI 报告（Day 8-9 细化）


class AIReport(BaseModel):
    """AI 固定结构报告（见方案 §12.2），字段随 Day 8-9 细化。"""

    overview: str = ""  # 数据概况
    findings: list[str] = Field(default_factory=list)  # 核心发现
    trends: list[str] = Field(default_factory=list)  # 趋势变化
    anomalies: list[str] = Field(default_factory=list)  # 异常情况
    causes: list[str] = Field(default_factory=list)  # 可能原因（推断）
    recommendations: list[str] = Field(default_factory=list)  # 建议关注事项
    quality_notes: list[str] = Field(default_factory=list)  # 数据质量提醒
    generated_at: datetime = Field(default_factory=datetime.now)
    source: Literal["ai", "template"] = "ai"  # 模板回退时为 template
