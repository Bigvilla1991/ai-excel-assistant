"""页面 2：数据体检 —— 健康评分、问题清单、字段类型表。"""

from __future__ import annotations

import streamlit as st

from core.profiler import profile
from models.schemas import ProfileResult
from utils.format_utils import TYPE_LABELS_ORDER, type_description, type_label
from utils.logger import get_logger, log_error_safe
from utils.session import init_session_state

st.set_page_config(page_title="数据体检", page_icon="🔍", layout="wide")
init_session_state()
logger = get_logger("quality_page")

st.title("② 数据体检")

# ---- 页面守卫：必须先上传 ----
if st.session_state.raw_df is None:
    st.info("请先在「① 文件上传」页上传并确认数据，再进行体检。")
    st.stop()

# ---- 计算体检结果（会话内缓存：确认上传后 raw_df 不可变，只算一次）----
if st.session_state.profile is None and not st.session_state.profile_error:
    with st.spinner("正在体检数据，请稍候…"):
        try:
            st.session_state.profile = profile(st.session_state.raw_df)
        except Exception as exc:
            log_error_safe(logger, exc, "体检-计算")
            st.session_state.profile_error = True
            st.stop()

if st.session_state.profile_error:
    st.error("数据体检失败，请检查数据后重试，或回到「① 文件上传」重新确认文件。")
    st.stop()

result: ProfileResult = st.session_state.profile

# ---- 概览 ----
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("健康评分", f"{result.health_score}", help="满分 100，扣分项见下方问题清单")
c2.metric("总行数", f"{result.row_count:,}")
c3.metric("列数", f"{result.column_count:,}")
c4.metric("空值格", f"{result.null_cells:,}")
c5.metric("重复行", f"{result.duplicate_rows:,}")

score = result.health_score
has_error = any(i.severity == "error" for i in result.issues)
error_count = sum(1 for i in result.issues if i.severity == "error")
if has_error:
    # 横幅口径与问题清单一致：存在 error 级问题时，即使分数较高也明确提示
    st.warning(
        f"整体评分 {score} 分，但有 **{error_count} 个需优先处理的问题**"
        f"（红色条目），建议先处理后再分析。"
    )
elif score >= 90:
    st.success(f"数据整体质量**良好**（{score} 分）。")
elif score >= 70:
    st.warning(f"数据质量**一般**（{score} 分），建议处理下方问题后再分析。")
else:
    st.error(f"数据质量**较差**（{score} 分），强烈建议先清洗数据。")

# ---- 问题清单 ----
st.subheader("问题清单")
issues = result.issues
if not issues:
    st.success("未发现明显问题。")
else:
    for issue in issues:
        if issue.severity == "error":
            st.error(issue.message)
        elif issue.severity == "warning":
            st.warning(issue.message)
        else:
            st.info(issue.message)

# ---- 字段类型表 ----
st.subheader("字段概览")
st.caption("类型为自动推断，可在「③ 数据清洗」中手动调整转换。")

rows = []
for col in result.columns:
    flags = []
    if col.is_id_like:
        flags.append("编号列")
    if col.high_missing:
        flags.append("高缺失")
    if col.is_constant:
        flags.append("常量")
    if col.type_conflict:
        flags.append("混合类型")
    if col.date_issues:
        flags.append(f"日期异常×{col.date_issues}")
    if col.anomaly_count:
        flags.append(f"异常值×{col.anomaly_count}")
    rows.append(
        {
            "字段": col.name,
            "推断类型": type_label(col.inferred_type),
            "唯一值数": col.unique_count,
            "空值数": col.null_count,
            "空值率": f"{col.null_rate:.1%}",
            "问题标记": "、".join(flags) or "—",
            "样例值": "、".join(col.sample_values) or "（全空）",
        }
    )
st.dataframe(rows, hide_index=True, width="stretch")

# ---- 类型说明（可折叠）----
with st.expander("各字段类型说明", expanded=False):
    for type_name in TYPE_LABELS_ORDER:
        desc = type_description(type_name)
        if desc:
            st.markdown(f"- **{type_label(type_name)}**：{desc}")
    st.caption("异常值仅提示、不自动删除；删除或填充需在「③ 数据清洗」确认。")

st.caption("下一步：从侧边栏进入 **③ 数据清洗**，选择要执行的清洗动作。")
