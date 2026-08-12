"""页面 6：结果导出 —— 清洗数据 / 分析工作簿 / AI 报告（xlsx / md / html）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.chart_engine import bar_chart, hbar_ranking, line_chart
from core.exporter import (
    build_analysis_workbook,
    build_cleaned_workbook,
    build_report_html,
    build_report_markdown,
)
from utils.logger import get_logger
from utils.session import init_session_state
from utils.ui import (
    handle_exception,
    render_session_status,
    require_profile,
    require_upload,
)

st.set_page_config(page_title="结果导出", page_icon="📦", layout="wide")
init_session_state()
render_session_status()
logger = get_logger("export_page")

st.title("⑥ 结果导出")
st.caption("导出内容与页面展示同源，数字可追溯。导出的 Excel 可继续编辑使用。")

# ---- 页面守卫 ----
require_upload()
require_profile()

raw = st.session_state.raw_df
clean = st.session_state.clean_df if st.session_state.clean_df is not None else raw
cleaned_used = st.session_state.clean_df is not None
profile = st.session_state.profile
analysis = st.session_state.analysis
log = st.session_state.cleaning_log
report = st.session_state.ai_report
src_name = Path(st.session_state.uploaded_name or "data").stem

if not cleaned_used:
    st.caption("当前未执行清洗，导出将使用**原始数据**（可先到「③ 数据清洗」处理）。")

# ---- 导出区 ----
st.subheader("导出文件")
st.caption("所有导出在浏览器内即时生成，不会在服务器留存。")


# 缓存：同一数据与参数不重复生成（避免每次 rerun 全量重建，10 万行场景）
@st.cache_data(show_spinner=False)
def _cleaned_bytes(df: pd.DataFrame, cleaned: bool) -> bytes:
    return build_cleaned_workbook(df, cleaned)


@st.cache_data(show_spinner=False)
def _analysis_bytes(
    raw_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    prof_json: str,
    analysis_json: str,
    log_json: str,
    report_json: str,
) -> bytes:
    """参数用 JSON 序列化（DataFrame 不可直接 hash）。"""
    from models.schemas import AIReport, AnalysisResult, CleaningLog, ProfileResult

    return build_analysis_workbook(
        raw_df,
        clean_df,
        ProfileResult.model_validate_json(prof_json),
        AnalysisResult.model_validate_json(analysis_json),
        log=CleaningLog.model_validate_json(log_json) if log_json else None,
        report=AIReport.model_validate_json(report_json) if report_json else None,
    )


# 1. 清洗数据
try:
    clean_bytes = _cleaned_bytes(clean, cleaned_used)
    st.download_button(
        "下载清洗数据（.xlsx）",
        data=clean_bytes,
        file_name=f"cleaned_{src_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_clean",
    )
except Exception as exc:
    handle_exception(exc, logger, "生成清洗数据导出", fatal=False)

# 2. 分析工作簿
if analysis is not None:
    try:
        analysis_bytes = _analysis_bytes(
            raw,
            clean,
            profile.model_dump_json(),
            analysis.model_dump_json(),
            log.model_dump_json() if log else "",
            report.model_dump_json() if report else "",
        )
        st.download_button(
            "下载分析工作簿（.xlsx，含 7+ Sheet）",
            data=analysis_bytes,
            file_name=f"analysis_{src_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_analysis",
        )
    except Exception as exc:
        handle_exception(exc, logger, "生成分析工作簿", fatal=False)
else:
    st.caption("分析工作簿：请先到「④ 数据分析」完成一次分析。")

# 3. AI 报告
if report is not None:
    try:
        md_text = build_report_markdown(report)
        st.download_button(
            "下载 AI 报告（.md）",
            data=md_text.encode("utf-8"),
            file_name=f"ai_report_{src_name}.md",
            mime="text/markdown",
            key="dl_report_md",
        )
        # HTML 报告（内嵌当前分析图表，与页面同源）
        figures = []
        if analysis is not None:
            if analysis.grouped:
                figures.append(bar_chart(analysis))
            if analysis.rankings:
                figures.append(hbar_ranking(analysis.rankings, analysis.metric))
            if analysis.trends:
                figures.append(
                    line_chart([t for t in analysis.trends if t.value is not None], analysis.metric)
                )
        html_text = build_report_html(report, figures)
        st.download_button(
            "下载 AI 报告（.html，含交互图表）",
            data=html_text.encode("utf-8"),
            file_name=f"ai_report_{src_name}.html",
            mime="text/html",
            key="dl_report_html",
        )
    except Exception as exc:
        handle_exception(exc, logger, "生成 AI 报告导出", fatal=False)
else:
    st.caption("AI 报告：请先到「⑤ AI 洞察」生成报告。")

# ---- 使用说明 ----
with st.expander("导出内容说明", expanded=False):
    st.markdown(
        """
        - **清洗数据**：清洗后数据 + 清洗说明（未清洗时为原始数据）
        - **分析工作簿**：原始数据 / 清洗数据 / 数据质量 / 问题清单 / 汇总统计 /
          排名分析 / 趋势分析 / 清洗日志（有 AI 报告时追加 AI报告 Sheet）
        - **AI 报告**：Markdown 可直接编辑；HTML 内嵌交互图表（打开时需联网加载图表库）
        - 安全说明：以单引号 `'` 开头的单元格为公式注入防护，Excel 中按文本显示
        """
    )
