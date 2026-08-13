"""隐私与数据处理说明。"""

from __future__ import annotations

import streamlit as st

from utils.session import init_session_state
from utils.ui import (
    apply_theme,
    render_footer,
    render_page_header,
    render_section_heading,
    render_session_status,
)

st.set_page_config(page_title="隐私与说明", page_icon="🔒", layout="wide")
init_session_state()
apply_theme()
render_session_status()

render_page_header("隐私与数据处理", "先了解数据去向，再选择适合当前文件的运行模式。")

render_section_heading("在线演示边界", "上传文件只用于当前会话，不作为长期存储")
with st.container(border=True):
    st.markdown(
        """
        - 请勿上传真实业务敏感数据，包括个人隐私、财务机密和人事信息。
        - 文件只在当前会话中解析、计算和生成导出结果；刷新或会话结束后即释放。
        - 本地模式不会向任何模型发送数据，适合敏感文件或离线处理。
        - 如需处理真实业务数据，建议下载项目并在组织允许的本地环境运行。
        """
    )

render_section_heading("三种运行模式", "模式会影响发送范围，不会改变本地统计口径")
with st.container(border=True):
    st.dataframe(
        [
            {"模式": "本地模式", "数据去向": "不发送给模型", "适用场景": "敏感数据；仅需本地模板报告"},
            {"模式": "安全 AI 模式", "数据去向": "字段名、汇总统计、趋势、异常摘要", "适用场景": "常规业务数据"},
            {"模式": "增强 AI 模式", "数据去向": "安全模式 + 每字段最多 3 个样例值", "适用场景": "需要更细的语义解读"},
        ],
        hide_index=True,
        width="stretch",
    )

st.warning("财务、医疗、人事等敏感数据请先确认组织政策与数据授权；AI 结论不视为专业审计或决策依据。")
render_footer()
