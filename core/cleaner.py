"""DataCleaner：数据清洗（见方案 §10）。

流程：build_plan（预览预估）→ 用户确认 → apply_plan（执行 + 实际日志）。
约束：
- 不修改传入 DataFrame（每一步在副本上操作，返回新 df）；
- 清洗动作全部可追溯：每个动作产生一条 CleaningAction（行/单元格影响数）；
- 原始数据由调用方保留（页面层），撤销 = 重新从 raw_df 构建。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from models.schemas import (
    CleaningAction,
    CleaningLog,
    CleaningPlan,
    ProfileResult,
)
from utils.data_utils import clean_frame, normalize_cn_dates

# 不可见字符（保留 \t \n \r）：Excel/CSV 粘贴常带入
_INVISIBLE_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 金额符号与千分位（￥ $ ¥ ￥，中文逗号）
_AMOUNT_PATTERN = re.compile(r"[￥$¥,，\s]")


# ---------------------------------------------------------------- 动作定义


def _drop_blank_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningAction]:
    cleaned = clean_frame(df)
    mask = cleaned.isna().all(axis=1)
    removed = int(mask.sum())
    new_df = df[~mask].reset_index(drop=True)
    action = CleaningAction(
        action="删除空白行",
        rows_affected=removed,
        description=f"删除完全空白行 {removed} 行。",
    )
    return new_df, action


def _drop_blank_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningAction]:
    cleaned = clean_frame(df)
    blank = cleaned.isna().all(axis=0)
    removed_cols = [str(c) for c in df.columns[blank]]
    new_df = df.loc[:, ~blank].reset_index(drop=True)
    action = CleaningAction(
        action="删除空白列",
        columns=removed_cols,
        description=f"删除完全空白列 {len(removed_cols)} 个：{'、'.join(removed_cols) or '无'}。",
    )
    return new_df, action


def _strip_text(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningAction]:
    changed_cells = 0
    for col in df.columns:
        series = df[col]
        if series.dtype != "string" and series.dtype != "object":
            continue
        stripped = (
            series.astype("string").str.strip().str.replace(_INVISIBLE_PATTERN, "", regex=True)
        )
        changed_cells += int((stripped != series.astype("string")).sum())
        df[col] = stripped
    action = CleaningAction(
        action="清理文本",
        description=f"去除全部文本列首尾空格与不可见字符，共影响 {changed_cells} 个单元格。",
        cells_affected=changed_cells,
    )
    return df, action


def _deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningAction]:
    dup_mask = df.duplicated(keep="first")
    removed = int(dup_mask.sum())
    new_df = df[~dup_mask].reset_index(drop=True)
    action = CleaningAction(
        action="删除重复行",
        rows_affected=removed,
        description=f"删除 {removed} 行完整重复记录（保留首次出现的行）。",
    )
    return new_df, action


def _normalize_amount(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, CleaningAction]:
    converted = 0
    affected = []
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].astype("string")
        cleaned_str = series.str.replace(_AMOUNT_PATTERN, "", regex=True)
        nums = pd.to_numeric(cleaned_str, errors="coerce")
        ok = nums.notna()
        converted += int(ok.sum())
        if ok.any():
            # object 类型承载混合结果（数值 + 未转换原文）
            df[col] = nums.astype("object").where(ok, series)
            affected.append(col)
    action = CleaningAction(
        action="金额归一化",
        columns=affected,
        cells_affected=converted,
        description=(
            f"去除金额符号与千分位并转为数值，影响列：{'、'.join(affected) or '无'}，"
            f"共 {converted} 个单元格；无法解析的值保留原样。"
        ),
    )
    return df, action


def _parse_dates(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, CleaningAction]:
    converted = 0
    affected = []
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].astype("string")
        # 中文日期单位先归一化（与 profiler 共用同一工具，口径一致）
        parsed = pd.to_datetime(normalize_cn_dates(series), errors="coerce", format="mixed")
        ok = parsed.notna()
        converted += int(ok.sum())
        if ok.any():
            df[col] = parsed.astype("object").where(ok, series)
            affected.append(col)
    action = CleaningAction(
        action="统一日期",
        columns=affected,
        cells_affected=converted,
        description=(
            f"统一日期格式并转为日期类型，影响列：{'、'.join(affected) or '无'}，"
            f"共 {converted} 个单元格；无法解析的值保留原样。"
        ),
    )
    return df, action


def _fill_missing(
    df: pd.DataFrame, strategies: dict[str, str]
) -> tuple[pd.DataFrame, CleaningAction]:
    filled_cells = 0
    dropped_rows = 0
    affected = []
    for col, strategy in strategies.items():
        if col not in df.columns or strategy == "保留":
            continue
        series = df[col].astype("string").replace("", pd.NA)
        null_count = int(series.isna().sum())
        if strategy == "删除该行":
            mask = series.notna()
            removed = int((~mask).sum())
            dropped_rows += removed
            df = df[mask].reset_index(drop=True)
            affected.append(col)
            continue
        if strategy in ("填充 0", "均值", "中位数"):
            # 只填充真正的缺失位；coerce 失败的原文（如 "N/A"）保留不动，
            # 避免静默把文本改写成数值。object 承载混合结果。
            nums = pd.to_numeric(series, errors="coerce")
            missing_mask = series.isna()
            result = series.astype("object").copy()
            result.loc[nums.notna()] = nums  # 可转换的值转为数值
            if strategy == "填充 0":
                result.loc[missing_mask] = 0
            elif strategy == "均值":
                result.loc[missing_mask] = nums.mean()
            else:
                result.loc[missing_mask] = nums.median()
            df[col] = result
            affected.append(col)
            filled_cells += null_count
            continue
        # 文本/分类填充（众数 / 未知 / 未填写 / 空字符串）
        if strategy == "众数":
            mode_val = series.dropna().mode()
            value = mode_val.iloc[0] if not mode_val.empty else pd.NA
        elif strategy == "未知":
            value = "未知"
        elif strategy == "未填写":
            value = "未填写"
        elif strategy == "空字符串":
            value = ""
        else:
            continue
        df[col] = series.fillna(value)
        affected.append(col)
        filled_cells += null_count

    action = CleaningAction(
        action="填充缺失值",
        columns=affected,
        rows_affected=dropped_rows,
        cells_affected=filled_cells,
        description=(
            f"按所选策略填充缺失值，影响列：{'、'.join(affected) or '无'}；"
            f"填充 {filled_cells} 单元格，删除 {dropped_rows} 行。"
        ),
    )
    return df, action


def _drop_anomalies(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, CleaningAction]:
    """按 IQR 法删除指定数值列的异常行（与 profiler 同口径）。"""
    drop_mask = pd.Series(False, index=df.index)
    for col in columns:
        if col not in df.columns:
            continue
        nums = pd.to_numeric(df[col].astype("string"), errors="coerce")
        clean = nums.dropna()
        if len(clean) < 5:
            continue
        q1, q3 = clean.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr <= 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        drop_mask |= (nums < lower) | (nums > upper)
    removed = int(drop_mask.sum())
    new_df = df[~drop_mask].reset_index(drop=True)
    action = CleaningAction(
        action="删除异常值",
        columns=columns,
        rows_affected=removed,
        description=(
            f"按 IQR 法删除数值列（{'、'.join(columns)}）中的异常值所在行，共删除 {removed} 行。"
        ),
    )
    return new_df, action


# ---------------------------------------------------------------- 计划与执行

_ACTION_ORDER = (
    "删除空白行",
    "删除空白列",
    "清理文本",
    "金额归一化",
    "统一日期",
    "填充缺失值",
    "删除异常值",
    "删除重复行",
)


def build_plan(profile: ProfileResult, choices: dict[str, Any]) -> CleaningPlan:
    """根据体检结果与用户选择生成清洗计划（预估影响，供预览）。

    choices 结构（key 省略或为空列表即不执行）：
    - drop_blank_rows / drop_blank_columns / strip_text / deduplicate: bool
    - normalize_amount / parse_dates / drop_anomalies: list[str] 列名
    - fill_missing: dict[str, str] 列名 → 策略名
    """
    actions: list[CleaningAction] = []
    by_name = {c.name: c for c in profile.columns}

    def _estimate(columns: list[str], kind: str) -> int:
        """预估可转换的**非空值**数量（与执行口径一致）。

        amount: 数值列可转数 ≈ 非空数；dates: 日期列可转数 ≈ 非空数 − date_issues。
        文本金额列无法从体检预估，返回 0（页面显示"执行时统计"）。
        """
        total = 0
        for name in columns:
            col = by_name.get(name)
            if col is None:
                continue
            non_null = profile.row_count - col.null_count
            if kind == "amount" and col.inferred_type in ("int", "float"):
                total += non_null
            elif kind == "dates" and col.inferred_type == "date":
                total += max(0, non_null - col.date_issues)
        return total

    if choices.get("drop_blank_rows"):
        actions.append(
            CleaningAction(
                action="删除空白行",
                rows_affected=profile.blank_rows,
                description=f"删除完全空白行（预计 {profile.blank_rows} 行）。",
            )
        )
    if choices.get("drop_blank_columns"):
        actions.append(
            CleaningAction(
                action="删除空白列",
                columns=profile.blank_columns,
                description=f"删除完全空白列（预计 {len(profile.blank_columns)} 个）。",
            )
        )
    if choices.get("strip_text"):
        actions.append(
            CleaningAction(
                action="清理文本",
                description="去除全部文本列首尾空格与不可见字符（影响数执行时统计）。",
            )
        )
    amount_cols = choices.get("normalize_amount") or []
    if amount_cols:
        actions.append(
            CleaningAction(
                action="金额归一化",
                columns=amount_cols,
                cells_affected=_estimate(amount_cols, "amount"),
                description=f"去除金额符号与千分位并转为数值，影响列：{'、'.join(amount_cols)}。",
            )
        )
    date_cols = choices.get("parse_dates") or []
    if date_cols:
        actions.append(
            CleaningAction(
                action="统一日期",
                columns=date_cols,
                cells_affected=_estimate(date_cols, "dates"),
                description=f"统一日期格式并转为日期类型，影响列：{'、'.join(date_cols)}。",
            )
        )
    fill = choices.get("fill_missing") or {}
    if fill:
        # 按策略分口径预估：删除该行 → 行数；其余 → 单元格数
        est_cells = sum(
            by_name[c].null_count for c, s in fill.items() if c in by_name and s != "删除该行"
        )
        est_rows = sum(
            by_name[c].null_count for c, s in fill.items() if c in by_name and s == "删除该行"
        )
        actions.append(
            CleaningAction(
                action="填充缺失值",
                columns=list(fill),
                rows_affected=est_rows,
                cells_affected=est_cells,
                description=(
                    f"按所选策略填充缺失值，影响列：{'、'.join(fill)}"
                    f"（预计填充 {est_cells} 单元格、删除 {est_rows} 行）。"
                ),
            )
        )
    anomaly_cols = choices.get("drop_anomalies") or []
    if anomaly_cols:
        est = sum(by_name[c].anomaly_count for c in anomaly_cols if c in by_name)
        actions.append(
            CleaningAction(
                action="删除异常值",
                columns=anomaly_cols,
                rows_affected=est,
                description=f"按 IQR 法删除异常值所在行，影响列：{'、'.join(anomaly_cols)}（预计 {est} 行）。",
            )
        )
    if choices.get("deduplicate"):
        actions.append(
            CleaningAction(
                action="删除重复行",
                rows_affected=profile.duplicate_rows,
                description=f"删除完整重复记录（预计 {profile.duplicate_rows} 行）。",
            )
        )

    # 按固定顺序排序，保证执行顺序可预期
    actions.sort(key=lambda a: _ACTION_ORDER.index(a.action))
    return CleaningPlan(
        actions=actions,
        rows_before=profile.row_count,
        fill_strategies={c: s for c, s in fill.items() if s != "保留"},
    )


def apply_plan(df: pd.DataFrame, plan: CleaningPlan) -> tuple[pd.DataFrame, CleaningLog]:
    """执行清洗计划，返回 (清洗后 df, 实际日志)。不修改原 df。"""
    current = df.copy(deep=True)
    log_actions: list[CleaningAction] = []

    for planned in plan.actions:
        action_name = planned.action
        if action_name == "删除空白行":
            current, actual = _drop_blank_rows(current)
        elif action_name == "删除空白列":
            current, actual = _drop_blank_columns(current)
        elif action_name == "清理文本":
            current, actual = _strip_text(current)
        elif action_name == "金额归一化":
            current, actual = _normalize_amount(current, planned.columns)
        elif action_name == "统一日期":
            current, actual = _parse_dates(current, planned.columns)
        elif action_name == "填充缺失值":
            fill_map = {c: plan.fill_strategies.get(c, "保留") for c in planned.columns}
            current, actual = _fill_missing(current, fill_map)
        elif action_name == "删除异常值":
            current, actual = _drop_anomalies(current, planned.columns)
        elif action_name == "删除重复行":
            current, actual = _deduplicate(current)
        else:
            continue  # 未知动作跳过（防御）
        log_actions.append(actual)

    log = CleaningLog(
        actions=log_actions,
        rows_before=len(df),
        rows_after=len(current),
        executed_at=datetime.now(),
    )
    return current, log
