"""UI 工具：主题、统一错误处理、页面守卫、页头、侧边栏会话状态。

约定（方案 §17.2）：
- AppError（业务错误）→ 直接展示其可读消息；
- 其他异常 → 泛化提示 + 脱敏日志（不向用户暴露 traceback）；
- 页面守卫统一文案，未完成前置步骤时给出可执行指引；
- 主题与页头组件统一视觉规范（现代 SaaS 简洁风）。
"""

from __future__ import annotations

import logging

import streamlit as st

from utils.errors import AppError
from utils.logger import log_error_safe

_AI_MODE_LABELS = {
    "secure": "安全 AI（默认）",
    "enhanced": "增强 AI",
    "local": "本地模式",
}

# 流程步骤定义（侧边栏/页头指示器共用）
STEPS = ["文件上传", "数据体检", "数据清洗", "数据分析", "AI 洞察", "结果导出"]

# 侧边栏品牌区
_BRAND_SIDEBAR = """
<div style="padding: 2px 0 10px 0;">
  <div style="font-size: 1.15rem; font-weight: 800; color: #4F46E5; letter-spacing: -0.01em;">
    📊 AI Excel 助手
  </div>
  <div style="font-size: 0.78rem; color: #94A3B8;">上传 · 体检 · 清洗 · 分析 · 解读 · 导出</div>
</div>
"""


def render_session_status(step: int | None = None) -> None:
    """侧边栏会话状态：品牌 + 已载入文件 + AI 模式 + 当前步骤。"""
    with st.sidebar:
        st.markdown(_BRAND_SIDEBAR, unsafe_allow_html=True)
        st.divider()
        if st.session_state.raw_df is not None:
            st.caption(f"📄 已载入：{st.session_state.uploaded_name}")
        mode = st.session_state.ai_mode
        st.caption(f"🤖 AI 模式：{_AI_MODE_LABELS.get(mode, mode)}")
        if step is not None:
            st.caption(f"📍 当前：第 {step} 步 · {STEPS[step - 1]}")


# 全局品牌 CSS（一次性注入，幂等）
_THEME_CSS = """
<style>
/* ---- 全局 ----
.aec-hero  首页 Hero 区
.aec-card  通用卡片（能力卡/上传卡/页脚）
.aec-step  步骤指示器（active 高亮）
*/

.aec-hero {
  padding: 36px 8px 16px 8px;
}
.aec-hero h1 {
  font-size: 2.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 10px 0;
  background: linear-gradient(120deg, #4F46E5 0%, #0EA5E9 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.aec-hero p {
  font-size: 1.1rem;
  color: #475569;
  margin: 0 0 20px 0;
}

.aec-card {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 14px;
  padding: 18px 18px 14px 18px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  height: 100%;
  transition: box-shadow 0.15s ease;
}
.aec-card:hover {
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.10);
}
.aec-card h3 {
  font-size: 1rem;
  font-weight: 700;
  color: #0F172A;
  margin: 8px 0 6px 0;
}
.aec-card p {
  font-size: 0.88rem;
  color: #64748B;
  margin: 0;
  line-height: 1.55;
}

.aec-steps {
  display: flex;
  gap: 6px;
  margin: 18px 0 6px 0;
  flex-wrap: wrap;
}
.aec-step {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.8rem;
  color: #94A3B8;
  background: #F1F5F9;
  border-radius: 999px;
  padding: 4px 12px;
  white-space: nowrap;
}
.aec-step.active {
  color: #FFFFFF;
  background: #4F46E5;
  font-weight: 600;
}

.aec-page-title {
  margin-top: 4px;
}
.aec-page-title h1 {
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}
.aec-page-title p {
  color: #64748B;
  margin-top: 0;
}

.aec-footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid #E2E8F0;
  color: #94A3B8;
  font-size: 0.8rem;
  text-align: center;
}

/* ---- 组件细节 ----
按钮：圆角 + 主按钮渐变
metric：卡片化
表格/输入：圆角
*/
.stButton > button {
  border-radius: 10px;
  font-weight: 600;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(120deg, #4F46E5 0%, #6366F1 100%);
  border: none;
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.25);
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
}

div[data-testid="stMetric"] {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
div[data-testid="stMetric"] label {
  color: #64748B;
}

div[data-testid="stDataFrame"] {
  border-radius: 10px;
  border: 1px solid #E2E8F0;
  overflow: hidden;
}
</style>
"""


def apply_theme() -> None:
    """注入全局品牌样式（幂等；每个页面脚本顶部调用）。"""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str = "", step: int | None = None) -> None:
    """统一页头：标题 + 副标题 + 流程步骤指示器（step 从 1 开始）。"""
    if step is not None:
        pills = "".join(
            f'<span class="aec-step{" active" if i == step else ""}">{i}. {name}</span>'
            for i, name in enumerate(STEPS, start=1)
        )
        st.markdown(f'<div class="aec-steps">{pills}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(
            f'<div class="aec-page-title"><h1>{title}</h1><p>{subtitle}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="aec-page-title"><h1>{title}</h1></div>', unsafe_allow_html=True)


def render_footer() -> None:
    """页脚（版本与免责声明）。"""
    st.markdown(
        '<div class="aec-footer">AI Excel 数据处理助手 V1.0 ｜ '
        "Python 负责准确计算，AI 负责解释结果 ｜ 本工具结果仅供参考，不视为专业审计或决策依据</div>",
        unsafe_allow_html=True,
    )


def handle_exception(
    exc: Exception,
    logger: logging.Logger,
    context: str,
    *,
    message: str | None = None,
    fatal: bool = True,
) -> None:
    """统一错误渲染。

    - AppError → 展示其可读消息（可用 message 覆盖）；
    - 其他异常 → 脱敏日志 + 泛化提示（message 未提供时）；
    - fatal=True（默认）→ 展示后 st.stop()；
      致命性低、页面可继续渲染的路径传 fatal=False。
    """
    if isinstance(exc, AppError):
        st.error(message or str(exc))
    else:
        log_error_safe(logger, exc, context)
        st.error(message or f"{context}失败，请检查数据后重试。")
    if fatal:
        st.stop()


def require_upload() -> None:
    """页面守卫：必须先上传并确认数据。"""
    if st.session_state.raw_df is None:
        st.info("请先在「① 文件上传」页上传并确认数据。")
        st.stop()


def require_profile() -> None:
    """页面守卫：必须先完成数据体检。"""
    if st.session_state.profile is None:
        st.info("请先进入「② 数据体检」生成体检结果。")
        st.stop()


def require_analysis() -> None:
    """页面守卫：必须先完成一次数据分析。"""
    if st.session_state.analysis is None:
        st.info("请先进入「④ 数据分析」完成一次分析（选择指标与维度）。")
        st.stop()
