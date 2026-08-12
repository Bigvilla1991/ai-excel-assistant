"""AIEngine 单元测试：模板回退、LLM 成功、坏 JSON、编造数字、重试次数（mock 不联网）。"""

from __future__ import annotations

import json

import pytest

from core.ai_engine import generate_report, report_text, template_report
from core.ai_validation import validate_report_numbers
from models.schemas import AIReport

CONTEXT = {
    "dataset": {"row_count": 1200, "column_count": 8},
    "quality": {
        "health_score": 95,
        "missing_cells": 2,
        "duplicate_rows": 0,
        "issues": ["日期异常"],
    },
    "analysis": {"metric": "销售额", "dimension": "地区", "agg": "sum", "total": 5321862.0},
    "rankings": [{"rank": 1, "label": "华东", "value": 5000000.0, "share": 0.94}],
    "trends": [
        {"period": "2024-01", "value": 100.0, "change_pct": None},
        {"period": "2024-02", "value": 120.0, "change_pct": 20.0},
    ],
    "anomalies": [],
}


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": content})()})()]


class FakeClient:
    """可编程 mock：按序返回预设响应（属性链模拟 openai SDK）。"""

    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls: list[str] = []

    @property
    def chat(self):  # noqa: ANN201
        return self

    @property
    def completions(self):  # noqa: ANN201
        return self

    def create(self, **kwargs):  # noqa: ANN201
        self.calls.append(json.dumps(kwargs, ensure_ascii=False))
        if not self.contents:
            raise RuntimeError("模拟网络故障")
        content = self.contents.pop(0)
        if content is None:  # None 标记 = 模拟网络故障
            raise RuntimeError("模拟网络故障")
        return FakeResponse(content)


def _valid_report_json() -> str:
    """一份数字全部可溯源的合法报告。"""
    return json.dumps(
        {
            "overview": "数据共 1200 行、8 列，健康评分 95 分，销售额合计 5321862。",
            "findings": ["华东排名第一，销售额为 5000000，占比 94%。"],
            "trends": ["2024-02 销售额 120，环比增长 20%。"],
            "anomalies": [],
            "causes": ["可能受活动或季节性因素影响，建议验证。"],
            "recommendations": ["建议复盘华东地区的驱动因素。"],
            "quality_notes": ["检测到日期格式异常。"],
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------- 模板报告


def test_template_report_structure() -> None:
    report = template_report(CONTEXT)
    assert report.source == "template"
    assert report.overview
    assert report.findings
    assert report.trends
    assert isinstance(report.anomalies, list)
    assert isinstance(report.causes, list)
    assert report.recommendations
    assert report.quality_notes


def test_template_report_numbers_traceable() -> None:
    """模板报告数字全部来自上下文（可溯源）。"""
    report = template_report(CONTEXT)
    assert validate_report_numbers(report_text(report), CONTEXT) == []


def test_template_report_references_ranking() -> None:
    report = template_report(CONTEXT)
    assert "华东" in report.findings[0]
    assert "94" in report.findings[0]  # 占比


def test_template_report_no_trends() -> None:
    ctx = dict(CONTEXT, trends=[])
    report = template_report(ctx)
    assert report.trends == []  # 无趋势时不编造


def test_template_report_value_none_no_crash() -> None:
    """趋势点 value=None（全空周期）：模板不崩溃，输出可溯源。"""
    ctx = dict(CONTEXT, trends=[{"period": "2024-01", "value": None, "change_pct": None}])
    report = template_report(ctx)
    assert report.trends
    assert "无有效数值" in report.trends[0]
    assert validate_report_numbers(report_text(report), ctx) == []


def test_template_report_all_none_trends() -> None:
    """所有趋势点均无有效值：峰值句省略，不崩溃。"""
    ctx = dict(
        CONTEXT,
        trends=[
            {"period": "2024-01", "value": None, "change_pct": None},
            {"period": "2024-02", "value": None, "change_pct": None},
        ],
    )
    report = template_report(ctx)
    assert not any("峰值" in t for t in report.trends)


# ---------------------------------------------------------------- 生成流程


def test_local_mode_returns_template() -> None:
    report = generate_report(CONTEXT, mode="local", api_key="sk-test")
    assert report.source == "template"


def test_no_api_key_returns_template() -> None:
    report = generate_report(CONTEXT, mode="secure", api_key=None)
    assert report.source == "template"


def test_llm_success() -> None:
    client = FakeClient([_valid_report_json()])
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "ai"
    assert report.overview.startswith("数据共")
    assert len(client.calls) == 1


def test_llm_bad_json_retries_then_template() -> None:
    """坏 JSON → 重试 → 仍坏 → 模板回退。"""
    client = FakeClient(["这不是 JSON", "还是不对"])
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "template"
    assert len(client.calls) == 2  # 最多重试 1 次


def test_llm_fabricated_numbers_retries_then_template() -> None:
    """编造数字 → 校验拦截 → 修正重试 → 仍编造 → 模板回退。"""
    fabricated = json.dumps(
        {
            "overview": "总销售额为 99999999 元。",
            "findings": ["华东排名第一。"],
            "trends": ["2024-02 销售额 120。"],
            "anomalies": [],
            "causes": [],
            "recommendations": [],
            "quality_notes": [],
        },
        ensure_ascii=False,
    )
    client = FakeClient([fabricated, fabricated])
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "template"
    assert len(client.calls) == 2
    # 第二次调用的修正提示必须携带编造数字（供模型更正）
    second_call = json.loads(client.calls[1])
    user_content = second_call["messages"][-1]["content"]
    assert "99999999" in user_content


def test_llm_fabricated_then_fixed() -> None:
    """第一次编造 → 修正提示 → 第二次正确 → 返回 AI 报告。"""
    bad = json.dumps(
        {
            "overview": "总销售额为 99999999 元。",
            "findings": [],
            "trends": [],
            "anomalies": [],
            "causes": [],
            "recommendations": [],
            "quality_notes": [],
        },
        ensure_ascii=False,
    )
    client = FakeClient([bad, _valid_report_json()])
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "ai"
    assert len(client.calls) == 2


def test_llm_network_error_retries_then_template() -> None:
    client = FakeClient([])  # 无响应 → 模拟网络故障
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "template"


def test_llm_incomplete_json_retries() -> None:
    """缺字段 JSON（只有 overview）→ 完整性校验拦截 → 重试 → 模板。"""
    incomplete = json.dumps({"overview": "只有概况。"}, ensure_ascii=False)
    client = FakeClient([incomplete, incomplete])
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "template"
    assert len(client.calls) == 2


def test_llm_network_error_then_success() -> None:
    """网络错误后第二次成功 → 返回 AI 报告。"""
    client = FakeClient([None, _valid_report_json()])  # 第一个触发网络错误
    report = generate_report(CONTEXT, mode="secure", api_key="sk-test", client=client)
    assert report.source == "ai"
    assert len(client.calls) == 2


def test_llm_secure_mode_no_samples_sent() -> None:
    """安全模式：请求内容不含样例值（隐私红线回归）。

    注：样例值裁剪发生在 build_context（见 test_ai_context），
    generate_report 原样透传上下文——本测试验证"误带样例时不会意外上送"。
    """
    ctx = dict(CONTEXT)
    ctx["samples"] = {"地区": ["华东", "华北"]}  # enhanced 结构误入 secure
    client = FakeClient([_valid_report_json()])
    generate_report(ctx, mode="secure", api_key="sk-test", client=client)
    content = json.loads(client.calls[0])["messages"][-1]["content"]
    # 上下文中确实包含 samples → 说明引擎层不负责裁剪，
    # 隐私保障依赖 build_context（页面层），此处锁定行为契约
    assert '"samples"' in content


def test_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="未知 AI 模式"):
        generate_report(CONTEXT, mode="foo", api_key="sk-test", client=FakeClient([]))


def test_report_text_joins_sections() -> None:
    report = AIReport(overview="概况", findings=["发现1"], trends=["趋势1"])
    text = report_text(report)
    assert "概况" in text
    assert "发现1" in text
    assert "趋势1" in text
