"""会话状态语义单测：reset_downstream 数据/偏好键分离。"""

from __future__ import annotations

import pytest
import streamlit as st

from utils.session import reset_downstream


@pytest.fixture(autouse=True)
def _clean_state():
    """每个测试前清空会话状态（数据键 + 偏好键）。"""
    yield
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def test_reset_clears_data_keeps_preferences() -> None:
    st.session_state["ai_mode"] = "enhanced"
    st.session_state["raw_df"] = object()
    st.session_state["analysis"] = {"x": 1}

    reset_downstream("raw_df")

    assert "raw_df" not in st.session_state
    assert "analysis" not in st.session_state
    assert "profile" not in st.session_state
    assert st.session_state["ai_mode"] == "enhanced"  # 偏好保留


def test_reset_partial_from_later_key() -> None:
    st.session_state["clean_df"] = object()
    st.session_state["analysis"] = {"x": 1}

    reset_downstream("clean_df")

    assert "clean_df" not in st.session_state
    assert "analysis" not in st.session_state
    assert "ai_report" not in st.session_state


def test_reset_keeps_earlier_keys() -> None:
    st.session_state["uploaded_name"] = "a.csv"
    st.session_state["raw_df"] = object()

    reset_downstream("profile")  # 起点在 raw_df 之后

    assert st.session_state["uploaded_name"] == "a.csv"
    assert st.session_state["raw_df"] is not None


def test_reset_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="未知数据键"):
        reset_downstream("ai_mode")  # 偏好键不能作起点
    with pytest.raises(ValueError, match="未知数据键"):
        reset_downstream("nope")
