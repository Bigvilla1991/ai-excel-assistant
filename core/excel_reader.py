"""ExcelReader：文件解析、Sheet 识别与读取（见方案 §8.1）。

设计决策：
- XLSX 用 calamine 引擎（速度快），失败回退 openpyxl；
- CSV 编码检测在 utils.file_utils，读取前支持手动覆盖；
- 统一以 dtype=str 读入，保留文本单元格原文（前导零、长 ID、文本型金额
  不丢失）；数值单元格读出的原始值是数字，字符串化后格式符号（如 ￥）
  不保留，类型推断与转换由 DataProfiler / DataCleaner（Day 3/5）负责；
- 不修改传入数据，返回 (DataFrame, meta) 元数据对。
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from utils.errors import FileValidationError, ParseError
from utils.file_utils import (
    MAX_ROWS,
    MAX_UNCOMPRESSED_SIZE,
    check_column_limit,
    detect_encoding,
    validate_file,
)

_XLSX_ENGINES: tuple[str, ...] = ("calamine", "openpyxl")

CSV_SHEET_MARKER: str = "（CSV 无工作表）"


def _check_zip_safety(data: bytes) -> None:
    """zip 炸弹防护：xlsx 为 zip 容器，压缩后 20MB 可解压至 GB 级。

    读取前统计解压后总大小，超过上限（默认 500MB）拒绝处理。
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            total = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile as exc:
        raise ParseError(
            "Excel 解析失败：文件不是有效的 xlsx 格式（zip 容器损坏或缺失）。"
        ) from exc
    if total > MAX_UNCOMPRESSED_SIZE:
        raise FileValidationError(
            f"文件解压后体积约 {total / (1024 * 1024):.0f} MB，"
            f"超过 {MAX_UNCOMPRESSED_SIZE // (1024 * 1024)}MB 安全处理上限。"
        )


def list_sheets(filename: str, data: bytes) -> list[str]:
    """返回工作表名列表。

    XLSX 读取 Sheet 名称（只读元数据，不加载数据）；
    CSV 返回空列表（调用方用 CSV_SHEET_MARKER 展示）。
    """
    suffix = validate_file(filename, data)
    if suffix == ".csv":
        return []
    try:
        wb = load_workbook(BytesIO(data), read_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    except Exception as exc:  # 非法 xlsx（损坏/伪格式）
        raise ParseError(
            f"Excel 解析失败：无法读取工作表列表，文件可能已损坏"
            f"或并非真正的 Excel 文件。（{type(exc).__name__}）"
        ) from exc


def _read_xlsx(data: bytes, sheet: str | None, has_header: bool) -> pd.DataFrame:
    last_error: Exception | None = None
    for engine in _XLSX_ENGINES:
        try:
            if has_header:
                return pd.read_excel(BytesIO(data), sheet_name=sheet, engine=engine, dtype=str)
            names = _auto_columns_from_xlsx(data, sheet, engine)
            return pd.read_excel(
                BytesIO(data),
                sheet_name=sheet,
                engine=engine,
                header=None,
                names=names,
                dtype=str,
            )
        except Exception as exc:  # 引擎级失败，尝试下一个
            last_error = exc
    raise ParseError(
        f"Excel 文件解析失败，文件可能已损坏或版本过旧。（{type(last_error).__name__}）"
    )


def _auto_columns_from_xlsx(data: bytes, sheet: str | None, engine: str) -> list[str]:
    probe = pd.read_excel(
        BytesIO(data), sheet_name=sheet, engine=engine, header=None, nrows=1, dtype=str
    )
    return [f"列{i + 1}" for i in range(probe.shape[1])]


def _read_csv(data: bytes, encoding: str | None, has_header: bool) -> pd.DataFrame:
    enc = encoding or detect_encoding(data)
    try:
        if has_header:
            return pd.read_csv(BytesIO(data), encoding=enc, dtype=str)
        names = _auto_columns_from_probe(data, enc)
        return pd.read_csv(BytesIO(data), encoding=enc, header=None, names=names, dtype=str)
    except UnicodeDecodeError as exc:
        raise FileValidationError(f"按编码「{enc}」读取失败，请在页面上手动选择其他编码。") from exc
    except pd.errors.EmptyDataError as exc:
        raise FileValidationError("CSV 文件内容为空，请检查文件。") from exc
    except Exception as exc:
        raise ParseError(f"CSV 文件解析失败（{type(exc).__name__}），请检查文件格式。") from exc


def _auto_columns_from_probe(data: bytes, enc: str) -> list[str]:
    """无表头时生成列名：列1、列2…（按文件列数）。"""
    probe = pd.read_csv(BytesIO(data), encoding=enc, nrows=1, header=None, dtype=str)
    return [f"列{i + 1}" for i in range(probe.shape[1])]


def looks_like_headerless(data: bytes, encoding: str | None, df: pd.DataFrame) -> bool:
    """启发式检测：文件第一行是否疑似数据而非表头（列名与首行数据全等）。"""
    if df.empty:
        return False
    try:
        probe = pd.read_csv(
            BytesIO(data),
            encoding=encoding or detect_encoding(data),
            nrows=1,
            header=None,
            dtype=str,
        )
    except Exception:
        return False
    if probe.shape[1] != df.shape[1]:
        return False
    first_row = probe.iloc[0].astype(str).tolist()
    columns = df.columns.astype(str).tolist()
    return first_row == columns


def read_file(
    filename: str,
    data: bytes,
    sheet: str | None = None,
    encoding: str | None = None,
    has_header: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """读取指定 Sheet（CSV 忽略 sheet），返回 (DataFrame, 元数据)。

    meta 包含：filename / suffix / sheet / encoding / row_count /
    column_count / sheet_names / over_row_limit（是否超过建议行数）/
    no_header（第一行疑似数据而非表头，仅 CSV 检测）。
    """
    suffix = validate_file(filename, data)

    if suffix == ".csv":
        df = _read_csv(data, encoding, has_header)
        used_sheet = None
        used_encoding = encoding or detect_encoding(data)
        sheet_names: list[str] = []
        no_header = not has_header or looks_like_headerless(data, used_encoding, df)
    else:
        _check_zip_safety(data)
        sheet_names = list_sheets(filename, data)
        if sheet is not None and sheet not in sheet_names:
            raise FileValidationError(
                f"工作表「{sheet}」不存在，可选工作表：{', '.join(sheet_names) or '（无）'}。"
            )
        used_sheet = sheet if sheet in sheet_names else (sheet_names[0] if sheet_names else None)
        df = _read_xlsx(data, used_sheet, has_header)
        used_encoding = None  # xlsx 无编码概念
        no_header = not has_header

    if df.shape[1] == 0:
        raise FileValidationError("文件内容为空：未读取到任何字段或数据行。")
    check_column_limit(df.shape[1])

    meta: dict[str, Any] = {
        "filename": filename,
        "suffix": suffix,
        "sheet": used_sheet,
        "encoding": used_encoding,
        "row_count": len(df),
        "column_count": df.shape[1],
        "sheet_names": sheet_names,
        "over_row_limit": len(df) > MAX_ROWS,
        "no_header": no_header,
    }
    return df, meta
