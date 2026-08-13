"""页面 1：文件上传 —— 解析、Sheet/编码选择、预览、确认入库。"""

from __future__ import annotations

import streamlit as st

from core.excel_reader import (
    CSV_SHEET_MARKER,
    list_sheets,
    read_file,
)
from utils.file_utils import ENCODING_OPTIONS, MAX_ROWS, detect_encoding
from utils.logger import get_logger
from utils.session import init_session_state, reset_downstream
from utils.ui import apply_theme, handle_exception, render_page_header, render_session_status

st.set_page_config(page_title="文件上传", page_icon="📁", layout="wide")
init_session_state()
apply_theme()
render_session_status()
logger = get_logger("upload_page")

render_page_header("文件上传", "支持 .xlsx / .csv，单文件不超过 20MB，建议不超过 10 万行。", step=1)

# ---- 已载入数据提示 ----
if st.session_state.raw_df is not None:
    cur = st.session_state.raw_df
    st.info(
        f"当前已载入：**{st.session_state.uploaded_name}**（{len(cur):,} 行 × {cur.shape[1]:,} 列）"
    )

uploaded = st.file_uploader(
    "选择文件",
    type=["xlsx", "csv"],
    key="uploader",
    help="文件只在本会话内处理，不会上传到任何服务器（AI 调用遵循所选隐私模式）。",
)

if uploaded is None:
    st.stop()

# ---- 校验与元数据 ----
try:
    raw_bytes = uploaded.getvalue()
    suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
    if suffix == ".csv":
        sheet_options = []
        detected_encoding = detect_encoding(raw_bytes)
    else:
        sheet_options = list_sheets(uploaded.name, raw_bytes)
        detected_encoding = None
except Exception as exc:
    handle_exception(exc, logger, "文件校验")

# ---- 选择器（Sheet / 编码 / 表头）----
# 控件 key 含上传唯一标识 file_id：更换文件时 key 变化 → 状态自动重置，
# 避免上一个文件的编码/表头选择残留到新文件（数据损坏风险）。
fid = uploaded.file_id
col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    if sheet_options:
        sheet = st.selectbox("工作表", sheet_options, key=f"sheet_sel_{fid}")
    else:
        sheet = None
        st.selectbox("工作表", [CSV_SHEET_MARKER], key="sheet_sel_disabled", disabled=True)
with col2:
    if suffix == ".csv":
        enc_options = list(ENCODING_OPTIONS)
        default_index = (
            enc_options.index(detected_encoding) if detected_encoding in enc_options else 0
        )
        encoding = st.selectbox("文件编码", enc_options, index=default_index, key=f"enc_sel_{fid}")
        if detected_encoding and detected_encoding not in enc_options:
            st.caption(f"检测结果：{detected_encoding}（不在列表中，请手动选择）")
    else:
        encoding = None
        st.selectbox("文件编码", ["Excel 无需编码"], key="enc_sel_disabled", disabled=True)
with col3:
    has_header = st.checkbox("第一行是表头（列名）", value=True, key=f"header_chk_{fid}")
    st.caption("如果预览中第一行出现在列名位置，请取消勾选。")

# ---- 读取与预览 ----
try:
    df, meta = read_file(
        uploaded.name, raw_bytes, sheet=sheet, encoding=encoding, has_header=has_header
    )
except Exception as exc:
    handle_exception(exc, logger, "文件读取")

m1, m2, m3, m4 = st.columns(4)
m1.metric("行数", f"{meta['row_count']:,}")
m2.metric("列数", f"{meta['column_count']:,}")
m3.metric("工作表", meta["sheet"] or "—")
m4.metric("编码", meta["encoding"] or "—")

if meta["no_header"] and has_header:
    st.warning(
        "检测到文件第一行可能**不是表头**（看起来像数据）。"
        "如果列名显示的是数据内容，请取消勾选上方「第一行是表头」。"
    )
if meta["over_row_limit"]:
    st.warning(f"文件行数超过 {MAX_ROWS:,} 行建议上限，处理速度可能较慢，请耐心等待。")

st.subheader("数据预览（前 100 行）")
st.dataframe(df.head(100), width="stretch", hide_index=True)

st.caption(f"共 {meta['row_count']:,} 行，预览前 100 行。字段类型识别将在「② 数据体检」完成。")

# ---- 确认入库 ----
if st.button("确认使用此数据", type="primary", key="confirm_btn"):
    st.session_state.uploaded_name = uploaded.name
    st.session_state.raw_df = df
    st.session_state.file_meta = meta
    reset_downstream("profile")  # 清除下游分析状态，保留 raw_df
    logger.info(
        "文件已载入 | name=%s rows=%d cols=%d sheet=%s",
        uploaded.name,
        len(df),
        df.shape[1],
        meta["sheet"],
    )
    st.success(f"已确认使用「{uploaded.name}」。接下来请从侧边栏进入 **② 数据体检** 查看数据质量。")
