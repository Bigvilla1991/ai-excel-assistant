"""AI Excel 数据处理助手 —— 首页（产品说明 + 上传入口 + 隐私提示）。"""

from __future__ import annotations

import streamlit as st

from utils.logger import get_logger

logger = get_logger("home")

st.set_page_config(
    page_title="AI Excel 数据处理助手",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.title("AI Excel 数据处理助手")
st.caption("上传文件 → 数据体检 → 一键清洗 → 统计分析 → AI 解读 → 导出结果")

st.markdown(
    """
    面向行政、销售、运营、财务辅助人员和小微企业经营者，把高频、重复、容易出错的
    Excel 数据整理工作变成可复用的流程。
    """
)

# ---- 能力列表 ----
st.subheader("能做什么")
st.markdown(
    """
    - **数据体检**：自动识别行列、字段类型、空值、重复记录和异常值，并给出健康评分
    - **一键清洗**：去重、格式统一、缺失值策略、金额归一化，全程可撤销
    - **统计分析**：基础统计、维度分组、TOP/BOTTOM 排名、按日/周/月/季的趋势
    - **图表展示**：折线、柱状、横向排名、散点，交互式查看
    - **AI 解读**：基于结构化统计结果生成固定格式报告（可关闭）
    - **结果导出**：清洗数据、多 Sheet 分析工作簿、HTML 报告
    """
)

# ---- 文件上传入口 ----
st.divider()
st.subheader("开始使用")
uploaded = st.file_uploader(
    "选择 Excel（.xlsx）或 CSV 文件",
    type=["xlsx", "csv"],
    help="单文件不超过 20MB，建议不超过 10 万行。超出时系统会提示，不会卡死。",
)
if uploaded is not None:
    st.success(f"已选择：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")
    st.markdown("👉 请前往侧边栏 **「1 · 文件上传」** 页面完成解析与预览。")
else:
    st.info("未选择文件。可先使用示例数据体验，或前往侧边栏「1 · 文件上传」。")

# ---- 隐私提示 ----
st.divider()
st.subheader("隐私与安全")
st.markdown(
    """
    - **本地模式**：数据不发送给任何模型，仅本地计算 + 模板报告
    - **安全 AI 模式（默认）**：仅发送字段名、汇总统计、趋势和异常摘要，不发送完整记录
    - **增强 AI 模式**：经你明确同意后，才发送少量脱敏样本

    API 密钥仅存放于环境变量（`.env`）或 Streamlit Cloud Secrets，不进入代码库。
    对财务、医疗、人事等敏感数据，请先确认组织政策与数据授权。
    """
)

logger.debug("home page rendered")
