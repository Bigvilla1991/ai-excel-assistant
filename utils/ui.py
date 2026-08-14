"""Shared UI primitives for the AI Excel workspace.

The calculation layer intentionally stays independent from Streamlit.  This
module owns the visual shell, task navigation, page guards and user-facing
error language so every page behaves like one product instead of a collection
of scripts.
"""

from __future__ import annotations

import html
import logging

import streamlit as st

from utils.errors import AppError
from utils.logger import log_error_safe

_AI_MODE_LABELS = {
    "secure": "安全 AI（默认）",
    "enhanced": "增强 AI",
    "local": "本地模式",
}

STEPS = ["文件上传", "数据体检", "数据清洗", "数据分析", "AI 洞察", "结果导出"]
_STEP_ICONS = ["📁", "🔍", "🧹", "📈", "✨", "📦"]
_PAGE_PATHS = [
    "pages/1_文件上传.py",
    "pages/2_数据体检.py",
    "pages/3_数据清洗.py",
    "pages/4_数据分析.py",
    "pages/5_AI洞察.py",
    "pages/6_结果导出.py",
]
_PRIVACY_PATH = "pages/7_隐私与说明.py"

# Public UI surface kept explicit for Streamlit Cloud and static import tooling.
__all__ = [
    "apply_theme",
    "handle_exception",
    "render_empty_state",
    "render_footer",
    "render_next_step",
    "render_page_header",
    "render_section_heading",
    "render_session_status",
    "require_analysis",
    "require_profile",
    "require_upload",
]


_THEME_CSS = """
<style>
:root {
  --aec-ink: #162033;
  --aec-muted: #667085;
  --aec-subtle: #98A2B3;
  --aec-line: #E4E7EC;
  --aec-surface: #FFFFFF;
  --aec-canvas: #F7F8FA;
  --aec-brand: #315EFB;
  --aec-brand-strong: #2447C7;
  --aec-brand-soft: #EEF3FF;
  --aec-success: #16845B;
  --aec-warning: #B54708;
  --aec-danger: #B42318;
}

/* Keep the canvas calm and reserve emphasis for the current task. */
.stApp { background: var(--aec-canvas); color: var(--aec-ink); }
[data-testid="stHeader"] { background: var(--aec-canvas); z-index: 1000000; }
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #FBFCFE; border-right: 1px solid var(--aec-line); }
[data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
[data-testid="stMainBlockContainer"] { max-width: 1240px; padding-top: 4rem; padding-bottom: 3rem; }

.aec-brand { padding: .15rem .2rem .85rem; }
.aec-brand-mark { display: flex; align-items: center; gap: .55rem; color: var(--aec-ink); font-size: 1.05rem; font-weight: 760; letter-spacing: -.02em; }
.aec-brand-mark span { display: grid; place-items: center; width: 1.8rem; height: 1.8rem; border-radius: .55rem; color: white; background: var(--aec-brand); box-shadow: 0 6px 14px rgba(49,94,251,.2); }
.aec-brand-sub { margin: .42rem 0 0 2.35rem; color: var(--aec-subtle); font-size: .72rem; }
.aec-file-state { margin: .35rem 0 .9rem; padding: .7rem .75rem; border: 1px solid var(--aec-line); border-radius: .75rem; background: var(--aec-surface); }
.aec-file-state strong { display: block; overflow: hidden; color: var(--aec-ink); font-size: .78rem; text-overflow: ellipsis; white-space: nowrap; }
.aec-file-state small { color: var(--aec-muted); font-size: .7rem; }
.aec-nav-label { margin: 1rem 0 .35rem; color: var(--aec-subtle); font-size: .68rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.aec-nav-status { margin: .2rem 0 .5rem; color: var(--aec-muted); font-size: .72rem; }

.aec-hero { padding: 1.2rem 0 1.4rem; }
.aec-eyebrow { margin-bottom: .7rem; color: var(--aec-brand); font-size: .74rem; font-weight: 750; letter-spacing: .11em; text-transform: uppercase; }
.aec-hero h1 { max-width: 760px; margin: 0; color: var(--aec-ink); font-size: clamp(2.2rem, 5vw, 3.8rem); font-weight: 820; letter-spacing: -.055em; line-height: 1.03; }
.aec-hero p { max-width: 690px; margin: 1rem 0 0; color: var(--aec-muted); font-size: 1.05rem; line-height: 1.7; }
.aec-hero-meta { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.2rem; }
.aec-meta-pill { padding: .32rem .6rem; border: 1px solid var(--aec-line); border-radius: 999px; background: var(--aec-surface); color: var(--aec-muted); font-size: .74rem; }

.aec-page-title { margin: .2rem 0 1.25rem; }
.aec-page-title h1 { margin: 0; color: var(--aec-ink); font-size: clamp(1.7rem, 3vw, 2.2rem); font-weight: 800; letter-spacing: -.04em; line-height: 1.15; }
.aec-page-title p { max-width: 760px; margin: .45rem 0 0; color: var(--aec-muted); font-size: .94rem; line-height: 1.55; }
.aec-stepper { display: flex; align-items: flex-start; gap: .35rem; margin: .2rem 0 1rem; overflow-x: auto; padding-bottom: .35rem; }
.aec-step-item { display: flex; min-width: 7.2rem; align-items: center; gap: .45rem; color: var(--aec-muted); font-size: .73rem; white-space: nowrap; }
.aec-step-item::after { content: ""; width: 1.7rem; height: 1px; margin-left: .15rem; background: var(--aec-line); }
.aec-step-item:last-child::after { display: none; }
.aec-step-dot { display: grid; flex: 0 0 auto; place-items: center; width: 1.65rem; height: 1.65rem; border: 1px solid var(--aec-line); border-radius: 50%; background: var(--aec-surface); font-size: .72rem; }
.aec-step-item.is-done { color: var(--aec-success); }
.aec-step-item.is-done .aec-step-dot { border-color: #A6F4C5; background: #ECFDF3; }
.aec-step-item.is-active { color: var(--aec-brand-strong); font-weight: 700; }
.aec-step-item.is-active .aec-step-dot { border-color: var(--aec-brand); background: var(--aec-brand); color: #fff; box-shadow: 0 0 0 4px var(--aec-brand-soft); }

.aec-section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin: 1.35rem 0 .7rem; }
.aec-section-head h2 { margin: 0; color: var(--aec-ink); font-size: 1.08rem; letter-spacing: -.02em; }
.aec-section-head p { margin: 0; color: var(--aec-muted); font-size: .78rem; }
.aec-card { height: 100%; padding: 1rem 1.05rem; border: 1px solid var(--aec-line); border-radius: .85rem; background: var(--aec-surface); box-shadow: 0 1px 2px rgba(16,24,40,.02); }
.aec-card h3 { margin: 0 0 .45rem; color: var(--aec-ink); font-size: .94rem; font-weight: 730; letter-spacing: -.01em; }
.aec-card p { margin: 0; color: var(--aec-muted); font-size: .8rem; line-height: 1.6; }
.aec-card .aec-card-kicker { margin-bottom: .65rem; color: var(--aec-brand); font-size: .72rem; font-weight: 750; }
.aec-action-card { padding: 1.2rem; border: 1px solid #C9D5FF; border-radius: 1rem; background: linear-gradient(135deg, #F7F9FF 0%, #FFFFFF 68%); }
.aec-action-card h2 { margin: 0; color: var(--aec-ink); font-size: 1.15rem; letter-spacing: -.025em; }
.aec-action-card p { max-width: 640px; margin: .35rem 0 1rem; color: var(--aec-muted); font-size: .84rem; line-height: 1.55; }
.aec-kpi-note { margin-top: .28rem; color: var(--aec-muted); font-size: .72rem; }
.aec-empty { padding: 1.45rem; border: 1px dashed #C8D0DC; border-radius: .9rem; background: rgba(255,255,255,.65); text-align: center; }
.aec-empty h3 { margin: 0 0 .35rem; color: var(--aec-ink); font-size: 1rem; }
.aec-empty p { margin: 0; color: var(--aec-muted); font-size: .82rem; }
.aec-footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--aec-line); color: var(--aec-subtle); font-size: .72rem; text-align: center; }

.stButton > button, .stDownloadButton > button { min-height: 2.55rem; border-radius: .65rem; font-weight: 680; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { border-color: var(--aec-brand); background: var(--aec-brand); box-shadow: 0 5px 12px rgba(49,94,251,.18); }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { border-color: var(--aec-brand-strong); background: var(--aec-brand-strong); }
.stButton > button:not([kind="primary"]), .stDownloadButton > button:not([kind="primary"]) { border-color: var(--aec-line); background: var(--aec-surface); }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible, input:focus-visible { outline: 3px solid rgba(49,94,251,.28); outline-offset: 2px; }
div[data-testid="stMetric"] { min-height: 5.2rem; padding: .85rem .95rem; border: 1px solid var(--aec-line); border-radius: .8rem; background: var(--aec-surface); box-shadow: 0 1px 2px rgba(16,24,40,.02); }
div[data-testid="stMetric"] label { color: var(--aec-muted); font-size: .74rem; }
div[data-testid="stMetricValue"] { color: var(--aec-ink); font-size: 1.25rem; }
div[data-testid="stDataFrame"] { border: 1px solid var(--aec-line); border-radius: .75rem; overflow: hidden; }
div[data-testid="stForm"], div[data-testid="stExpander"] { border-color: var(--aec-line); border-radius: .85rem; }
[data-testid="stAlert"] { border-radius: .7rem; }
.stProgress > div > div > div { background: var(--aec-brand); }
@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"] { padding: 4rem .8rem 2.5rem; }
  .aec-step-item { min-width: 6.4rem; }
  .aec-step-item::after { width: .8rem; }
  .aec-hero h1 { font-size: 2.35rem; }
}
</style>
"""


def apply_theme() -> None:
    """Inject the shared design tokens and component styles."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _completed_steps() -> set[int]:
    completed: set[int] = set()
    if st.session_state.get("raw_df") is not None:
        completed.add(1)
    if st.session_state.get("profile") is not None:
        completed.add(2)
    if st.session_state.get("clean_df") is not None:
        completed.add(3)
    if st.session_state.get("analysis") is not None:
        completed.add(4)
    if st.session_state.get("ai_report") is not None:
        completed.add(5)
    return completed


def _safe_page_link(path: str, label: str, icon: str) -> None:
    """Render a navigation link while keeping AppTest/from_string robust."""
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:
        # A standalone page unit test may not have the multipage router context.
        st.caption(f"{icon} {label}")


def render_session_status(step: int | None = None) -> None:
    """Render product navigation and a compact, persistent session summary."""
    with st.sidebar:
        st.markdown(
            '<div class="aec-brand"><div class="aec-brand-mark"><span>▦</span>AI Excel 助手</div>'
            '<div class="aec-brand-sub">从原始表格到可交付结论</div></div>',
            unsafe_allow_html=True,
        )
        _safe_page_link("app.py", "工作台", "⌂")
        st.markdown('<div class="aec-nav-label">工作流</div>', unsafe_allow_html=True)
        completed = _completed_steps()
        for index, (name, path, icon) in enumerate(
            zip(STEPS, _PAGE_PATHS, _STEP_ICONS, strict=True), start=1
        ):
            marker = "✓" if index in completed else str(index)
            _safe_page_link(path, f"{marker}  {name}", icon)

        st.markdown('<div class="aec-nav-label">当前会话</div>', unsafe_allow_html=True)
        if st.session_state.get("raw_df") is not None:
            df = st.session_state.raw_df
            name = html.escape(str(st.session_state.get("uploaded_name") or "未命名文件"))
            try:
                dimensions = f"{len(df):,} 行 × {df.shape[1]:,} 列"
            except (TypeError, AttributeError, IndexError):
                dimensions = "已载入数据"
            st.markdown(
                f'<div class="aec-file-state"><strong title="{name}">📄 {name}</strong>'
                f"<small>{dimensions}</small></div>",
                unsafe_allow_html=True,
            )
            st.caption(f"📄 已载入：{st.session_state.get('uploaded_name')}")
        else:
            st.caption("尚未载入数据")
        mode = st.session_state.get("ai_mode", "secure")
        st.caption(f"✨ AI 模式：{_AI_MODE_LABELS.get(mode, mode)}")
        if step is not None and 1 <= step <= len(STEPS):
            st.caption(f"📍 当前：第 {step} 步 · {STEPS[step - 1]}")
        st.markdown('<div class="aec-nav-label">帮助</div>', unsafe_allow_html=True)
        _safe_page_link(_PRIVACY_PATH, "隐私与说明", "🔒")


def render_page_header(title: str, subtitle: str = "", step: int | None = None) -> None:
    """Render a consistent page title and task progress indicator."""
    if step is not None:
        completed = _completed_steps()
        items: list[str] = []
        for index, name in enumerate(STEPS, start=1):
            state = "is-active" if index == step else "is-done" if index in completed else ""
            marker = "✓" if index in completed and index != step else str(index)
            items.append(
                f'<div class="aec-step-item {state}"><span class="aec-step-dot">{marker}</span>'
                f'<span>{name}</span></div>'
            )
        st.markdown(f'<div class="aec-stepper">{"".join(items)}</div>', unsafe_allow_html=True)
    subtitle_html = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="aec-page-title"><h1>{html.escape(title)}</h1>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, description: str = "") -> None:
    desc = f"<p>{html.escape(description)}</p>" if description else ""
    st.markdown(f'<div class="aec-section-head"><h2>{html.escape(title)}</h2>{desc}</div>', unsafe_allow_html=True)


def render_empty_state(title: str, description: str, page: str | None = None, label: str = "开始") -> None:
    st.markdown(
        f'<div class="aec-empty"><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></div>',
        unsafe_allow_html=True,
    )
    if page:
        _safe_page_link(page, label, "→")


def render_next_step(step: int, description: str = "") -> None:
    if not 1 <= step <= len(STEPS):
        return
    text = description or f"准备好后进入「{STEPS[step - 1]}」。"
    st.markdown(f'<div class="aec-kpi-note">下一步：{html.escape(text)}</div>', unsafe_allow_html=True)
    _safe_page_link(_PAGE_PATHS[step - 1], f"进入「{STEPS[step - 1]}」", _STEP_ICONS[step - 1])


def render_footer() -> None:
    st.markdown(
        '<div class="aec-footer">AI Excel 数据处理助手 V1.1 ｜ Python 负责准确计算，AI 负责解释结果 ｜ '
        "结果仅供参考，不视为专业审计或决策依据</div>",
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
    """Render safe user-facing error language and optionally stop the page."""
    if isinstance(exc, AppError):
        st.error(message or str(exc))
    else:
        log_error_safe(logger, exc, context)
        st.error(message or f"{context}失败，请检查数据后重试。")
    if fatal:
        st.stop()


def require_upload() -> None:
    if st.session_state.get("raw_df") is None:
        st.info("请先在「文件上传」页面载入文件，完成解析后再继续。")
        _safe_page_link(_PAGE_PATHS[0], "去文件上传", "📁")
        st.stop()


def require_profile() -> None:
    if st.session_state.get("profile") is None:
        st.info("请先进入「数据体检」页面，系统才能给出清洗建议。")
        _safe_page_link(_PAGE_PATHS[1], "去数据体检", "🔍")
        st.stop()


def require_analysis() -> None:
    if st.session_state.get("analysis") is None:
        st.info("请先进入「数据分析」页面完成一次分析，再生成可追溯的洞察报告。")
        _safe_page_link(_PAGE_PATHS[3], "去数据分析", "📈")
        st.stop()
