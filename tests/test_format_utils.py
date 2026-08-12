"""格式工具单测：类型映射防漂移（与 models.schemas 的 TypeName 保持一致）。"""

from __future__ import annotations

from typing import get_args

from models.schemas import TypeName
from utils.format_utils import (
    TYPE_DESCRIPTIONS,
    TYPE_LABELS,
    TYPE_LABELS_ORDER,
    type_description,
    type_label,
)


def test_mapping_covers_all_types() -> None:
    """TypeName 全部 7 种类型在标签/说明/顺序三张映射中完整覆盖。"""
    names = set(get_args(TypeName))
    assert names == set(TYPE_LABELS)
    assert names == set(TYPE_DESCRIPTIONS)
    assert set(TYPE_LABELS_ORDER) == names
    assert len(TYPE_LABELS_ORDER) == len(names)  # 无重复


def test_label_roundtrip() -> None:
    assert type_label("date") == "日期"
    assert type_label("id") == "编号"
    assert type_label("unknown_type") == "unknown_type"  # 未知类型原样返回


def test_description_not_empty_for_known_types() -> None:
    for type_name in TYPE_LABELS_ORDER:
        assert type_description(type_name), f"{type_name} 缺少说明"
