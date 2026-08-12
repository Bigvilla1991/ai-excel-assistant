"""UI 工具单测：统一错误处理、页面守卫、侧边栏状态。"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

PAGE = __file__


def test_handle_exception_app_error_shows_message() -> None:
    """AppError → 直接展示其可读消息。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.errors import FileValidationError\n"
        "from utils.ui import handle_exception\n"
        "import logging\n"
        "handle_exception(FileValidationError('文件过大'), logging.getLogger('t'), '上传')\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    errors = "\n".join(str(e.value) for e in at.error)
    assert "文件过大" in errors  # AppError 消息直接展示
    assert "after" not in "\n".join(str(m.value) for m in at.markdown)  # st.stop 生效


def test_require_profile_guard() -> None:
    """已上传未体检 → 提示「②」。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.session import init_session_state\n"
        "from utils.ui import require_profile\n"
        "init_session_state()\n"
        "st.session_state.raw_df = object()\n"
        "require_profile()\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    infos = "\n".join(str(i.value) for i in at.info)
    assert "数据体检" in infos
    assert not any("after" in str(m.value) for m in at.markdown)


def test_require_analysis_guard() -> None:
    """已体检未分析 → 提示「④」。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.session import init_session_state\n"
        "from utils.ui import require_analysis\n"
        "init_session_state()\n"
        "st.session_state.raw_df = object()\n"
        "st.session_state.profile = object()\n"
        "require_analysis()\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    infos = "\n".join(str(i.value) for i in at.info)
    assert "数据分析" in infos


def test_handle_exception_non_fatal_continues() -> None:
    """fatal=False：展示错误后页面继续渲染。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.ui import handle_exception\n"
        "import logging\n"
        "handle_exception(RuntimeError('x'), logging.getLogger('t'), '趋势计算', fatal=False)\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    assert any("趋势计算失败" in str(e.value) for e in at.error)
    assert any("after" in str(m.value) for m in at.markdown)  # 未停止


def test_handle_exception_custom_message() -> None:
    """自定义 message 覆盖泛化文案（AppError 也可覆盖）。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.errors import FileValidationError\n"
        "from utils.ui import handle_exception\n"
        "import logging\n"
        "handle_exception(FileValidationError('原始消息'), logging.getLogger('t'), 'x', message='自定义消息')\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    errors = "\n".join(str(e.value) for e in at.error)
    assert "自定义消息" in errors
    assert "原始消息" not in errors
    """非 AppError → 泛化提示，不暴露内部细节。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.ui import handle_exception\n"
        "import logging\n"
        "handle_exception(RuntimeError('内部错误: 密码 abc123'), logging.getLogger('t'), '清洗')\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    errors = "\n".join(str(e.value) for e in at.error)
    assert "清洗失败" in errors
    assert "abc123" not in errors  # 内部细节不暴露


def test_require_upload_guard() -> None:
    """未上传时守卫提示并停止执行。"""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.session import init_session_state\n"
        "from utils.ui import require_upload\n"
        "init_session_state()\n"
        "require_upload()\n"
        "st.write('after')",
        default_timeout=10,
    )
    at.run()
    infos = "\n".join(str(i.value) for i in at.info)
    assert "文件上传" in infos
    assert not any("after" in str(m.value) for m in at.markdown)  # 已停止


def test_render_session_status_shows_state() -> None:
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from utils.session import init_session_state\n"
        "from utils.ui import render_session_status\n"
        "init_session_state()\n"
        "st.session_state.raw_df = object()\n"
        "st.session_state.uploaded_name = 'a.csv'\n"
        "st.session_state.ai_mode = 'local'\n"
        "render_session_status()",
        default_timeout=10,
    )
    at.run()
    assert not at.exception
    captions = "\n".join(str(c.value) for c in at.sidebar.caption)
    assert "a.csv" in captions
    assert "本地模式" in captions
