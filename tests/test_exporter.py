"""ExcelExporter 单元测试：7 Sheet、公式注入防护、格式、HTML 报告。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from core.analyzer import analyze
from core.exporter import (
    build_analysis_workbook,
    build_cleaned_workbook,
    build_report_html,
    build_report_markdown,
    sanitize_cell,
)
from core.profiler import profile
from models.schemas import AIReport, CleaningAction, CleaningLog

RAW = pd.DataFrame(
    {
        "地区": ["华东", "华北", "华东"],
        "销售额": ["100", "200", "300"],
        "订单号": ["A1", "A2", "A3"],
    }
)
CLEAN = RAW.assign(销售额=["100.0", "200.0", "300.0"])


# ---------------------------------------------------------------- 单元格净化


def test_sanitize_numeric_kept() -> None:
    assert sanitize_cell(100) == 100
    assert sanitize_cell("100") == 100.0
    assert sanitize_cell("-5") == -5.0  # 负数是合法数值，不转义
    assert sanitize_cell("0.5") == 0.5


def test_sanitize_preserves_text_like_numbers() -> None:
    """前导零/下划线/千分位文本保持原文（回归：float() 误伤）。"""
    assert sanitize_cell("007") == "007"  # 前导零不丢失
    assert sanitize_cell("00123") == "00123"
    assert sanitize_cell("2024_01") == "2024_01"  # 下划线不是数字分隔符
    assert sanitize_cell("1,234.5") == "1,234.5"  # 千分位文本保持原文
    assert sanitize_cell("12,34") == "12,34"  # 非法千分位不静默改写


def test_sanitize_nan_inf_as_text() -> None:
    """NaN/inf 文本按文本保留，不写入为空单元格。"""
    assert sanitize_cell("NaN") == "NaN"
    assert sanitize_cell("inf") == "inf"
    assert sanitize_cell("-Infinity") == "'-Infinity"  # - 开头非数值 → 转义保护


def test_sanitize_nat() -> None:
    assert sanitize_cell(pd.NaT) is None


def test_sanitize_formula_injection() -> None:
    assert sanitize_cell("=SUM(A1:A9)") == "'=SUM(A1:A9)"  # 前置单引号
    assert sanitize_cell("+cmd") == "'+cmd"
    assert sanitize_cell("@cmd") == "'@cmd"
    assert sanitize_cell("- 未填写") == "'- 未填写"  # 非数值的 - 开头文本
    assert sanitize_cell("\t=1") == "'=1"  # 制表符被 strip 后 = 仍被转义（安全）


def test_sanitize_normal_text_kept() -> None:
    assert sanitize_cell("普通文本") == "普通文本"
    assert sanitize_cell("华东") == "华东"


def test_sanitize_empty_and_null() -> None:
    assert sanitize_cell(None) is None
    assert sanitize_cell("") is None
    assert sanitize_cell(pd.NA) is None


def test_sanitize_timestamp() -> None:
    from datetime import datetime

    ts = pd.Timestamp("2024-01-05")
    assert sanitize_cell(ts) == datetime(2024, 1, 5)


# ---------------------------------------------------------------- 工作簿导出


def _load(bytes_data: bytes):
    return load_workbook(BytesIO(bytes_data))


def test_cleaned_workbook_content() -> None:
    wb = _load(build_cleaned_workbook(CLEAN))
    assert wb.sheetnames == ["清洗数据", "清洗说明"]
    ws = wb["清洗数据"]
    assert [c.value for c in ws[1]] == ["地区", "销售额", "订单号"]
    assert ws["B2"].value == 100.0  # 数值化
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None


def test_analysis_workbook_sheets() -> None:
    prof = profile(CLEAN)
    result = analyze(CLEAN, "销售额", dimension="地区", agg="sum")
    result.rankings = []
    log = CleaningLog(
        actions=[
            CleaningAction(
                action="金额归一化", columns=["销售额"], cells_affected=3, description="x"
            )
        ],
        rows_before=3,
        rows_after=3,
    )
    report = AIReport(overview="概况", findings=["发现1"], source="template")
    wb = _load(build_analysis_workbook(RAW, CLEAN, prof, result, log=log, report=report))
    expected = [
        "原始数据",
        "清洗数据",
        "数据质量",
        "问题清单",
        "汇总统计",
        "排名分析",
        "趋势分析",
        "清洗日志",
        "AI报告",
    ]
    assert wb.sheetnames == expected

    # 排名分析为空表可打开
    assert wb["排名分析"].max_row >= 1
    # 清洗日志含动作
    log_ws = wb["清洗日志"]
    assert log_ws["A2"].value == "金额归一化"
    # AI 报告 sheet 含内容
    assert wb["AI报告"]["A2"].value == "数据概况"


def test_analysis_workbook_formula_protection() -> None:
    """导出含公式注入文本时被转义（读出为文本而非公式）。"""
    evil = RAW.copy()
    evil.loc[0, "订单号"] = '=HYPERLINK("http://evil.com")'
    prof = profile(evil)
    result = analyze(evil, "销售额", agg="sum")
    wb = _load(build_analysis_workbook(evil, evil, prof, result))
    ws = wb["原始数据"]
    cell = ws["C2"]
    assert cell.data_type == "s"  # 字符串类型（非公式）
    assert str(cell.value).startswith("'")


def test_analysis_workbook_without_rankings_trends() -> None:
    """无排名/趋势/日志时各 Sheet 仍可打开（空表头）。"""
    prof = profile(CLEAN)
    result = analyze(CLEAN, "销售额", agg="sum")
    wb = _load(build_analysis_workbook(RAW, CLEAN, prof, result))
    assert wb["排名分析"]["A1"].value == "排名"
    assert wb["趋势分析"]["A1"].value == "周期"
    assert wb["清洗日志"]["A1"].value == "动作"


# ---------------------------------------------------------------- 报告导出


def test_report_markdown_structure() -> None:
    report = AIReport(
        overview="数据概况内容",
        findings=["发现A", "发现B"],
        trends=["趋势A"],
        recommendations=["建议A"],
        source="template",
    )
    md = build_report_markdown(report)
    assert "# AI 数据分析报告" in md
    assert "数据概况" in md and "数据概况内容" in md
    assert "- 发现A" in md and "- 发现B" in md
    assert "本地模板" in md  # 来源标注


def test_report_html_contains_charts() -> None:
    import plotly.graph_objects as go

    report = AIReport(overview="概况", findings=["发现1"])
    fig = go.Figure(go.Bar(x=["a"], y=[1.0]))
    html = build_report_html(report, [fig])
    assert "<html" in html and "AI 数据分析报告" in html
    assert "plotly" in html  # 图表库引用
    assert "概况" in html


def test_report_html_escapes_content() -> None:
    """AI 内容含脚本标签 → 转义（防分享型 XSS）。"""
    report = AIReport(
        overview="<img src=x onerror=alert(1)>",
        findings=['<script>alert("x")</script>'],
        recommendations=["安全 <b>内容</b>"],
    )
    html = build_report_html(report, [])
    assert "<script>" not in html  # 原始标签不存在
    assert "&lt;script&gt;" in html  # 已转义
    assert "&lt;img" in html
    # 正常内容不被破坏
    assert "安全 &lt;b&gt;内容&lt;/b&gt;" in html
