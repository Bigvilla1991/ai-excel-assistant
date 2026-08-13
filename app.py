"""AI Excel 数据处理助手工作台。

首页只负责三件事：说明价值、接收文件、把用户带入任务流。具体处理
由「文件上传」页完成，避免首页和解析页各自维护一套逻辑。
"""

from __future__ import annotations

import streamlit as st

from utils.logger import get_logger
from utils.session import init_session_state
from utils.ui import apply_theme, render_footer, render_section_heading, render_session_status

st.set_page_config(
    page_title="AI Excel 数据处理助手",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_session_state()
apply_theme()
render_session_status()
logger = get_logger("home")


def _go_to_upload(uploaded: st.runtime.uploaded_file_manager.UploadedFile | None) -> None:
    if uploaded is not None:
        st.session_state.pending_upload = {
            "name": uploaded.name,
            "data": uploaded.getvalue(),
            "type": uploaded.type,
        }
    st.switch_page("pages/1_文件上传.py")


st.markdown(
    '<div class="aec-hero">'
    '<div class="aec-eyebrow">DATA WORKSPACE · V1.1</div>'
    '<h1>把 Excel 整理工作，变成一条清晰的任务流。</h1>'
    '<p>上传文件后，系统会依次完成解析、体检、清洗、分析、AI 解读与结果交付。'
    '每一步都保留原始数据、处理依据和可追溯结果。</p>'
    '<div class="aec-hero-meta"><span class="aec-meta-pill">支持 XLSX / CSV</span>'
    '<span class="aec-meta-pill">本地计算优先</span><span class="aec-meta-pill">结果可导出</span></div>'
    '</div>',
    unsafe_allow_html=True,
)

render_section_heading("从文件到结论", "一条主线完成数据准备、探索和交付")
flow = [
    ("01", "上传与解析", "识别工作表、编码和表头，先确认数据再进入后续步骤。"),
    ("02", "数据体检", "快速查看空值、重复、类型冲突和异常值，明确优先问题。"),
    ("03", "清洗与复核", "逐项选择清洗动作，预览影响范围，执行后仍可撤销。"),
    ("04", "分析与洞察", "围绕指标、维度和时间趋势生成统计结果与可解释结论。"),
]
for row_start in range(0, len(flow), 2):
    cols = st.columns(2)
    for col, (number, title, desc) in zip(cols, flow[row_start : row_start + 2], strict=False):
        with col:
            st.markdown(
                f'<div class="aec-card"><div class="aec-card-kicker">{number}</div>'
                f'<h3>{title}</h3><p>{desc}</p></div>',
                unsafe_allow_html=True,
            )

st.write("")
with st.container():
    st.markdown(
        '<div class="aec-action-card"><h2>开始一个数据任务</h2>'
        '<p>文件只在当前会话中处理。上传后可在解析页选择工作表、编码和表头，并先预览再确认。</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "选择 Excel 或 CSV 文件",
        type=["xlsx", "csv"],
        key="home_uploader",
        help="单文件不超过 20MB，建议不超过 10 万行。",
    )
    action_col, demo_col = st.columns([1, 1])
    with action_col:
        if st.button("解析文件并继续", type="primary", key="home_continue", width="stretch"):
            _go_to_upload(uploaded)
    with demo_col:
        st.page_link("pages/1_文件上传.py", label="进入文件上传页", icon="📁", width="stretch")
    if uploaded is not None:
        st.caption(f"已选择：{uploaded.name} · {uploaded.size / 1024:.0f} KB。点击上方按钮进入解析。")
    else:
        st.caption("也可以直接进入文件上传页，或使用项目 samples 目录中的演示数据。")

render_section_heading("你将得到什么", "把计算、证据和交付放在同一个会话里")
capabilities = [
    ("质量有依据", "健康评分、问题清单与字段类型来自确定性计算，避免只给结论不解释。"),
    ("清洗可回退", "原始数据始终保留，清洗动作先预览后执行，结果异常时可以撤销重来。"),
    ("交付可复用", "输出清洗工作簿、分析工作簿和 AI 报告，方便继续编辑、复核和分享。"),
]
cols = st.columns(3)
for col, (title, desc) in zip(cols, capabilities, strict=True):
    with col:
        st.markdown(f'<div class="aec-card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)

with st.expander("隐私与安全说明", expanded=False):
    st.markdown(
        """
        - **本地模式**：数据不发送给任何模型，仅使用本地计算与模板报告。
        - **安全 AI 模式**：只发送字段名、汇总统计、趋势和异常摘要，不发送完整记录。
        - **增强 AI 模式**：明确选择后才附加每个字段最多 3 个样例值。

        API 密钥仅存放在环境变量或 Streamlit Secrets 中。财务、医疗、人事等敏感数据请先确认组织政策与授权范围。
        """
    )

render_footer()
logger.debug("home page rendered")
