"""UI 工具：统一错误处理、页面守卫、侧边栏会话状态。

约定（方案 §17.2）：
- AppError（业务错误）→ 直接展示其可读消息；
- 其他异常 → 泛化提示 + 脱敏日志（不向用户暴露 traceback）；
- 页面守卫统一文案，未完成前置步骤时给出可执行指引。
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


def render_session_status() -> None:
    """侧边栏会话状态：已载入文件 + 当前 AI 模式（5 个功能页调用）。"""
    with st.sidebar:
        st.divider()
        if st.session_state.raw_df is not None:
            st.caption(f"📄 已载入：{st.session_state.uploaded_name}")
        mode = st.session_state.ai_mode
        st.caption(f"🤖 AI 模式：{_AI_MODE_LABELS.get(mode, mode)}")
