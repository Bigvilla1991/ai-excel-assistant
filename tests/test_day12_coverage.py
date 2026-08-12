"""Day 12 补齐测试：引擎回退、边界分支（对应 coverage 缺口）。"""

from __future__ import annotations

import pandas as pd
import pytest

from core.cleaner import apply_plan, build_plan
from core.excel_reader import read_file
from core.profiler import profile
from models.schemas import CleaningAction, CleaningPlan
from utils.errors import FileValidationError, ParseError


def test_read_xlsx_engine_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """calamine 引擎失败 → 回退 openpyxl 仍可读取。"""
    import pandas as _pd

    path = tmp_path / "t.xlsx"
    _pd.DataFrame({"a": ["1", "2"]}).to_excel(path, index=False, engine="openpyxl")
    data = path.read_bytes()

    import core.excel_reader as er

    def _boom(*args, **kwargs):
        raise RuntimeError("calamine 故障")

    # 全部引擎失败 → ParseError
    monkeypatch.setattr(pd, "read_excel", _boom)
    with pytest.raises(ParseError, match="解析失败"):
        er._read_xlsx(data, None, True)
    monkeypatch.undo()  # 恢复真实 read_excel

    # 真实引擎（openpyxl）成功（sheet 名必须显式传入，sheet=None 返回 dict）
    df = er._read_xlsx(data, "Sheet1", True)
    assert df.shape == (2, 1)


def test_read_xlsx_without_header(tmp_path) -> None:
    """xlsx 无表头：has_header=False 生成列1、列2…"""
    import pandas as _pd

    path = tmp_path / "nh.xlsx"
    _pd.DataFrame([["a", "b"], ["c", "d"]]).to_excel(
        path, index=False, header=False, engine="openpyxl"
    )
    df, meta = read_file("nh.xlsx", path.read_bytes(), has_header=False)
    assert df.columns.tolist() == ["列1", "列2"]
    assert df["列1"].tolist() == ["a", "c"]
    assert meta["no_header"] is True


def test_zip_badzipfile_raises_parse_error() -> None:
    """损坏 zip → ParseError（zip 炸弹预检路径）。"""
    from core.excel_reader import _check_zip_safety

    with pytest.raises(ParseError, match="解析失败"):
        _check_zip_safety(b"not a zip at all")


# ---------------------------------------------------------------- cleaner 边界


def test_fill_mode_on_all_null_column() -> None:
    """全空列 + 众数：不崩溃，填充为 NA 保留。"""
    df = pd.DataFrame({"备注": [None, None, None], "数值": ["1", "2", "3"]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["备注"], description="x")],
        fill_strategies={"备注": "众数"},
    )
    clean, log = apply_plan(df, plan)
    assert len(clean) == 3
    assert clean["备注"].isna().all()  # 众数为空 → 保持缺失
    assert log.actions[0].cells_affected == 3  # 计入尝试填充数


def test_apply_plan_unknown_action_skipped() -> None:
    """未知动作静默跳过（防御），不影响其他动作。"""
    df = pd.DataFrame({"a": ["1", "2"]})
    plan = CleaningPlan(actions=[CleaningAction(action="不存在的动作", description="x")])
    clean, log = apply_plan(df, plan)
    assert len(log.actions) == 0
    assert len(clean) == 2


def test_build_plan_empty_choices() -> None:
    plan = build_plan(profile(pd.DataFrame({"a": ["1"]})), {})
    assert plan.actions == []


def test_fill_strategy_unknown_kept() -> None:
    """未知策略名 → 跳过该列（不崩溃）。"""
    df = pd.DataFrame({"a": ["1", None]})
    plan = CleaningPlan(
        actions=[CleaningAction(action="填充缺失值", columns=["a"], description="x")],
        fill_strategies={"a": "神秘策略"},
    )
    clean, log = apply_plan(df, plan)
    assert clean["a"].isna().sum() == 1  # 未填充
    assert log.actions[0].cells_affected == 0


# ---------------------------------------------------------------- ai_engine 分支


def test_authentication_error_falls_back_immediately() -> None:
    """鉴权错误不重试，直接回退模板。"""
    from openai import AuthenticationError

    from core.ai_engine import generate_report

    class AuthClient:
        @property
        def chat(self):
            return self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):  # noqa: ANN201
            raise AuthenticationError("invalid key", response=None, body=None)

    ctx = {"analysis": {"total": 100.0}}
    report = generate_report(ctx, mode="secure", api_key="bad", client=AuthClient())
    assert report.source == "template"


def test_prompt_file_missing_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """提示词文件缺失 → 内置 fallback 含 7 字段结构要求。"""
    from core import ai_engine

    monkeypatch.setattr(ai_engine, "_PROMPT_FILE", __import__("pathlib").Path("不存在.md"))
    prompt = ai_engine._load_system_prompt()
    assert "overview" in prompt
    assert "findings" in prompt  # fallback 保留结构约束


# ---------------------------------------------------------------- chart_engine 空图


def test_line_chart_empty_and_all_none() -> None:
    from core.chart_engine import line_chart
    from models.schemas import TrendPoint

    assert len(line_chart([], "销售额").data) == 0  # 空 → 空图
    fig = line_chart([TrendPoint(period="2024-01", value=None)], "销售额")
    assert len(fig.data) == 0  # 全 None → 空图


# ---------------------------------------------------------------- analyzer 边界


def test_analyze_mean_without_dimension_all_null() -> None:
    from core.analyzer import analyze

    df = pd.DataFrame({"销售额": [None, None]})
    result = analyze(df, "销售额", agg="mean")
    assert result.grouped[0].value is None  # 全空 → None 不崩溃


# ---------------------------------------------------------------- exporter 金额格式


def test_money_format_applied() -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    from core.exporter import build_cleaned_workbook

    df = pd.DataFrame({"销售额": ["100.5", "200"], "名称": ["a", "b"]})
    wb = load_workbook(BytesIO(build_cleaned_workbook(df)))
    ws = wb["清洗数据"]
    assert ws["A2"].number_format == "#,##0.00"  # 销售额列自动应用金额格式
    assert ws["A2"].value == 100.5  # 数值保持


# ---------------------------------------------------------------- file_utils 分支


def test_probe_utf16_no_nul_returns_none() -> None:
    from utils.file_utils import _probe_utf16

    assert _probe_utf16("普通文本".encode()) is None  # 无 NUL → None


def test_check_column_limit_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import file_utils

    monkeypatch.setattr(file_utils, "MAX_COLUMNS", 5)
    file_utils.check_column_limit(5)  # 等于上限 → OK
    with pytest.raises(FileValidationError):
        file_utils.check_column_limit(6)
