"""上传页 AppTest：模拟真实上传、Sheet 选择、确认入库全交互。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "1_文件上传.py"


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_file(str(_PAGE), default_timeout=30)


def test_upload_page_renders_without_file(at: AppTest) -> None:
    at.run()
    assert not at.exception


def test_upload_confirm_flow_xlsx(at: AppTest) -> None:
    df = pd.DataFrame({"姓名": ["张三", "李四"], "金额": ["￥1,234.50", "567"]})
    at.run()
    at.file_uploader(key="uploader").set_value(
        (
            "demo.xlsx",
            _xlsx_bytes(df),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ).run()
    assert not at.exception
    # 预览表格出现
    assert at.dataframe

    at.button(key="confirm_btn").click().run()
    assert not at.exception
    stored: pd.DataFrame = at.session_state["raw_df"]
    assert stored.shape == (2, 2)
    assert stored["姓名"].tolist() == ["张三", "李四"]
    assert stored["金额"].tolist() == ["￥1,234.50", "567"]  # 原文保留
    assert at.session_state["uploaded_name"] == "demo.xlsx"


def test_upload_rejects_bad_extension(at: AppTest) -> None:
    """Streamlit 上传控件原生拦截非法扩展名（页面代码不执行）。"""
    at.run()
    at.file_uploader(key="uploader").set_value(("evil.txt", b"hello", "text/plain")).run()
    assert at.exception, "非法扩展名应在 UI 层被拦截并记录异常"
    message = "\n".join(str(e.message) for e in at.exception)
    assert "Invalid file extension" in message


def test_upload_csv_gbk_without_header(at: AppTest) -> None:
    """GBK 无表头 CSV：取消表头勾选后数据完整入库。"""
    raw = "张三,北京\n李四,上海\n".encode("gbk")
    at.run()
    at.file_uploader(key="uploader").set_value(("data.csv", raw, "text/csv")).run()
    assert not at.exception
    # 检测到无表头 → 出现警告
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "不是表头" in warnings

    header_boxes = [c for c in at.checkbox if c.label == "第一行是表头（列名）"]
    assert header_boxes, "未找到表头复选框"
    header_boxes[0].uncheck().run()
    assert not at.exception
    at.button(key="confirm_btn").click().run()
    stored: pd.DataFrame = at.session_state["raw_df"]
    assert stored["列1"].tolist() == ["张三", "李四"]
    assert stored["列2"].tolist() == ["北京", "上海"]


def _selectbox_value(at: AppTest, label: str) -> str:
    matches = [s for s in at.selectbox if s.label == label]
    assert matches, f"未找到选择器: {label}"
    return str(matches[0].value)


def test_upload_switch_file_resets_widgets(at: AppTest) -> None:
    """换文件后编码选择必须重置为检测值，入库列名正确（回归：跨文件残留）。"""
    gbk_bytes = "姓名,城市\n张三,北京\n".encode("gbk")
    utf8_bytes = "姓名,城市\n李四,上海\n".encode()

    at.run()
    at.file_uploader(key="uploader").set_value(("a.csv", gbk_bytes, "text/csv")).run()
    assert _selectbox_value(at, "文件编码") in ("gbk", "gb18030")

    # 换传 UTF-8 文件：编码应自动重置为 utf-8-sig（而非残留 gbk）
    at.file_uploader(key="uploader").set_value(("b.csv", utf8_bytes, "text/csv")).run()
    assert not at.exception
    assert _selectbox_value(at, "文件编码") == "utf-8-sig"

    at.button(key="confirm_btn").click().run()
    stored: pd.DataFrame = at.session_state["raw_df"]
    assert stored.columns.tolist() == ["姓名", "城市"]
    assert stored["姓名"].tolist() == ["李四"]  # 无乱码


def test_upload_fake_xlsx_shows_page_error(at: AppTest) -> None:
    """合法扩展名 + 损坏内容：页面自身给出可读错误（非平台异常）。"""
    at.run()
    at.file_uploader(key="uploader").set_value(
        (
            "fake.xlsx",
            b"not a real zip",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ).run()
    assert not at.exception
    errors = "\n".join(str(e.value) for e in at.error)
    assert "解析失败" in errors
