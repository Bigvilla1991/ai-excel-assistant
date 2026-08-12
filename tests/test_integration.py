"""全链路集成测试：上传 → 体检 → 清洗 → 分析 → AI 报告（AppTest 逐页模拟）。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parent.parent / "pages"

_SALES = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东", "华南", "华北", "华东"],
        "销售额": ["100", "200", "300", "400", "500", "600"],
        "订单号": ["A1", "A2", "A3", "A4", "A5", "A6"],
        "日期": [
            "2024-01-05",
            "2024-01-20",
            "2024-02-10",
            "2024-02-15",
            "2024-03-05",
            "2024-03-12",
        ],
    }
)


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _page(name: str) -> AppTest:
    return AppTest.from_file(str(PAGES / name), default_timeout=30)


def test_full_pipeline_upload_to_ai_report() -> None:
    """五页全链路：每步产出正确且可被下游消费。"""
    # ① 上传页（真实交互）
    at1 = _page("1_文件上传.py")
    at1.run()
    at1.file_uploader(key="uploader").set_value(
        (
            "sales.xlsx",
            _xlsx_bytes(_SALES),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ).run()
    assert not at1.exception
    at1.button(key="confirm_btn").click().run()
    assert not at1.exception
    raw_df = at1.session_state["raw_df"]
    assert raw_df.shape == (6, 4)

    # ② 体检页（注入上游 state）
    at2 = _page("2_数据体检.py")
    at2.session_state["uploaded_name"] = "sales.xlsx"
    at2.session_state["raw_df"] = raw_df
    at2.run()
    assert not at2.exception
    profile = at2.session_state["profile"]
    assert profile.row_count == 6
    assert profile.health_score >= 90

    # ③ 清洗页：预览 + 执行（金额归一化）
    at3 = _page("3_数据清洗.py")
    at3.session_state["raw_df"] = raw_df
    at3.session_state["profile"] = profile
    at3.run()
    assert not at3.exception
    [b for b in at3.button if b.label == "预览变更"][0].click().run()
    assert at3.session_state["cleaning_plan"] is not None
    [b for b in at3.button if b.label == "执行清洗"][0].click().run()
    assert not at3.exception
    clean_df = at3.session_state["clean_df"]
    assert clean_df is not None
    assert clean_df["销售额"].astype(float).sum() == 2100.0  # 归一化后可求和

    # ④ 分析页：分组（使用清洗后数据）
    at4 = _page("4_数据分析.py")
    at4.session_state["raw_df"] = raw_df
    at4.session_state["profile"] = profile
    at4.session_state["clean_df"] = clean_df
    at4.run()
    assert not at4.exception
    # 选择维度：地区 → 分组表
    dim_sel = [s for s in at4.selectbox if s.label == "维度（分组）"][0]
    dim_sel.select("地区").run()
    assert not at4.exception
    analysis = at4.session_state["analysis"]
    assert analysis.overview["指标合计"] == 2100.0
    labels = {g.label: g.value for g in analysis.grouped}
    assert labels["华东"] == 1000.0

    # ⑤ AI 洞察页：本地模式生成模板报告
    at5 = _page("5_AI洞察.py")
    at5.session_state["raw_df"] = raw_df
    at5.session_state["profile"] = profile
    at5.session_state["analysis"] = analysis
    at5.run()
    assert not at5.exception
    at5.radio[0].set_value("local").run()
    [b for b in at5.button if b.label == "生成 AI 报告"][0].click().run()
    assert not at5.exception
    report = at5.session_state["ai_report"]
    assert report is not None
    assert report.source == "template"
    assert "华东" in report.findings[0]


def test_guard_chain_without_upload() -> None:
    """未上传时，全部下游页面给出守卫提示且不崩溃。"""
    for name in ["2_数据体检.py", "3_数据清洗.py", "4_数据分析.py", "5_AI洞察.py"]:
        at = _page(name)
        at.run()
        assert not at.exception, f"{name} 未上传时不应崩溃"
        infos = "\n".join(str(i.value) for i in at.info)
        assert "文件上传" in infos, f"{name} 应有上传守卫提示"


def test_upload_new_file_resets_downstream() -> None:
    """重传新文件后：旧的分析/AI 状态被清除。"""
    at = _page("1_文件上传.py")
    at.run()
    # 模拟旧状态
    at.session_state["profile"] = object()
    at.session_state["analysis"] = object()
    at.session_state["ai_report"] = object()
    at.file_uploader(key="uploader").set_value(
        (
            "a.xlsx",
            _xlsx_bytes(_SALES),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ).run()
    at.button(key="confirm_btn").click().run()
    assert not at.exception
    # 确认新文件 → 下游全部清除（pop 后键不存在）；偏好保留
    assert "profile" not in at.session_state
    assert "cleaning_plan" not in at.session_state
    assert "analysis" not in at.session_state
    assert "trends" not in at.session_state
    assert "ai_report" not in at.session_state
    assert at.session_state["raw_df"] is not None
    assert at.session_state["ai_mode"] == "secure"  # 偏好键保留（reset 不清偏好）
