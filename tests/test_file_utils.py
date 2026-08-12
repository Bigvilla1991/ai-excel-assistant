"""文件工具单测：编码检测（GBK/UTF-8/UTF-16 BOM）、大小校验。"""

from __future__ import annotations

import pytest

from utils.errors import FileValidationError
from utils.file_utils import detect_encoding, validate_file


def test_detect_gbk_chinese() -> None:
    """GBK 中文文本应判为 gbk/gb18030，不得误判 utf-16（回归保护）。"""
    enc = detect_encoding("张三,北京\n李四,上海\n销售数据汇总".encode("gbk"))
    assert enc in ("gbk", "gb18030")


def test_detect_utf8() -> None:
    enc = detect_encoding("姓名,城市\n张三,北京".encode())
    assert enc in ("utf-8-sig", "utf-8")


def test_detect_utf8_sig_bom() -> None:
    enc = detect_encoding("姓名,城市\n".encode("utf-8-sig"))
    assert enc == "utf-8-sig"


def test_detect_utf16_bom() -> None:
    enc = detect_encoding("姓名,城市\n".encode("utf-16"))
    assert enc == "utf-16"


def test_detect_utf16le_no_bom() -> None:
    """无 BOM UTF-16LE：NUL 启发式应判为 utf-16-le，不落入 GBK 误判。"""
    enc = detect_encoding("姓名,城市\n张三,北京".encode("utf-16-le"))
    assert enc == "utf-16-le"


def test_detect_short_ascii() -> None:
    enc = detect_encoding(b"a,b\n1,2\n")
    assert enc in ("utf-8", "utf-8-sig", "ascii")


def test_detect_empty_returns_any() -> None:
    enc = detect_encoding(b"")
    assert isinstance(enc, str) and enc  # 空内容由校验层拦截，检测值无关紧要


def test_validate_extension_ok() -> None:
    assert validate_file("报告.XLSX", b"x") == ".xlsx"
    assert validate_file("data.csv", b"x") == ".csv"


def test_validate_extension_bad() -> None:
    with pytest.raises(FileValidationError):
        validate_file("data.txt", b"x")


def test_validate_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import file_utils

    monkeypatch.setattr(file_utils, "MAX_FILE_SIZE", 5)
    with pytest.raises(FileValidationError, match="超过"):
        validate_file("data.csv", b"123456")
