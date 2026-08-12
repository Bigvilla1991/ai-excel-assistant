"""AIEngine：固定结构 AI 报告生成（见方案 §12、§8.6）。

流程：
1. build_context 产出最小上下文（core/ai_context.py）；
2. 本地模式 / 未配置密钥 → template_report（确定性规则，数字全部来自上下文）；
3. LLM 调用（OpenAI 兼容接口，response_format=json_object）；
4. 输出经 AIReport 校验 + validate_report_numbers 数字交叉校验；
5. 失败 → 带修正提示重试 1 次 → 仍失败 → 模板报告回退。

安全约定（§13.2）：日志只记录调用状态与用量，不记录上下文内容。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI

from core.ai_validation import validate_report_numbers
from models.schemas import AIReport

# 本地 .env 加载（Streamlit 多页面下 app.py 不执行，需在模块入口加载）
load_dotenv()

logger = logging.getLogger("ai_excel.ai_engine")

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "data_analysis_prompt.md"
_MAX_ATTEMPTS = 2  # 首次调用 + 1 次修正重试

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _load_system_prompt() -> str:
    """读取系统提示词（prompts/data_analysis_prompt.md）。"""
    try:
        return _PROMPT_FILE.read_text(encoding="utf-8")
    except OSError:
        logger.warning("提示词文件缺失，使用内置最小提示词")
        return (
            "你是数据分析助手。只根据输入 JSON 中的数字撰写报告，不得编造数值。"
            "输出严格为 JSON 对象，含 7 个字段："
            "overview（字符串）、findings（数组）、trends（数组）、anomalies（数组）、"
            "causes（数组）、recommendations（数组）、quality_notes（数组）。"
        )


def report_text(report: AIReport) -> str:
    """报告全文拼接（供数字交叉校验）。"""
    sections = [
        report.overview,
        *report.findings,
        *report.trends,
        *report.anomalies,
        *report.causes,
        *report.recommendations,
        *report.quality_notes,
    ]
    return "\n".join(s for s in sections if s)


# ---------------------------------------------------------------- 模板报告（本地回退）


def template_report(context: dict[str, Any]) -> AIReport:
    """确定性模板报告：全部数字取自上下文，可追溯、可复现。"""
    ds = context.get("dataset", {})
    q = context.get("quality", {})
    analysis = context.get("analysis", {})
    rankings = context.get("rankings", [])
    trends = context.get("trends", [])
    anomalies = context.get("anomalies", [])
    issues = q.get("issues", [])

    metric = analysis.get("metric", "指标")
    total = analysis.get("total")

    overview_parts = [
        f"数据共 {ds.get('row_count', 0):,} 行、{ds.get('column_count', 0):,} 列，"
        f"健康评分 {q.get('health_score', 0)} 分"
    ]
    if total is not None:
        overview_parts.append(f"{metric}合计 {total:,.0f}")
    if analysis.get("dimension"):
        overview_parts.append(f"按「{analysis['dimension']}」分组")
    overview = "，".join(overview_parts) + "。"

    findings: list[str] = []
    if rankings:
        top1 = rankings[0]
        findings.append(
            f"「{top1['label']}」排名第一，{metric}为 {top1['value']:,.0f}"
            f"（占比 {top1['share'] * 100:.1f}%）。"
        )
        if len(rankings) > 1:
            top2 = rankings[1]
            findings.append(
                f"「{top2['label']}」排名第二，{metric}为 {top2['value']:,.0f}"
                f"（占比 {top2['share'] * 100:.1f}%）。"
            )
    if not findings:
        findings.append(
            f"当前视角下未生成排名结果，{metric}合计为 {total:,.0f}。"
            if total is not None
            else "当前视角下未生成排名结果。"
        )

    trend_lines: list[str] = []
    valid_trends = [t for t in trends if t.get("value") is not None]
    if trends:
        latest = trends[-1]
        if latest.get("value") is not None:
            change = latest.get("change_pct")
            if change is not None:
                trend_lines.append(
                    f"最近周期「{latest['period']}」{metric}为 {latest['value']:,.0f}，"
                    f"较上一周期变化 {change:+.1f}%。"
                )
            else:
                trend_lines.append(
                    f"最近周期「{latest['period']}」{metric}为 {latest['value']:,.0f}"
                    f"（无上一周期可比）。"
                )
        else:
            trend_lines.append(f"最近周期「{latest['period']}」无有效数值（该周期指标缺失）。")
        if valid_trends:
            peak = max(valid_trends, key=lambda t: t["value"])
            trend_lines.append(
                f"统计范围内峰值出现在「{peak['period']}」（{peak['value']:,.0f}）。"
            )

    anomaly_lines = [a for a in anomalies] or ["未检测到明显异常值（或未选择异常检测）。"]
    causes: list[str] = []
    recommendations = [
        "建议对排名靠前的分类进行业务复盘，确认驱动因素。",
        "若存在缺失或异常值，建议在「数据清洗」中处理后再做结论。",
    ]
    quality_notes = [i for i in issues] or ["未发现明显数据质量问题。"]

    return AIReport(
        overview=overview,
        findings=findings,
        trends=trend_lines,
        anomalies=anomaly_lines,
        causes=causes,
        recommendations=recommendations,
        quality_notes=quality_notes,
        source="template",
    )


# ---------------------------------------------------------------- LLM 调用


def _parse_report(content: str) -> AIReport | None:
    """解析 LLM 输出为 AIReport；失败或结构不完整返回 None。

    结构完整性：overview 与核心段落（findings/trends）必须非空，
    防止缺字段 JSON 被当作成功（提示词要求的 7 段结构）。
    """
    try:
        data = json.loads(content)
        report = AIReport.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("AI 输出解析失败: %s", type(exc).__name__)
        return None
    if not report.overview.strip() or not report.findings or not report.trends:
        logger.debug("AI 输出结构不完整（缺 overview/findings/trends）")
        return None
    return report


def _call_llm(
    client: OpenAI,
    system_prompt: str,
    context: dict[str, Any],
    model: str,
    fix_hint: str | None = None,
) -> str:
    """调用模型，返回原始内容字符串。"""
    user_content = json.dumps(context, ensure_ascii=False)
    if fix_hint:
        user_content += f"\n\n（修正要求：{fix_hint}）"
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content or ""


def generate_report(
    context: dict[str, Any],
    mode: str = "secure",
    api_key: str | None = None,
    client: OpenAI | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> AIReport:
    """生成 AI 报告（含校验、重试、模板回退）。

    - mode="local" 或未提供 api_key → 直接模板报告；
    - client 可注入 mock（测试不联网）；
    - 返回值 source 为 "ai"（LLM 成功）或 "template"（回退）。
    """
    system_prompt = _load_system_prompt()
    if mode == "local" or not api_key:
        logger.info("AI 报告：本地模式/无密钥 → 模板报告")
        return template_report(context)
    if mode not in ("secure", "enhanced"):
        raise ValueError(f"未知 AI 模式: {mode}（仅支持 local/secure/enhanced）")

    if client is None:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            timeout=60,
        )
    model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)

    fix_hint: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            content = _call_llm(client, system_prompt, context, model, fix_hint)
        except AuthenticationError:
            # 密钥无效：重试无意义，直接回退模板
            logger.warning("AI 鉴权失败（密钥可能无效），回退模板报告")
            return template_report(context)
        except Exception as exc:
            logger.warning("AI 调用失败（第 %d 次）: %s", attempt, type(exc).__name__)
            fix_hint = f"上次调用失败（{type(exc).__name__}），请重新生成。"
            continue

        report = _parse_report(content)
        if report is None:
            fix_hint = "上次输出不是合法 JSON 或结构不完整，请严格按 7 字段 JSON 输出。"
            continue

        problems = validate_report_numbers(report_text(report), context)
        if problems:
            fix_hint = f"上次输出包含无法溯源的数字（{problems}），请删除或修正这些数字。"
            continue

        logger.info("AI 报告生成成功 | attempts=%d source=ai", attempt)
        return report

    logger.warning("AI 报告多次尝试失败，回退模板报告")
    return template_report(context)
