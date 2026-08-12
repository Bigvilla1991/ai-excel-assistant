"""页面 4：数据分析 —— 基础统计与维度分组（图表 Day 7 接入）。"""

from __future__ import annotations

import streamlit as st

from core.analyzer import _detect_numeric_cols, analyze
from models.schemas import AnalysisResult, ProfileResult
from utils.logger import get_logger, log_error_safe
from utils.session import init_session_state

st.set_page_config(page_title="数据分析", page_icon="📈", layout="wide")
init_session_state()
logger = get_logger("analysis_page")

st.title("④ 数据分析")

# ---- 页面守卫 ----
if st.session_state.raw_df is None:
    st.info("请先在「① 文件上传」页上传并确认数据。")
    st.stop()
if st.session_state.profile is None:
    st.info("请先进入「② 数据体检」生成体检结果。")
    st.stop()

# ---- 数据选择：优先使用清洗后数据 ----
using_clean = st.session_state.clean_df is not None
data = st.session_state.clean_df if using_clean else st.session_state.raw_df
profile: ProfileResult = st.session_state.profile

if using_clean:
    st.caption("正在使用**清洗后**的数据。若需基于原始数据，请到「③ 数据清洗」撤销清洗。")
else:
    st.caption("正在使用**原始**数据（尚未清洗）。")

# 类型信息以体检结果为准（id 列不参与求和）；
# 清洗后的新增数值列（如金额归一化）用轻量探测补入候选
by_name = {c.name: c for c in profile.columns}
id_cols = {c.name for c in profile.columns if c.is_id_like}
numeric_candidates = list(
    dict.fromkeys(
        [c.name for c in profile.columns if c.inferred_type in ("int", "float")]
        + [c for c in _detect_numeric_cols(data) if c not in id_cols]
    )
)
dimension_candidates = [
    c.name for c in profile.columns if c.inferred_type in ("category", "text") and not c.is_id_like
]

# ---- 选择器 ----
c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
with c1:
    metric = st.selectbox(
        "指标（数值）",
        numeric_candidates,
        index=0 if numeric_candidates else None,
        help="参与求和的数值列；若指标列含金额符号等文本，请先到「③ 数据清洗」归一化",
        key="a_metric",
    )
with c2:
    dimension = st.selectbox(
        "维度（分组）",
        [None] + dimension_candidates,
        format_func=lambda x: "不分组（总体汇总）" if x is None else x,
        key="a_dimension",
    )
with c3:
    metric_type = by_name[metric].inferred_type if metric else "text"
    if metric_type in ("int", "float"):
        agg_options = ["sum", "mean", "count", "nunique"]
    else:
        agg_options = ["count", "nunique"]
    agg = st.selectbox(
        "聚合方式",
        agg_options,
        format_func={"sum": "求和", "mean": "平均", "count": "行数", "nunique": "去重计数"}.get,
        key="a_agg",
    )
with c4:
    include_blank = st.checkbox("包含空白分类", value=False, key="a_blank")

if metric is None:
    st.warning("未识别到可用的数值指标列。若指标列含金额符号等文本，请先清洗再返回。")
    st.stop()

# ---- 计算（会话内缓存：同一组参数只算一次）----
cache_key = f"analysis_{metric}_{dimension or 'all'}_{agg}_{include_blank}_{'clean' if using_clean else 'raw'}"
if st.session_state.analysis is None or st.session_state.analysis_key != cache_key:
    with st.spinner("正在计算统计…"):
        try:
            result: AnalysisResult = analyze(
                data,
                metric,
                dimension=dimension,
                agg=agg,
                include_blank=include_blank,
                exclude_cols=list(id_cols),
            )
            st.session_state.analysis = result
            st.session_state.analysis_key = cache_key
        except Exception as exc:
            log_error_safe(logger, exc, "分析-计算")
            st.error("统计计算失败，请调整选择后重试。")
            st.stop()

result: AnalysisResult = st.session_state.analysis

# ---- 总体概况 ----
agg_labels = {"sum": "合计", "mean": "总体均值", "count": "总行数", "nunique": "去重数"}
ov = result.overview
m1, m2, m3, m4 = st.columns(4)
m1.metric("指标", str(ov["指标"]))
m2.metric("维度", str(ov["维度"]))
m3.metric("聚合方式", str(ov["聚合"]))
m4.metric(
    agg_labels.get(str(ov["聚合"]), "指标合计"),
    f"{ov['指标合计']:,.2f}" if isinstance(ov["指标合计"], float) else "—",
)

# ---- 维度分组表 ----
if dimension is not None:
    st.subheader(f"按「{dimension}」分组汇总")
    rows = [
        {
            "分类": g.label,
            "数值": f"{g.value:,.2f}" if g.value is not None else "（无有效值）",
            "占比": f"{g.share:.1%}" if g.share is not None else "—",
        }
        for g in result.grouped
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
else:
    st.subheader("总体汇总")
    for g in result.grouped:
        st.markdown(
            f"- **{g.label}**：{g.value:,.2f}"
            if g.value is not None
            else f"- **{g.label}**：（无有效值）"
            + (f"（占比 {g.share:.1%}）" if g.share is not None else "")
        )

# ---- 基础统计表 ----
st.subheader("基础统计（数值列）")
stats_rows = []
for col_name, stats in result.statistics.items():
    row = {"字段": col_name}
    row.update(
        {
            k: f"{v:,.2f}" if isinstance(v, float) else ("—" if v is None else v)
            for k, v in stats.items()
        }
    )
    stats_rows.append(row)
if stats_rows:
    st.dataframe(stats_rows, hide_index=True, width="stretch")
else:
    st.caption("未识别到数值列，无基础统计。")

st.caption("统计口径与 Excel 一致：求和/平均忽略空值；若指标列尚未归一化，结果可能不含文本金额。")
st.caption("下一步：从侧边栏进入 **⑤ AI 洞察** 生成解读报告。")
