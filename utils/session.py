"""会话状态管理（st.session_state 键名约定，见实施计划 §2.1）。

原则：
- 模块层（core/、utils/）不依赖 Streamlit，session_state 只在 pages/ 读写；
- 上传新文件 / 重新选择时，调用 reset_downstream 清理下游数据状态，防止脏数据；
- DATA_KEYS 与 PREFERENCE_KEYS 分离：用户偏好（如 AI 模式）不随数据重置。
"""

from __future__ import annotations

import streamlit as st

# 数据状态（可随文件变更整体清除）
DATA_KEYS: tuple[str, ...] = (
    "pending_upload",  # 首页暂存的上传文件（进入解析页前使用）
    "uploaded_name",  # 文件名
    "file_meta",  # 文件元数据（行列数/sheet/编码等）
    "raw_df",  # 原始 DataFrame（只读，永不修改）
    "profile",  # ProfileResult（Day 3）
    "profile_error",  # 体检失败标记（避免每次 rerun 重复失败计算）
    "cleaning_plan",  # CleaningPlan（Day 5）
    "clean_df",  # 清洗后 DataFrame（Day 5）
    "cleaning_log",  # CleaningLog（Day 5）
    "analysis",  # AnalysisResult（Day 6-8）
    "analysis_key",  # 分析参数缓存指纹（同参数不重算）
    "trends",  # 趋势点缓存（Day 7）
    "trends_key",  # 趋势参数缓存指纹
    "ai_report",  # AIReport | None（Day 8-9）
)

# 用户偏好（跨文件保留）
PREFERENCE_KEYS: tuple[str, ...] = (
    "ai_mode",  # 本地 / 安全AI（默认）/ 增强AI
)

DEFAULT_STATE: dict[str, object] = {
    **{key: None for key in DATA_KEYS},
    "ai_mode": "secure",
}


def init_session_state() -> None:
    """初始化全部会话状态键（幂等）。"""
    for key, value in DEFAULT_STATE.items():
        st.session_state.setdefault(key, value)


def reset_downstream(upto: str = "raw_df") -> None:
    """清除指定键及其之后的所有下游数据状态（偏好键不受影响）。

    例如重选文件时 reset_downstream("raw_df")，
    会把 raw_df/profile/clean_df/analysis 等数据全部清空，ai_mode 保留。
    """
    if upto not in DATA_KEYS:
        raise ValueError(f"未知数据键: {upto}")
    for key in DATA_KEYS[DATA_KEYS.index(upto) :]:
        st.session_state.pop(key, None)
