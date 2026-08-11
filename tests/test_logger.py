"""日志模块冒烟测试：初始化幂等、敏感信息保护、非法级别回退。"""

from __future__ import annotations

import logging

import pytest

from utils.logger import get_logger, log_error_safe, setup_logging


def test_setup_logging_idempotent() -> None:
    """重复调用 setup_logging 不重复添加 handler。"""
    root = logging.getLogger("ai_excel")
    setup_logging()
    after_first = len(root.handlers)
    assert after_first > 0
    setup_logging()
    assert len(root.handlers) == after_first


def test_get_logger_auto_initializes() -> None:
    """多页面独立入口场景：直接 get_logger 也能拿到带 handler 的 logger。"""
    logger = get_logger("smoke")
    assert logger.name == "ai_excel.smoke"
    assert logging.getLogger("ai_excel").handlers, "root logger 应有 handler"


def test_log_error_safe_does_not_leak_full_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """error 级别只记录类型，完整异常消息截断后仅进 debug。"""
    logger = get_logger("leak_check")
    with caplog.at_level(logging.DEBUG, logger="ai_excel"):
        log_error_safe(
            logger,
            ValueError("列名: 姓名 值: 张三 长消息 " + "x" * 500),
            "测试阶段",
        )

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    err_msg = error_records[0].getMessage()
    assert "列名" not in err_msg  # error 行不含细节
    assert "测试阶段" in err_msg
    assert "ValueError" in err_msg

    # debug 记录存在且已截断
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug_records) == 1
    assert debug_records[0].getMessage().endswith("…")


def test_log_error_safe_with_short_message(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger("short_msg")
    with caplog.at_level(logging.DEBUG, logger="ai_excel"):
        log_error_safe(logger, ValueError("简单错误"), "清洗")
    assert "简单错误" in caplog.text
    assert "详细错误(截断)" in caplog.text


def test_invalid_log_level_falls_back_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """非法 LOG_LEVEL 回退 INFO，不崩溃。"""
    monkeypatch.setenv("LOG_LEVEL", "BANANA")
    # 重新加载模块（模拟新进程读取环境变量）
    import importlib

    import utils.logger as logger_module

    logger_module = importlib.reload(logger_module)
    assert logger_module._LEVEL == "INFO"  # noqa: SLF001


def test_default_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import importlib

    import utils.logger as logger_module

    logger_module = importlib.reload(logger_module)
    assert logger_module._LEVEL == "DEBUG"  # noqa: SLF001
