"""清洗页 AppTest：守卫、预览、执行、撤销全交互。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.profiler import profile

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "3_数据清洗.py"

_DIRTY_DF = pd.DataFrame(
    {
        "销售日期": ["2024/1/5", "2024-01-06", "2024年2月1日", "20240108", "20240108"],
        "订单号": ["ORD-001", "ORD-002", "ORD-003", "ORD-004", "ORD-004"],
        "地区": [" 华东 ", "华北", "华东", "华南", "华南"],
        "销售额": ["￥1,234.50", "567", "1,000", None, None],
        "备注": ["正常", "加急", "", "正常", "正常"],
    }
)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def _load(at: AppTest) -> None:
    at.session_state["uploaded_name"] = "dirty.csv"
    at.session_state["raw_df"] = _DIRTY_DF
    at.session_state["profile"] = profile(_DIRTY_DF)
    at.run()


def test_guard_without_upload(at: AppTest) -> None:
    at.run()
    assert not at.exception
    infos = "\n".join(str(i.value) for i in at.info)
    assert "文件上传" in infos


def test_guard_without_profile(at: AppTest) -> None:
    at.session_state["raw_df"] = _DIRTY_DF
    at.run()
    assert not at.exception
    infos = "\n".join(str(i.value) for i in at.info)
    assert "数据体检" in infos


def test_preview_execute_undo_flow(at: AppTest) -> None:
    _load(at)
    assert not at.exception

    # 表单默认勾选：空白行/列、清理文本 → 预览
    preview = [b for b in at.button if b.label == "预览变更"]
    assert preview
    preview[0].click().run()
    assert not at.exception
    plan = at.session_state["cleaning_plan"]
    assert plan is not None
    assert [a.action for a in plan.actions] == ["删除空白行", "删除空白列", "清理文本"]
    assert at.session_state["clean_df"] is None  # 预览不执行

    # 执行清洗（form 内第二个提交按钮，用当前表单值重建计划）
    exec_btn = [b for b in at.button if b.label == "执行清洗"]
    assert exec_btn
    exec_btn[0].click().run()
    assert not at.exception
    clean_df: pd.DataFrame = at.session_state["clean_df"]
    log = at.session_state["cleaning_log"]
    # 默认只选空白行/列 + 清理文本：数据无空白行/列 → 行数不变
    assert log.rows_before == 5
    assert log.rows_after == 5
    # 清理文本后"地区"列无首尾空格
    assert clean_df["地区"].str.strip().eq(clean_df["地区"]).all()
    assert len(log.actions) == 3

    # 撤销
    undo = [b for b in at.button if b.label == "撤销清洗并重新选择"]
    assert undo
    undo[0].click().run()
    assert not at.exception
    assert at.session_state["clean_df"] is None
    assert at.session_state["cleaning_log"] is None


def test_execute_with_deduplicate(at: AppTest) -> None:
    _load(at)
    # 勾选"删除完整重复记录"
    dup_box = [c for c in at.checkbox if c.label == "删除完整重复记录"]
    assert dup_box
    dup_box[0].check().run()
    exec_btn = [b for b in at.button if b.label == "执行清洗"][0]
    exec_btn.click().run()
    assert not at.exception
    log = at.session_state["cleaning_log"]
    assert log.rows_after == 4  # 空白行/列不触发；重复 1 行被删（5→4）


def test_changed_form_executes_new_plan(at: AppTest) -> None:
    """表单改动后直接执行：必须使用当前表单值（回归：旧计划误执行）。"""
    _load(at)
    # 先预览（计划 1：无去重）
    [b for b in at.button if b.label == "预览变更"][0].click().run()
    plan1 = at.session_state["cleaning_plan"]
    assert "删除重复行" not in [a.action for a in plan1.actions]

    # 勾选去重后不预览直接执行 → 应执行含去重的新计划
    dup_box = [c for c in at.checkbox if c.label == "删除完整重复记录"][0]
    dup_box.check().run()
    [b for b in at.button if b.label == "执行清洗"][0].click().run()
    assert not at.exception
    log = at.session_state["cleaning_log"]
    assert "删除重复行" in [a.action for a in log.actions]
    assert log.rows_after == 4
