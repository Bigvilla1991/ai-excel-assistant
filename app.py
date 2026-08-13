"""AI Excel 数据处理助手 —— 首页（Hero + 能力卡片 + 上传入口 + 隐私提示）。"""

from __future__ import annotations

import streamlit as st

from utils.logger import get_logger
from utils.session import init_session_state
from utils.ui import apply_theme, render_footer

init_session_state()
apply_theme()
logger = get_logger("home")

st.set_page_config(
    page_title="AI Excel 数据处理助手",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---- Hero ----
st.markdown(
    """
    <div class="aec-hero">
      <h1>AI Excel 数据处理助手</h1>
      <p>上传文件 → 数据体检 → 一键清洗 → 统计分析 → AI 解读 → 导出结果，<br>
      把高频、重复、容易出错的 Excel 整理工作，变成几分钟的可复用流程。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- 六步流程 ----
st.markdown("#### 完整工作流")
flow = [
    ("① 文件上传", "XLSX / CSV，自动识别编码与工作表"),
    ("② 数据体检", "空值、重复、异常值，健康评分"),
    ("③ 数据清洗", "去重、格式统一、缺失策略，可撤销"),
    ("④ 数据分析", "分组、排名、趋势，口径与 Excel 一致"),
    ("⑤ AI 洞察", "固定结构报告，数字可溯源防幻觉"),
    ("⑥ 结果导出", "Excel / Markdown / HTML，开箱可用"),
]
cols = st.columns(6)
for col, (title, desc) in zip(cols, flow, strict=True):
    with col:
        st.markdown(
            f'<div class="aec-card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True
        )

st.write("")

# ---- 能力卡片（3 大卡）----
st.markdown("#### 核心能力")
capabilities = [
    (
        "🔍 体检与清洗",
        "自动识别字段类型（编号列不参与求和）、IQR 异常检测、中文日期兼容、健康评分与问题清单；"
        "去重、金额归一化（￥1,234.50→1234.5）、统一日期、缺失值策略，全程预览可撤销。",
    ),
    (
        "📈 统计与图表",
        "基础统计、维度分组、TOP/BOTTOM 排名、按日/周/月/季趋势（含环比），口径与 Excel 透视表一致；"
        "折线（峰值标注）、柱状、横向排名、散点交互图表，与汇总表同源可追溯。",
    ),
    (
        "🤖 解读与导出",
        "DeepSeek 生成固定 7 段报告，只发送结构化汇总、数字交叉校验防幻觉，无密钥自动用本地模板；"
        "9 Sheet 分析工作簿、公式注入防护、Markdown/HTML 报告，本地模式完全离线。",
    ),
]
cols = st.columns(3)
for col, (title, desc) in zip(cols, capabilities, strict=True):
    with col:
        st.markdown(
            f'<div class="aec-card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True
        )

st.write("")

# ---- 上传入口（卡片容器）----
with st.container(border=True):
    st.markdown("#### 开始使用")
    uploaded = st.file_uploader(
        "选择 Excel（.xlsx）或 CSV 文件",
        type=["xlsx", "csv"],
        help="单文件不超过 20MB，建议不超过 10 万行。超出时系统会提示，不会卡死。",
    )
    if uploaded is not None:
        st.success(f"已选择：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")
        st.markdown("👉 请前往侧边栏 **「① 文件上传」** 页面完成解析与预览。")
    else:
        st.caption(
            "未选择文件。可先运行 `python scripts\\generate_sample_data.py` 生成演示数据体验完整流程。"
        )

# ---- 隐私提示 ----
st.divider()
with st.expander("隐私与安全说明", expanded=False):
    st.markdown(
        """
        - **本地模式**：数据不发送给任何模型，仅本地计算 + 模板报告
        - **安全 AI 模式（默认）**：仅发送字段名、汇总统计、趋势和异常摘要，不发送完整记录
        - **增强 AI 模式**：经你明确同意后，才发送每字段最多 3 个样例值

        API 密钥仅存放于环境变量（`.env`）或 Streamlit Cloud Secrets，不进入代码库。
        对财务、医疗、人事等敏感数据，请先确认组织政策与数据授权。
        """
    )

render_footer()

logger.debug("home page rendered")
