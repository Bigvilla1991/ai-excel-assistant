"""应用统一异常体系。

约定：业务层抛 AppError 子类，UI 层捕获后转为友好的 st.error 提示，
避免裸 traceback 直接暴露给用户。
"""

from __future__ import annotations


class AppError(Exception):
    """应用统一异常基类，message 必须是可向用户展示的中文说明。"""


class FileValidationError(AppError):
    """文件校验失败：扩展名、大小、内容不合法。"""


class ParseError(AppError):
    """文件解析失败：无法读取或解析。"""


class ConfigError(AppError):
    """配置缺失或非法（如未配置 API Key）。"""
