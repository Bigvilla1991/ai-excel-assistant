"""模型层单测：字段约束、序列化 round-trip。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.schemas import (
    AIReport,
    AnalysisResult,
    CleaningLog,
    ColumnProfile,
    ProfileResult,
    RankItem,
    TrendPoint,
)


def test_column_profile_defaults() -> None:
    col = ColumnProfile(name="a", inferred_type="text", unique_count=2, null_count=1, null_rate=0.5)
    assert col.anomaly_count == 0
    assert col.is_constant is False
    assert col.sample_values == []


def test_column_profile_rejects_bad_rate() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(name="a", inferred_type="text", unique_count=2, null_count=1, null_rate=1.5)
    with pytest.raises(ValidationError):
        ColumnProfile(name="a", inferred_type="text", unique_count=-1, null_count=0, null_rate=0)


def test_profile_result_roundtrip() -> None:
    profile = ProfileResult(
        row_count=10,
        column_count=2,
        null_cells=1,
        null_rate_total=0.05,
        duplicate_rows=0,
        blank_rows=0,
        blank_columns=[],
        columns=[
            ColumnProfile(
                name="a", inferred_type="int", unique_count=10, null_count=0, null_rate=0.0
            ),
        ],
        health_score=95,
        issues=[],
    )
    dumped = profile.model_dump()
    loaded = ProfileResult.model_validate(dumped)
    assert loaded == profile


def test_issue_item_requires_category() -> None:
    with pytest.raises(ValidationError):
        from models.schemas import IssueItem

        IssueItem(severity="warning", message="x")  # 缺 category


def test_rank_item_share_bounds() -> None:
    RankItem(label="a", value=10.0, share=0.5, rank=1)  # OK
    with pytest.raises(ValidationError):
        RankItem(label="a", value=10.0, share=1.5, rank=1)  # share > 1


def test_trend_point_change_optional() -> None:
    t = TrendPoint(period="2024-01", value=100.0)
    assert t.change_pct is None


def test_cleaning_log_defaults() -> None:
    log = CleaningLog()
    assert log.actions == []
    assert log.rows_before == 0
    assert log.rows_after == 0


def test_analysis_result_defaults() -> None:
    r = AnalysisResult(metric="销售额", agg="sum")
    assert r.dimension is None
    assert r.rankings == []
    assert r.trends == []


def test_ai_report_defaults() -> None:
    r = AIReport()
    assert r.source == "ai"
    assert r.findings == []
    assert r.overview == ""
