"""DataProfiler：数据体检（见方案 §9）。

职责：
- 统计行列数、空值、重复行、空白行列；
- 字段类型推断（含疑似编号列识别）；
- IQR 异常值检测、日期问题检测；
- 生成健康评分与问题清单。

约束：
- 不修改传入 DataFrame（只读）；
- 类型推断基于 dtype=str 读入的原始文本（见 excel_reader 设计决策）。
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from models.schemas import (
    ColumnProfile,
    IssueItem,
    ProfileResult,
    TypeName,
)
from utils.data_utils import clean_frame, clean_series, normalize_cn_dates

# 疑似编号列名关键词（命中即标记 is_id_like，不参与数值聚合）。
# 用完整词组避免单字"号"误伤（符号/绰号）；id 用词边界防误匹配（valid/aid）
_ID_NAME_PATTERN = re.compile(
    r"(序号|单号|编号|货号|型号|账号|卡号|证件号|身份证|手机号|电话|流水|code|(?<![a-z0-9])id(?![a-z0-9]))",
    re.IGNORECASE,
)

# 编号值编码风格：字母/数字/分隔符组成，无中文与空格（避免把文本备注误判为编号）
_ENCODING_PATTERN = re.compile(r"^[A-Za-z0-9_\-./:#]+$")

# 日期候选正则：2024/1/5、2024-01-05、2024年2月1日、2024年2月、20240108
_DATE_PATTERN = re.compile(r"^\d{4}[-/年]\d{1,2}([-/月]\d{1,2}(日)?)?$|^\d{4}年\d{1,2}月$|^\d{8}$")

_HIGH_MISSING_RATE = 0.5  # 高缺失列阈值
_DATE_CANDIDATE_RATIO = 0.8  # 日期候选格式占比达到该值才尝试解析
_CONSTANT_UNIQUE_LIMIT = 1  # 常量列：非空唯一值数上限
_CATEGORY_UNIQUE_LIMIT = 30  # 分类列：唯一值数上限
_CATEGORY_UNIQUE_RATIO = 0.05  # 分类列：唯一值占比上限
_CATEGORY_UNIQUE_ABSOLUTE = 500  # 分类列：唯一值数硬上限（按占比判定时）
_SAMPLE_VALUES_LIMIT = 5
_SAMPLE_VALUE_MAX_LEN = 80


def _parse_numeric(series: pd.Series) -> tuple[pd.Series, int]:
    """数值解析：返回 (数值序列, 成功数)。"""
    nums = pd.to_numeric(series, errors="coerce")
    return nums, int(nums.notna().sum())


def _is_bool_text(series: pd.Series) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return False
    lowered = non_null.str.lower()
    return lowered.isin({"true", "false"}).all()


def _parse_dates(series: pd.Series) -> tuple[pd.Series, int]:
    """日期解析（仅对匹配日期候选格式的行），返回 (datetime 序列, 成功数)。

    中文格式（2024年2月1日 / 2024年2月）先归一化为 ISO 短格式再解析。
    """
    non_null = series.dropna()
    candidates = non_null[non_null.str.match(_DATE_PATTERN)]
    normalized = normalize_cn_dates(candidates)
    # pandas 3.0 起 to_datetime 不再自动推断混合格式，需显式指定
    parsed = pd.to_datetime(normalized, errors="coerce", format="mixed")
    return parsed, int(parsed.notna().sum())


def _iqr_anomaly_count(nums: pd.Series) -> int:
    """IQR 法异常值计数（见方案 §9.3），仅提示不删除。"""
    clean = nums.dropna()
    if len(clean) < 5:
        return 0
    q1, q3 = clean.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr <= 0 or np.isnan(iqr):
        return 0
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((clean < lower) | (clean > upper)).sum())


def _infer_type(
    series: pd.Series, non_null: pd.Series, name: str
) -> tuple[TypeName, dict[str, Any]]:
    """类型推断（优先级：空列→常量→日期→数值→布尔→编号→分类→文本）。"""
    info: dict[str, Any] = {
        "type_conflict": False,
        "date_issues": 0,
        "anomaly_count": 0,
    }
    total = int(non_null.notna().sum())
    if non_null.empty:
        return "text", info
    if non_null.nunique() <= _CONSTANT_UNIQUE_LIMIT:
        return "category", info  # 常量列由 is_constant 标记，类型归 category

    # 日期：候选格式占比足够才尝试解析
    date_mask = non_null.str.match(_DATE_PATTERN)
    if date_mask.mean() >= _DATE_CANDIDATE_RATIO:
        parsed, ok = _parse_dates(series)
        candidates_total = int(date_mask.sum())
        if ok / total >= 0.5:
            # date_issues 只统计候选格式内的解析失败，避免混入非日期文本值
            info["date_issues"] = candidates_total - ok
            info["type_conflict"] = ok / total < 0.95
            return "date", info
        # 候选格式占比高但解析成功率低（如全列 2024-99-99）：
        # 仍是日期列，全部计入问题，不得静默降级为文本
        info["date_issues"] = total
        info["type_conflict"] = True
        return "date", info

    # 数值
    nums, ok = _parse_numeric(series)
    if ok / total >= 0.95:
        # 名称含编号关键词：即使全为数字也不按数值处理（如证件号）
        if _ID_NAME_PATTERN.search(name):
            info["is_id_like"] = True
            return "id", info
        is_integral = bool((nums.dropna() % 1 == 0).all())
        if is_integral:
            info["anomaly_count"] = _iqr_anomaly_count(nums)
            return "int", info
        info["anomaly_count"] = _iqr_anomaly_count(nums)
        return "float", info
    if ok / total >= 0.5:
        info["type_conflict"] = True
        info["anomaly_count"] = _iqr_anomaly_count(nums)
        return "float", info

    # 布尔
    if _is_bool_text(series):
        return "bool", info

    # 编号列：名称关键词 或 全唯一 + 编码风格（无中文/空格，排除 URL）
    unique_count = int(non_null.nunique())
    not_url = ~non_null.str.contains("://", regex=False)
    encoding_ratio = float((non_null.str.match(_ENCODING_PATTERN) & not_url).mean())
    all_unique_encoded = unique_count == total and total >= 10 and encoding_ratio >= 0.9
    if _ID_NAME_PATTERN.search(name) or all_unique_encoded:
        info["is_id_like"] = True
        return "id", info

    # 分类 / 文本
    if unique_count <= _CATEGORY_UNIQUE_LIMIT or (
        unique_count / total <= _CATEGORY_UNIQUE_RATIO and unique_count <= _CATEGORY_UNIQUE_ABSOLUTE
    ):
        return "category", info
    return "text", info


def profile(df: pd.DataFrame) -> ProfileResult:
    """对 DataFrame 做数据体检，返回 ProfileResult。不修改 df。"""
    row_count, column_count = df.shape
    columns: list[ColumnProfile] = []
    null_cells = 0
    blank_rows = 0

    for name in df.columns:
        raw = df[name]
        series = clean_series(raw)
        null_count = int(series.isna().sum())
        null_cells += null_count
        null_rate = null_count / row_count if row_count else 0.0
        non_null = series.dropna()
        unique_count = int(non_null.nunique()) if not non_null.empty else 0

        inferred, info = _infer_type(series, non_null, str(name))

        is_blank_col = non_null.empty
        sample_values = [
            str(v)[:_SAMPLE_VALUE_MAX_LEN] for v in non_null.head(_SAMPLE_VALUES_LIMIT)
        ]

        columns.append(
            ColumnProfile(
                name=str(name),
                inferred_type=inferred,
                unique_count=unique_count,
                null_count=null_count,
                null_rate=round(null_rate, 4),
                anomaly_count=info["anomaly_count"],
                is_constant=not is_blank_col and unique_count <= _CONSTANT_UNIQUE_LIMIT,
                is_id_like=bool(info.get("is_id_like", False)),
                high_missing=null_rate >= _HIGH_MISSING_RATE,
                type_conflict=info["type_conflict"],
                date_issues=info["date_issues"],
                sample_values=sample_values,
            )
        )

    # 空白行：整行全空（含空字符串；"" 归一为缺失后判断）
    blank_rows = 0
    if row_count:
        cleaned = clean_frame(df)
        blank_rows = int(cleaned.isna().all(axis=1).sum())
    blank_cols = [c.name for c in columns if c.null_count == row_count and row_count > 0]

    # 重复行
    duplicate_rows = 0
    if row_count:
        dup_mask = df.duplicated(keep="first")
        duplicate_rows = int(dup_mask.sum())

    issues = _build_issues(df, columns, row_count, duplicate_rows, blank_rows, blank_cols)
    score = _health_score(columns, row_count, duplicate_rows, blank_rows)

    return ProfileResult(
        row_count=row_count,
        column_count=column_count,
        null_cells=null_cells,
        null_rate_total=round(null_cells / (row_count * column_count), 4)
        if row_count * column_count
        else 0.0,
        duplicate_rows=duplicate_rows,
        blank_rows=blank_rows,
        blank_columns=blank_cols,
        columns=columns,
        health_score=score,
        issues=issues,
    )


def _build_issues(
    df: pd.DataFrame,
    columns: list[ColumnProfile],
    row_count: int,
    duplicate_rows: int,
    blank_rows: int,
    blank_cols: list[str],
) -> list[IssueItem]:
    """生成问题清单（可读中文，UI 直接展示）。"""
    issues: list[IssueItem] = []

    if blank_rows:
        issues.append(
            IssueItem(
                severity="warning",
                category="blank",
                message=f"发现 {blank_rows} 行完全空白行，建议删除。",
            )
        )
    if blank_cols:
        issues.append(
            IssueItem(
                severity="warning",
                category="blank",
                message=f"发现 {len(blank_cols)} 列完全空白列：{'、'.join(blank_cols)}，建议删除。",
                columns=blank_cols,
            )
        )
    if duplicate_rows:
        severity = "error" if duplicate_rows / row_count > 0.05 else "warning"
        issues.append(
            IssueItem(
                severity=severity,
                category="duplicate",
                message=f"发现 {duplicate_rows} 行完整重复记录，建议去重。",
            )
        )

    for col in columns:
        # 全空列（100%）已由空白列提示覆盖，不重复提示缺失；
        # 非全空的高缺失列（含常量但缺失严重）正常提示
        if col.high_missing and (not col.is_constant or col.null_rate < 1.0):
            severity = "error" if col.null_rate >= 0.9 else "warning"
            issues.append(
                IssueItem(
                    severity=severity,
                    category="missing",
                    message=f"字段「{col.name}」空值率 {col.null_rate:.0%}，缺失严重。",
                    columns=[col.name],
                )
            )
        if col.type_conflict:
            issues.append(
                IssueItem(
                    severity="warning",
                    category="type",
                    message=f"字段「{col.name}」疑似混合类型，部分值无法按推断类型解析。",
                    columns=[col.name],
                )
            )
        if col.date_issues:
            issues.append(
                IssueItem(
                    severity="error",
                    category="date",
                    message=f"字段「{col.name}」有 {col.date_issues} 个日期无法解析或格式异常。",
                    columns=[col.name],
                )
            )
        if col.anomaly_count:
            issues.append(
                IssueItem(
                    severity="warning",
                    category="anomaly",
                    message=f"字段「{col.name}」检测到 {col.anomaly_count} 个疑似异常值（IQR 法），"
                    f"仅提示不删除，请人工确认。",
                    columns=[col.name],
                )
            )
        if col.is_constant:
            issues.append(
                IssueItem(
                    severity="info",
                    category="constant",
                    message=f"字段「{col.name}」为常量列（唯一值 {col.unique_count} 个），"
                    f"对分析无区分度。",
                    columns=[col.name],
                )
            )

    return issues


def _health_score(
    columns: list[ColumnProfile],
    row_count: int,
    duplicate_rows: int,
    blank_rows: int,
) -> int:
    """健康评分（0~100）。扣分表见实施计划 §3，写死为常量口径，单测锁定。

    口径补充：
    - 重复扣分 = 固定 5 分 + 占比每 1% × 0.5（叠加，与文档字面一致）；
    - 空白列走"高缺失"扣分（100% 空 → 50 分），固定 3 分仅针对空白行；
    - 最终取整用四舍五入（int(x+0.5)），避免 round() 银行家舍入。
    """
    score = 100.0

    # 1. 高缺失列：每 1% 空值率扣 0.5 分（空白列 100% 缺失由此覆盖）
    for col in columns:
        if col.high_missing:
            score -= int(col.null_rate * 100 + 0.5) * 0.5

    # 2. 重复记录：固定 5 分 + 占比每 1% 扣 0.5 分（叠加）
    if duplicate_rows and row_count:
        dup_pct = duplicate_rows / row_count * 100
        score -= 5.0 + dup_pct * 0.5

    # 3. 类型冲突列：5 分/列
    score -= 5.0 * sum(1 for c in columns if c.type_conflict)

    # 4. 日期异常列：5 分/列
    score -= 5.0 * sum(1 for c in columns if c.date_issues > 0)

    # 5. 常量列：3 分/列（空白列不重复计——已是高缺失）
    score -= 3.0 * sum(1 for c in columns if c.is_constant and not c.high_missing)

    # 6. 空白行存在：固定 3 分（空白列已由缺失扣分覆盖）
    if blank_rows:
        score -= 3.0

    return max(0, min(100, int(score + 0.5)))
