"""体检页 AppTest：守卫、评分渲染、结果缓存、问题清单。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "2_数据体检.py"

_DITY_DF = pd.DataFrame(
    {
        "销售日期": ["2024/1/5", "2024-01-06", "2024年2月1日", "20240108", "不是日期"],
        "订单号": ["ORD-001", "ORD-002", "ORD-003", "ORD-004", "ORD-005"],
        "地区": ["华东", "华北", "华东", "华南", "西南"],
        "销售额": [100.5, 200.0, 300.0, 400.0, 999999.0],
        "备注": [None, "加急", "", "正常", "其他"],
    }
)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def _load_data(at: AppTest, df: pd.DataFrame) -> None:
    at.session_state["uploaded_name"] = "test.csv"
    at.session_state["raw_df"] = df
    at.run()


def test_guard_without_upload(at: AppTest) -> None:
    at.run()
    assert not at.exception
    assert at.session_state["raw_df"] is None
    infos = "\n".join(str(i.value) for i in at.info)
    assert "文件上传" in infos
    assert not at.metric  # 未计算评分


def test_quality_page_renders_result(at: AppTest) -> None:
    _load_data(at, _DITY_DF)
    assert not at.exception
    assert at.session_state["profile"] is not None

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["健康评分"] == "95"
    assert metrics["总行数"] == "5"
    assert metrics["列数"] == "5"
    assert metrics["重复行"] == "0"

    # 95 分 → 良好等级提示（success），且类型冲突问题在警告中
    successes = "\n".join(str(s.value) for s in at.success)
    assert "良好" in successes
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "混合类型" in warnings

    # 字段表渲染
    assert at.dataframe
    assert len(at.dataframe) >= 1


def test_score_stable_across_reruns(at: AppTest) -> None:
    """健康评分在多次渲染间稳定且复用缓存（只计算一次）。"""
    _load_data(at, _DITY_DF)
    first_profile = at.session_state["profile"]
    first_score = at.session_state["profile"].health_score

    at.run()  # 再次渲染（模拟交互触发 rerun）
    assert not at.exception
    assert at.session_state["profile"] is first_profile  # 缓存复用，未重算
    assert at.session_state["profile"].health_score == first_score


def test_clean_data_shows_success(at: AppTest) -> None:
    clean = pd.DataFrame(
        {"销售日期": ["2024/1/5", "2024/1/6"], "地区": ["华东", "华北"], "销售额": [100.5, 200.0]}
    )
    _load_data(at, clean)
    assert not at.exception
    assert at.session_state["profile"].health_score == 100
    successes = "\n".join(str(s.value) for s in at.success)
    assert "未发现明显问题" in successes or "良好" in successes
