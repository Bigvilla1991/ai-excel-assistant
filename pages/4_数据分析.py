"""页面 4：数据分析 —— 基础统计与维度分组（图表 Day 7 接入）。"""

from __future__ import annotations

import streamlit as st

from core.analyzer import analyze, build_rankings, detect_numeric_cols, trend
from core.chart_engine import bar_chart, hbar_ranking, line_chart, scatter_chart
from models.schemas import AnalysisResult, ProfileResult
from utils.logger import get_logger
from utils.session import init_session_state
from utils.ui import (
    apply_theme,
    handle_exception,
    render_page_header,
    render_session_status,
    require_profile,
    require_upload,
)

st.set_page_config(page_title="数据分析", page_icon="📈", layout="wide")
init_session_state()
apply_theme()
render_session_status()
logger = get_logger("analysis_page")

render_page_header("数据分析", "基础统计、维度分组、排名与时间趋势，口径与 Excel 一致。", step=4)

# ---- 页面守卫 ----
require_upload()
require_profile()

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
        + [c for c in detect_numeric_cols(data) if c not in id_cols]
    )
)
dimension_candidates = [
    c.name for c in profile.columns if c.inferred_type in ("category", "text") and not c.is_id_like
]
# 高基数维度提示：分组键（如姓名）会随 AI 上下文发送，隐私提示
high_cardinality_dims = [
    c.name
    for c in profile.columns
    if c.inferred_type in ("category", "text") and c.unique_count > 100
]
if high_cardinality_dims and dimension_candidates:
    st.caption(
        "⚠️ 以下维度取值较多（>100），分组标签会随 AI 上下文发送："
        + "、".join(high_cardinality_dims[:5])
        + "。如含身份信息请勿用作维度，或使用本地模式。"
    )

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
            handle_exception(exc, logger, "统计计算", message="统计计算失败，请调整选择后重试。")
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
    rows = [{"分类": g.label, "数值": g.value, "占比": g.share} for g in result.grouped]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "数值": st.column_config.NumberColumn(format="%.2f"),
            "占比": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
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

# ================================================================ 图表区（Day 7）
# 全部图表与上方汇总表共用同一份 AnalysisResult（同源，§11.5）
if dimension is not None and agg == "sum":
    st.divider()
    st.subheader("排名与图表")

    c_rank, c_n = st.columns([2, 1])
    with c_n:
        top_n = st.selectbox("排名数量", [5, 10, 20], index=1, key="a_topn")
        bottom_mode = st.checkbox("BOTTOM（末位）", value=False, key="a_bottom")
    with c_rank:
        rankings = build_rankings(result, top_n=top_n, bottom=bottom_mode)
        st.dataframe(
            [{"排名": r.rank, "分类": r.label, "数值": r.value, "占比": r.share} for r in rankings],
            hide_index=True,
            width="stretch",
            column_config={
                "数值": st.column_config.NumberColumn(format="%.2f"),
                "占比": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    if rankings:
        st.plotly_chart(bar_chart(result), width="stretch", key="chart_bar")
        st.plotly_chart(
            hbar_ranking(rankings, metric, bottom=bottom_mode),
            width="stretch",
            key="chart_rank",
        )
        if len(build_rankings(result, top_n=999)) > top_n:
            st.caption(f"仅展示前 {top_n} 名，并列边界可能被截断。")
    # 无条件写回（空列表也写回），防止残留上一次的排名（AI 上下文/导出会读到）
    result.rankings = rankings

# ---- 散点图（两个数值列）----
if len(numeric_candidates) >= 2:
    st.divider()
    st.subheader("散点图（两列关系）")
    sc1, sc2 = st.columns(2)
    x_col = sc1.selectbox("X 轴", numeric_candidates, index=0, key="a_scatter_x")
    y_col = sc2.selectbox("Y 轴", numeric_candidates, index=1, key="a_scatter_y")
    if x_col != y_col:
        st.plotly_chart(scatter_chart(data, x_col, y_col), width="stretch", key="chart_scatter")
    else:
        st.caption("请选择两个不同的数值列。")

# ---- 趋势图（日期列）----
date_candidates = [
    c.name for c in profile.columns if c.inferred_type == "date" and not c.is_id_like
]
if date_candidates:
    st.divider()
    st.subheader("时间趋势")
    tc1, tc2 = st.columns([2, 1])
    date_col = tc1.selectbox("日期列", date_candidates, key="a_date_col")
    granularity = tc2.selectbox(
        "时间粒度",
        ["day", "week", "month", "quarter"],
        index=2,
        format_func={"day": "按日", "week": "按周", "month": "按月", "quarter": "按季度"}.get,
        key="a_granularity",
    )
    # 数值指标才可做趋势（文本指标无法求和）
    if metric not in numeric_candidates:
        st.caption("当前指标为文本类型，无法生成数值趋势；请先清洗转换后再试。")
    else:
        trend_key = f"trend_{metric}_{date_col}_{granularity}_{'clean' if using_clean else 'raw'}"
        if st.session_state.trends_key != trend_key:
            try:
                st.session_state.trends = trend(data, metric, date_col, granularity=granularity)
                st.session_state.trends_key = trend_key
            except Exception as exc:
                handle_exception(
                    exc,
                    logger,
                    "趋势计算",
                    message="趋势计算失败，日期列可能无法解析。",
                    fatal=False,
                )
                st.session_state.trends = []
        points = st.session_state.trends

        valid_points = [p for p in points if p.value is not None]
        # 无条件写回（空列表也写回），防止残留上一次的趋势
        result.trends = valid_points
        if valid_points:
            st.plotly_chart(
                line_chart(
                    valid_points,
                    metric,
                    {"day": "日", "week": "周", "month": "月", "quarter": "季度"}[granularity],
                ),
                width="stretch",
                key="chart_line",
            )
            trend_rows = [
                {"周期": p.period, "数值": p.value, "环比": p.change_pct} for p in valid_points
            ]
            st.dataframe(
                trend_rows,
                hide_index=True,
                width="stretch",
                column_config={
                    "数值": st.column_config.NumberColumn(format="%.2f"),
                    "环比": st.column_config.NumberColumn(format="%+.1f%%"),
                },
            )
            peak = max(valid_points, key=lambda p: p.value)
            st.caption(f"峰值：**{peak.period}**（{peak.value:,.2f}）")
        elif points:
            st.caption("所选周期内均无有效指标值，无法生成趋势。")
        else:
            st.caption("日期列无法解析或没有有效日期，无法生成趋势。")
