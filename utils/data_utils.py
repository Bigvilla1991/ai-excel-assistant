"""数据清洗辅助：字符串化、缺失归一、中文日期归一化（profiler/cleaner 共用）。

约定：空字符串（""）与 None/NaN 统一视为缺失，整表以 pandas
StringDtype 处理，保证清洗与体检口径一致。
"""

from __future__ import annotations

import pandas as pd


def clean_series(series: pd.Series) -> pd.Series:
    """字符串化并归一缺失（None/NaN/"" → pd.NA），返回副本。"""
    s = series.astype("string").str.strip()
    return s.replace("", pd.NA)


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """整表字符串化 + 缺失归一（None/NaN/"" → pd.NA），返回副本。"""
    return pd.DataFrame(
        {c: df[c].astype("string").str.strip().replace("", pd.NA) for c in df.columns}
    )


def normalize_cn_dates(series: pd.Series) -> pd.Series:
    """中文日期单位归一化为 ISO 短格式（2024年2月1日 → 2024-2-1）。

    pandas 3.0 的 to_datetime 不支持中文年月日单位，统一先转换。
    对无中文单位的字符串返回原样。
    """
    return series.str.replace(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日?", r"\1-\2-\3", regex=True
    ).str.replace(r"(\d{4})年(\d{1,2})月", r"\1-\2", regex=True)
