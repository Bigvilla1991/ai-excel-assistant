"""页面 3：数据清洗 —— 动作选择（form）、预览、执行、撤销重选。"""

from __future__ import annotations

import streamlit as st

from core.cleaner import apply_plan, build_plan
from models.schemas import CleaningPlan
from utils.format_utils import type_label
from utils.logger import get_logger
from utils.session import init_session_state
from utils.ui import (
    handle_exception,
    render_session_status,
    require_profile,
    require_upload,
)

st.set_page_config(page_title="数据清洗", page_icon="🧹", layout="wide")
init_session_state()
render_session_status()
logger = get_logger("cleaning_page")

st.title("③ 数据清洗")

# ---- 页面守卫 ----
require_upload()
require_profile()

profile = st.session_state.profile
by_name = {c.name: c for c in profile.columns}

# ---- 已清洗状态 ----
cleaned = st.session_state.clean_df is not None
if cleaned:
    st.info(
        f"当前数据已清洗：{st.session_state.cleaning_log.rows_before:,} 行 → "
        f"{st.session_state.cleaning_log.rows_after:,} 行，"
        f"共执行 {len(st.session_state.cleaning_log.actions)} 个动作。"
    )

# ---- 数值/日期/文本列候选 ----
numeric_cols = [c.name for c in profile.columns if c.inferred_type in ("int", "float")]
date_cols = [c.name for c in profile.columns if c.inferred_type == "date"]
missing_cols = [c.name for c in profile.columns if c.null_count > 0 and not c.is_id_like]

with st.form("cleaning_form"):
    st.subheader("清洗动作")
    st.caption("所有动作均可先预览再执行；原始数据始终保留，可随时撤销。")

    c1, c2 = st.columns(2)
    with c1:
        drop_blank_rows = st.checkbox(
            "删除完全空白行",
            value=True,
            help=f"预计删除 {profile.blank_rows} 行",
            key="c_drop_blank_rows",
        )
        drop_blank_cols = st.checkbox(
            "删除完全空白列",
            value=True,
            help=f"预计删除 {len(profile.blank_columns)} 列",
            key="c_drop_blank_cols",
        )
        strip_text = st.checkbox(
            "清理文本（首尾空格与不可见字符）",
            value=True,
            help="作用于全部文本/分类列，例如「 华东 」→「华东」",
            key="c_strip_text",
        )
        deduplicate = st.checkbox(
            "删除完整重复记录",
            help=f"预计删除 {profile.duplicate_rows} 行",
            key="c_deduplicate",
        )
    with c2:
        normalize_cols = st.multiselect(
            "金额归一化（去符号/千分位 → 数值）",
            options=numeric_cols,
            help="如「￥1,234.50」→ 1234.5",
            key="c_normalize",
        )
        parse_cols = st.multiselect(
            "统一日期格式",
            options=date_cols,
            help="如「2024/1/5」「2024年1月5日」→ 统一为日期",
            key="c_parse_dates",
        )
        anomaly_cols = st.multiselect(
            "删除异常值所在行（IQR 法）",
            options=numeric_cols,
            help="删除数值超出正常范围的行，需谨慎确认",
            key="c_anomalies",
        )

    # 删除异常值需二次确认（预估删除行数 > 0 时）
    confirm_anomalies = False
    if anomaly_cols:
        est_anomalies = sum(by_name[c].anomaly_count for c in anomaly_cols if c in by_name)
        confirm_anomalies = st.checkbox(
            f"我已知晓：删除异常值预计影响约 {est_anomalies} 行，确认执行",
            key="c_confirm_anomalies",
        )

    # 缺失值策略（按列类型给出可选策略）
    st.markdown("**缺失值填充策略**（默认保留）")
    fill_strategies: dict[str, str] = {}
    if missing_cols:
        for col_name in missing_cols:
            col = by_name[col_name]
            if col.inferred_type in ("int", "float"):
                options = ["保留", "填充 0", "均值", "中位数"]
            elif col.inferred_type == "category":
                options = ["保留", "众数", "未知"]
            elif col.inferred_type == "date":
                options = ["保留", "删除该行"]
            else:
                options = ["保留", "未填写"]
            strategy = st.selectbox(
                f"{col_name}（{type_label(col.inferred_type)}，缺 {col.null_count} 个）",
                options,
                key=f"c_fill_{col_name}",
            )
            if strategy != "保留":
                fill_strategies[col_name] = strategy
    else:
        st.caption("没有需要填充的列。")

    st.divider()
    col_prev, col_exec = st.columns(2)
    preview_clicked = col_prev.form_submit_button("预览变更")
    execute_clicked = col_exec.form_submit_button("执行清洗", type="primary")

# 汇总当前表单选择（预览与执行共用，保证所见即所执行）
choices = {
    "drop_blank_rows": drop_blank_rows,
    "drop_blank_columns": drop_blank_cols,
    "strip_text": strip_text,
    "deduplicate": deduplicate,
    "normalize_amount": normalize_cols,
    "parse_dates": parse_cols,
    "drop_anomalies": anomaly_cols if confirm_anomalies else [],
    "fill_missing": fill_strategies,
}

# ---- 预览与执行（按钮均在表单内，用当前表单值重建计划，所见即所执行）----
if preview_clicked:
    try:
        st.session_state.cleaning_plan = build_plan(profile, choices)
    except Exception as exc:
        handle_exception(exc, logger, "生成清洗计划", fatal=False)

if execute_clicked:
    try:
        plan_now = build_plan(profile, choices)
    except Exception as exc:
        handle_exception(exc, logger, "生成清洗计划", fatal=False)
        st.stop()
    if not plan_now.actions:
        st.warning("当前没有选择任何清洗动作。")
        st.stop()
    with st.spinner("正在清洗…"):
        try:
            clean_df, log = apply_plan(st.session_state.raw_df, plan_now)
        except Exception as exc:
            handle_exception(
                exc,
                logger,
                "清洗执行",
                message="清洗执行失败，原始数据未受影响，请调整选项后重试。",
            )
    st.session_state.clean_df = clean_df
    st.session_state.cleaning_log = log
    st.session_state.cleaning_plan = plan_now
    # 数据已变化：使下游分析/AI 缓存失效，避免展示旧数据的结果
    st.session_state.analysis = None
    st.session_state.analysis_key = None
    st.session_state.ai_report = None
    logger.info(
        "清洗完成 | actions=%d rows %d->%d",
        len(log.actions),
        log.rows_before,
        log.rows_after,
    )
    st.success(
        f"清洗完成：{log.rows_before:,} 行 → {log.rows_after:,} 行，"
        f"执行 {len(log.actions)} 个动作。"
    )
    st.rerun()

plan: CleaningPlan | None = st.session_state.cleaning_plan
if plan and plan.actions:
    st.subheader("清洗计划预览")
    st.caption("以下为预计影响，执行后以实际统计为准。")
    rows = [
        {
            "动作": a.action,
            "影响列": "、".join(a.columns) or "—",
            "预计影响": (
                f"{a.rows_affected} 行"
                if a.rows_affected
                else f"{a.cells_affected} 单元格"
                if a.cells_affected
                else "执行时统计"
            ),
            "说明": a.description,
        }
        for a in plan.actions
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
elif plan is not None:
    st.caption("当前计划为空：没有选择任何动作，或所选动作无影响。")

# ---- 已执行：变更摘要 / 预览 / 撤销 ----
if cleaned:
    st.divider()
    st.subheader("清洗结果")
    log = st.session_state.cleaning_log
    for action in log.actions:
        summary = (
            f"**{action.action}**"
            + (f"（影响列：{'、'.join(action.columns)}）" if action.columns else "")
            + (f"：{action.rows_affected} 行" if action.rows_affected else "")
            + (f"：{action.cells_affected} 单元格" if action.cells_affected else "")
        )
        st.markdown(f"- {summary}")
        st.caption(f"  {action.description}")

    with st.expander("查看清洗后数据（前 100 行）", expanded=False):
        st.dataframe(st.session_state.clean_df.head(100), hide_index=True, width="stretch")

    if st.button("撤销清洗并重新选择", key="undo_btn"):
        st.session_state.clean_df = None
        st.session_state.cleaning_log = None
        st.session_state.cleaning_plan = None
        st.rerun()

    st.caption("下一步：从侧边栏进入 **④ 数据分析**（默认使用清洗后的数据）。")
