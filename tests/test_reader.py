"""ExcelReader 单元测试：合法/非法文件、编码、空文件、仅表头、Sheet 识别。

用 tmp_path 生成真实文件（xlsx 经 openpyxl 写出，csv 覆盖多编码），
不依赖任何外部样例数据。
"""

from __future__ import annotations

import pandas as pd
import pytest

from core.excel_reader import CSV_SHEET_MARKER, list_sheets, read_file
from utils.errors import FileValidationError, ParseError


def _make_xlsx(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


@pytest.fixture
def xlsx_multi(tmp_path):
    path = tmp_path / "multi.xlsx"
    _make_xlsx(
        path,
        {
            "销售": pd.DataFrame(
                {"姓名": ["张三", "李四"], "销售额": ["￥1,234.50", "567"], "编号": ["007", "0008"]}
            ),
            "明细": pd.DataFrame({"日期": ["2024/1/5", "2024-01-06"]}),
        },
    )
    return path.read_bytes()


@pytest.fixture
def csv_gbk(tmp_path):
    path = tmp_path / "gbk.csv"
    df = pd.DataFrame({"姓名": ["张三", "李四"], "城市": ["北京", "上海"]})
    df.to_csv(path, index=False, encoding="gbk")
    return path.read_bytes()


@pytest.fixture
def csv_utf8_sig(tmp_path):
    path = tmp_path / "utf8sig.csv"
    df = pd.DataFrame({"姓名": ["张三"], "城市": ["广州"]})
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path.read_bytes()


# ---- 合法读取 ----


def test_read_xlsx_default_first_sheet(xlsx_multi: bytes) -> None:
    df, meta = read_file("multi.xlsx", xlsx_multi)
    assert df.shape == (2, 3)
    assert meta["row_count"] == 2
    assert meta["column_count"] == 3
    assert meta["sheet"] == "销售"
    assert meta["suffix"] == ".xlsx"


def test_read_xlsx_specific_sheet(xlsx_multi: bytes) -> None:
    df, meta = read_file("multi.xlsx", xlsx_multi, sheet="明细")
    assert df.columns.tolist() == ["日期"]
    assert meta["sheet"] == "明细"


def test_read_xlsx_preserves_raw_text(xlsx_multi: bytes) -> None:
    """前导零与金额符号原文保留（dtype=str 策略）。"""
    df, _ = read_file("multi.xlsx", xlsx_multi)
    assert df["编号"].tolist() == ["007", "0008"]
    assert df["销售额"].tolist() == ["￥1,234.50", "567"]


def test_read_csv_gbk(csv_gbk: bytes) -> None:
    df, meta = read_file("gbk.csv", csv_gbk)
    assert df["姓名"].tolist() == ["张三", "李四"]
    assert meta["encoding"] in ("gbk", "gb18030")
    assert meta["sheet"] is None
    assert meta["sheet_names"] == []


def test_read_csv_utf8_sig(csv_utf8_sig: bytes) -> None:
    df, meta = read_file("utf8sig.csv", csv_utf8_sig)
    assert df["姓名"].tolist() == ["张三"]
    assert meta["encoding"] == "utf-8-sig"


def test_read_csv_with_forced_encoding(csv_gbk: bytes) -> None:
    """用户手动指定编码时以指定值为准。"""
    df, meta = read_file("gbk.csv", csv_gbk, encoding="gbk")
    assert df["姓名"].tolist() == ["张三", "李四"]
    assert meta["encoding"] == "gbk"


# ---- 非法文件 ----


def test_reject_bad_extension() -> None:
    with pytest.raises(FileValidationError, match="不支持的文件类型"):
        read_file("evil.txt", b"hello")


def test_reject_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import file_utils

    monkeypatch.setattr(file_utils, "MAX_FILE_SIZE", 10)  # 10 字节
    with pytest.raises(FileValidationError, match="超过"):
        read_file("big.csv", b"a,b\n1,2\n3,4\n")


def test_reject_empty_file() -> None:
    with pytest.raises(FileValidationError, match="文件内容为空"):
        read_file("empty.csv", b"")


def test_reject_headerless_csv(tmp_path) -> None:
    """无表头 CSV 默认按有表头读取：列名会变成首行数据，检测器应能识别。"""
    path = tmp_path / "no_header.csv"
    path.write_bytes("张三,北京\n李四,上海\n".encode())
    df, meta = read_file("no_header.csv", path.read_bytes())
    assert meta["no_header"] is True  # 提示用户：第一行疑似数据
    assert df.columns.tolist() == ["张三", "北京"]  # 现状：首行成为列名


def test_read_csv_without_header(tmp_path) -> None:
    """用户确认无表头后：自动生成列1、列2…，数据完整保留。"""
    path = tmp_path / "no_header.csv"
    path.write_bytes("张三,北京\n李四,上海\n".encode())
    df, meta = read_file("no_header.csv", path.read_bytes(), has_header=False)
    assert df.columns.tolist() == ["列1", "列2"]
    assert df["列1"].tolist() == ["张三", "李四"]
    assert df["列2"].tolist() == ["北京", "上海"]
    assert meta["no_header"] is True


def test_reject_fake_xlsx() -> None:
    with pytest.raises(ParseError, match="解析失败"):
        read_file("fake.xlsx", b"this is not a zip file")


# ---- Sheet 识别 ----


def test_list_sheets_xlsx(xlsx_multi: bytes) -> None:
    assert list_sheets("multi.xlsx", xlsx_multi) == ["销售", "明细"]


def test_list_sheets_csv(csv_gbk: bytes) -> None:
    assert list_sheets("gbk.csv", csv_gbk) == []


def test_csv_sheet_marker_is_display_text() -> None:
    assert CSV_SHEET_MARKER == "（CSV 无工作表）"


# ---- 边界 ----


def test_header_only_csv(tmp_path) -> None:
    """仅表头文件：可读取，0 行数据。"""
    path = tmp_path / "header_only.csv"
    path.write_bytes("姓名,城市\n".encode())
    df, meta = read_file("header_only.csv", path.read_bytes())
    assert df.shape == (0, 2)
    assert meta["row_count"] == 0


def test_header_only_xlsx(tmp_path) -> None:
    path = tmp_path / "header_only.xlsx"
    _make_xlsx(path, {"Sheet1": pd.DataFrame(columns=["a", "b"])})
    df, _ = read_file("header_only.xlsx", path.read_bytes())
    assert df.shape == (0, 2)


def test_extension_uppercase(xlsx_multi: bytes) -> None:
    df, meta = read_file("multi.XLSX", xlsx_multi)
    assert df.shape == (2, 3)
    assert meta["suffix"] == ".xlsx"


# ---- 安全防护 ----


def test_reject_zip_bomb(monkeypatch: pytest.MonkeyPatch, xlsx_multi: bytes) -> None:
    """解压后体积超上限应拒绝（zip 炸弹防护）。"""
    from core import excel_reader

    monkeypatch.setattr(excel_reader, "MAX_UNCOMPRESSED_SIZE", 10)  # 10 字节
    with pytest.raises(FileValidationError, match="解压后体积"):
        read_file("multi.xlsx", xlsx_multi)


def test_reject_too_many_columns(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """超过列数上限应拒绝（宽表防护）。"""
    from utils import file_utils

    monkeypatch.setattr(file_utils, "MAX_COLUMNS", 5)
    path = tmp_path / "wide.csv"
    header = ",".join(f"c{i}" for i in range(6))
    path.write_bytes((header + "\n" + ",".join(["1"] * 6) + "\n").encode())
    with pytest.raises(FileValidationError, match="列数"):
        read_file("wide.csv", path.read_bytes())


def test_reject_unknown_sheet(xlsx_multi: bytes) -> None:
    """指定的工作表不存在应显式报错，不静默回退第一个。"""
    with pytest.raises(FileValidationError, match="不存在"):
        read_file("multi.xlsx", xlsx_multi, sheet="不存在表")
