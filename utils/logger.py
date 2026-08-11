"""统一日志模块。

安全约定（见方案 §17.4）：
- 只记录处理阶段、耗时、行列规模、错误类型和版本信息；
- 严禁记录：原始表格内容、敏感字段值、API 密钥、完整文件路径细节。
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "app.log"

# 非法级别值回退到 INFO，避免配置笔误导致应用启动崩溃
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if _LEVEL not in _VALID_LEVELS:
    _LEVEL = "INFO"

_MAX_ERR_LEN = 200


def get_logger(name: str) -> logging.Logger:
    """获取应用统一 logger（带控制台 + 轮转文件输出）。

    惰性初始化：首次调用自动完成 setup，Streamlit 多页面每个脚本都是
    独立入口，无需在每个页面手动调用 setup_logging()。
    """
    setup_logging()
    return logging.getLogger(f"ai_excel.{name}")


def setup_logging(console: bool = True, file: bool = True) -> None:
    """初始化根 logger。重复调用幂等。"""
    root = logging.getLogger("ai_excel")
    if root.handlers:
        return

    root.setLevel(_LEVEL)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    if file:
        _LOG_DIR.mkdir(exist_ok=True)
        fh = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    root.info("logger initialized (level=%s, file=%s)", _LEVEL, _LOG_FILE)


def log_error_safe(logger: logging.Logger, exc: Exception, context: str) -> None:
    """记录异常，但剥离可能包含敏感信息的异常消息细节。

    只记录异常类型与外部上下文，异常消息本身（可能含文件路径、列名等）
    降级为 debug，并截断至 _MAX_ERR_LEN 字符。
    """
    logger.error("处理失败 | 阶段: %s | 错误类型: %s", context, type(exc).__name__)
    detail = str(exc)
    if len(detail) > _MAX_ERR_LEN:
        detail = detail[:_MAX_ERR_LEN] + "…"
    logger.debug("详细错误(截断): %s", detail)
