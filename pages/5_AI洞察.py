"""页面 5：AI 洞察 —— 固定结构报告（AI / 模板回退 / 数字校验提示）。"""

from __future__ import annotations

import os

import streamlit as st

from core.ai_context import build_context
from core.ai_engine import generate_report, report_text
from core.ai_validation import validate_report_numbers
from models.schemas import AIReport
from utils.logger import get_logger, log_error_safe
from utils.session import init_session_state
from utils.ui import (
    handle_exception,
    render_session_status,
    require_analysis,
    require_profile,
    require_upload,
)

st.set_page_config(page_title="AI 洞察", page_icon="🤖", layout="wide")
init_session_state()
render_session_status()
logger = get_logger("ai_page")

st.title("⑤ AI 洞察")
st.caption("Python 负责准确计算，AI 负责解释结果 —— 报告数字全部来自左侧统计结果，可溯源。")

# ---- 页面守卫 ----
require_upload()
require_profile()
require_analysis()

# ---- 模式选择 ----
mode_help = {
    "local": "数据不发送给任何模型，使用本地模板报告（适合敏感数据）",
    "secure": "仅发送字段名、汇总统计、趋势和异常摘要，不发送完整记录（默认）",
    "enhanced": "在安全模式基础上，附加每字段最多 3 个样例值",
}
mode = st.radio(
    "AI 模式",
    ["secure", "enhanced", "local"],
    index={"local": 2, "secure": 0, "enhanced": 1}.get(st.session_state.ai_mode, 0),
    format_func={"secure": "安全 AI（默认）", "enhanced": "增强 AI", "local": "本地模式"}.get,
    help="\n".join(mode_help.values()),
    key="ai_mode_radio",
    horizontal=True,
)
# 模式变化时清空旧报告：防止用户误以为旧报告由当前模式生成（隐私误判）
if st.session_state.ai_mode != mode:
    st.session_state.ai_mode = mode
    st.session_state.ai_report = None


def _api_key() -> str | None:
    """密钥双通道：环境变量（.env / 系统）或 Streamlit Cloud Secrets。"""
    env_key = os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    try:
        return st.secrets.get("DEEPSEEK_API_KEY")
    except Exception:  # AppTest / 本地无 secrets.toml 时安全降级
        return None


has_api_key = bool(_api_key())

if mode != "local" and not has_api_key:
    st.warning(
        "当前未配置 DEEPSEEK_API_KEY（本地 .env 或 Streamlit Cloud Secrets），"
        "将使用**本地模板报告**。配置密钥后可生成 AI 解读。"
    )

# ---- 上下文（数据与④分析页同源）----
# local 模式不发送任何内容；上下文仅本地用于模板生成与数字校验
context_mode = "secure" if mode == "local" else mode
try:
    context = build_context(
        st.session_state.profile,
        st.session_state.analysis,
        mode=context_mode,
    )
except Exception as exc:
    log_error_safe(logger, exc, "AI-上下文")
    st.error("上下文构造失败，请返回「④ 数据分析」重新选择。")
    st.stop()

st.caption(
    f"发送范围：{st.session_state.analysis.metric} × "
    f"{st.session_state.analysis.dimension or '全部'}（共 "
    f"{st.session_state.profile.row_count:,} 行 × {st.session_state.profile.column_count} 列）"
)

# ---- 生成按钮 ----
col_btn, col_info = st.columns([1, 3])
generate_clicked = col_btn.button(
    "生成 AI 报告",
    type="primary",
    disabled=(mode != "local" and not has_api_key),
    key="gen_btn",
    help="生成固定结构的 7 段解读报告",
)
if col_info.button("清空报告", key="clear_btn"):
    st.session_state.ai_report = None
    st.rerun()

if generate_clicked:
    with st.spinner("正在生成报告…"):
        try:
            st.session_state.ai_report = generate_report(
                context,
                mode=mode,
                api_key=_api_key(),
            )
            logger.info("AI 报告完成 | mode=%s", mode)
        except Exception as exc:
            handle_exception(exc, logger, "报告生成", message="报告生成失败，请重试。")

report: AIReport | None = st.session_state.ai_report
if report is None:
    st.caption("点击上方按钮生成报告。生成后各段内容如下。")
    st.stop()

# ---- 报告展示 ----
st.divider()
if report.source == "template":
    st.info("本报告由**本地模板**生成（未调用模型），数字全部来自统计结果。")
else:
    st.success("本报告由 **AI 生成**，数字已经过程序交叉校验。")

# 数字溯源二次校验（双保险）
problems = validate_report_numbers(report_text(report), context)
if problems:
    st.warning(f"以下数字未能从统计结果中溯源，请人工核对：{'、'.join(problems[:10])}")

st.markdown(f"### 数据概况\n{report.overview}")

sections = [
    ("核心发现", report.findings),
    ("趋势变化", report.trends),
    ("异常情况", report.anomalies),
    ("可能原因（推断）", report.causes),
    ("建议关注事项", report.recommendations),
    ("数据质量提醒", report.quality_notes),
]
for title, items in sections:
    st.markdown(f"### {title}")
    if not items:
        st.caption("（无）")
        continue
    for item in items:
        st.markdown(f"- {item}")

st.caption(f"报告生成时间：{report.generated_at:%Y-%m-%d %H:%M} ｜ 数据范围：当前会话数据")
st.caption(
    "提示：AI 解读仅供参考，不视为专业审计或决策依据；关键结论请以「④ 数据分析」的统计表为准。"
)
