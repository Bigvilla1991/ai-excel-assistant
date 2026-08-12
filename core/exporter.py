"""ExcelExporter：工作簿与报告导出（见方案 §14）。

安全约定（§13.2）：
- 公式注入防护：以 = + - @ 及制表符开头的**非数值文本**单元格前置单引号，
  使其在 Excel 中按文本显示、不触发公式执行（负数等合法数值不受影响）；
- 所有导出函数返回 bytes，不落盘（页面通过 st.download_button 交付）；
- 样式适度：表头加粗+底色、自动列宽、冻结首行、开启筛选、数字格式。
"""

from __future__ import annotations

import html
import io
import re
from datetime import date, datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from models.schemas import AIReport, AnalysisResult, CleaningLog, ProfileResult

# 公式注入危险前缀（Excel CSV 注入常见向量）
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
# 合法数值：整数/小数/负号，排除前导零（007）、下划线（1_000）、科学计数法、NaN/inf
_NUMERIC_PATTERN = re.compile(r"^[+-]?(?:0|[1-9]\d*)(?:\.\d+)?$")
# 金额列名识别（命中即应用 #,##0.00 格式，方案 §14.4）
_MONEY_COLUMN_PATTERN = re.compile(r"(金额|销售额|单价|成本|利润|价格|收入|支出|金额|额)")
_MAX_COL_WIDTH = 30
_MONEY_FORMAT = "#,##0.00"
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="1F6FEB", end_color="1F6FEB", fill_type="solid")


def _is_money_column(name: str) -> bool:
    return bool(_MONEY_COLUMN_PATTERN.search(name))


def sanitize_cell(value: Any) -> Any:
    """单元格净化：合法数值保持数值；危险前缀的非数值文本前置 '（防公式注入）。

    数值判定用严格正则：前导零（007）、下划线分隔（1_000）、NaN/inf、
    科学计数法均按文本保留原文，不静默改写（与 excel_reader 保留原文承诺一致）。
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()  # openpyxl 写为日期单元格
    if isinstance(value, (datetime, date)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value

    text = str(value).strip()
    if text == "":
        return None
    if _NUMERIC_PATTERN.match(text):
        return float(text)
    if text.startswith(_DANGEROUS_PREFIXES):
        return "'" + text  # 转义为文本，Excel 不执行
    return text


def _write_sheet(
    wb: Workbook, title: str, df: pd.DataFrame, money_cols: list[str] | None = None
) -> None:
    """写入数据表：表头样式、冻结、筛选、自动列宽、金额格式。

    money_cols 缺省时按列名自动识别金额列（金额/销售额/单价等，§14.4）。
    """
    ws = wb.create_sheet(title=title[:31])
    if money_cols is not None:
        money = set(money_cols)
    else:
        money = {str(c) for c in df.columns if _is_money_column(str(c))}

    headers = [str(c) for c in df.columns]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    for row in df.itertuples(index=False, name=None):
        ws.append([sanitize_cell(v) for v in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # 列宽（按内容估算，截断上限）
    for idx, col in enumerate(df.columns, start=1):
        letter = get_column_letter(idx)
        max_len = len(str(col))
        for v in df[col].head(200):
            max_len = max(max_len, len(str(v)))
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), _MAX_COL_WIDTH)

    # 金额列数字格式
    for idx, col in enumerate(df.columns, start=1):
        if str(col) in money:
            for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
                for cell in row:
                    cell.number_format = _MONEY_FORMAT


def build_cleaned_workbook(df: pd.DataFrame, cleaned: bool = True) -> bytes:
    """清洗结果工作簿：数据 + 清洗说明。"""
    wb = Workbook()
    wb.remove(wb.active)
    _write_sheet(wb, "清洗数据", df)
    note = wb.create_sheet("清洗说明")
    note.append(["说明"])
    note.append(["本工作簿由 AI Excel 数据处理助手导出。"])
    note.append(["数据来源：", "清洗后数据" if cleaned else "原始数据（未清洗）"])
    note.append(["提示：", "以单引号 ' 开头的单元格为文本保护，Excel 中不会执行公式。"])
    for cell in note[1]:
        cell.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_analysis_workbook(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    profile: ProfileResult,
    analysis: AnalysisResult,
    log: CleaningLog | None = None,
    report: AIReport | None = None,
) -> bytes:
    """分析工作簿（7 Sheet，见方案 §14.2）。"""
    wb = Workbook()
    wb.remove(wb.active)

    _write_sheet(wb, "原始数据", raw)
    _write_sheet(wb, "清洗数据", clean)

    # 数据质量
    quality_rows = pd.DataFrame(
        {
            "指标": ["总行数", "总列数", "健康评分", "空值格数", "重复行数", "空白行数"],
            "数值": [
                profile.row_count,
                profile.column_count,
                profile.health_score,
                profile.null_cells,
                profile.duplicate_rows,
                profile.blank_rows,
            ],
        }
    )
    _write_sheet(wb, "数据质量", quality_rows)
    issues_df = pd.DataFrame(
        [
            {
                "级别": i.severity,
                "类别": i.category,
                "问题": i.message,
                "涉及字段": "、".join(i.columns),
            }
            for i in profile.issues
        ]
    )
    _write_sheet(wb, "问题清单", issues_df)

    # 汇总统计
    stats_rows = []
    for col_name, stats in analysis.statistics.items():
        row: dict[str, Any] = {"字段": col_name}
        row.update({k: v if v is not None else "" for k, v in stats.items()})
        stats_rows.append(row)
    _write_sheet(
        wb, "汇总统计", pd.DataFrame(stats_rows) if stats_rows else pd.DataFrame({"字段": []})
    )

    # 排名分析
    if analysis.rankings:
        rank_df = pd.DataFrame(
            [
                {"排名": r.rank, "分类": r.label, "数值": r.value, "占比": r.share}
                for r in analysis.rankings
            ]
        )
    else:
        rank_df = pd.DataFrame({"排名": [], "分类": [], "数值": [], "占比": []})
    _write_sheet(wb, "排名分析", rank_df)

    # 趋势分析
    if analysis.trends:
        trend_df = pd.DataFrame(
            [
                {
                    "周期": t.period,
                    "数值": t.value if t.value is not None else "",
                    "环比(%)": t.change_pct,
                }
                for t in analysis.trends
            ]
        )
    else:
        trend_df = pd.DataFrame({"周期": [], "数值": [], "环比(%)": []})
    _write_sheet(wb, "趋势分析", trend_df)

    # 清洗日志
    if log is not None and log.actions:
        log_df = pd.DataFrame(
            [
                {
                    "动作": a.action,
                    "影响字段": "、".join(a.columns),
                    "影响行数": a.rows_affected,
                    "影响单元格": a.cells_affected,
                    "说明": a.description,
                }
                for a in log.actions
            ]
        )
        log_df.loc[len(log_df)] = [
            "合计",
            "",
            log.rows_before - log.rows_after,
            "",
            f"{log.rows_before} 行 → {log.rows_after} 行",
        ]
    else:
        log_df = pd.DataFrame(
            {"动作": [], "影响字段": [], "影响行数": [], "影响单元格": [], "说明": []}
        )
    _write_sheet(wb, "清洗日志", log_df)

    # AI 报告（有则追加）
    if report is not None:
        rpt_df = pd.DataFrame(
            [
                {"段落": "数据概况", "内容": report.overview},
                *[{"段落": "核心发现", "内容": item} for item in report.findings],
                *[{"段落": "趋势变化", "内容": item} for item in report.trends],
                *[{"段落": "异常情况", "内容": item} for item in report.anomalies],
                *[{"段落": "可能原因", "内容": item} for item in report.causes],
                *[{"段落": "建议关注", "内容": item} for item in report.recommendations],
                *[{"段落": "数据质量提醒", "内容": item} for item in report.quality_notes],
            ]
        )
        _write_sheet(wb, "AI报告", rpt_df)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_report_markdown(report: AIReport) -> str:
    """AI 报告 Markdown 文本（可直接编辑、转发）。"""
    lines = [
        "# AI 数据分析报告",
        "",
        f"> 生成时间：{report.generated_at:%Y-%m-%d %H:%M} ｜ "
        f"来源：{'AI 模型' if report.source == 'ai' else '本地模板'}",
        "",
        "## 数据概况",
        report.overview,
        "",
        "## 核心发现",
    ]
    lines += [f"- {item}" for item in report.findings] or ["（无）"]
    lines += ["", "## 趋势变化"]
    lines += [f"- {item}" for item in report.trends] or ["（无）"]
    lines += ["", "## 异常情况"]
    lines += [f"- {item}" for item in report.anomalies] or ["（无）"]
    lines += ["", "## 可能原因（推断）"]
    lines += [f"- {item}" for item in report.causes] or ["（无）"]
    lines += ["", "## 建议关注事项"]
    lines += [f"- {item}" for item in report.recommendations] or ["（无）"]
    lines += ["", "## 数据质量提醒"]
    lines += [f"- {item}" for item in report.quality_notes] or ["（无）"]
    lines += ["", "---", "本报告由 AI Excel 数据处理助手生成，仅供参考，不视为专业审计或决策依据。"]
    return "\n".join(lines)


def build_report_html(
    report: AIReport,
    figures: list[go.Figure],
    include_plotlyjs: str = "cdn",
) -> str:
    """AI 报告 HTML（内嵌交互图表）。

    include_plotlyjs：默认 cdn（需联网）；"inline" 内嵌（离线可开，体积大）。
    """
    plot_divs = []
    for i, fig in enumerate(figures):
        plot_divs.append(
            f'<div class="chart">{fig.to_html(full_html=False, include_plotlyjs="cdn" if i else include_plotlyjs)}</div>'
        )

    sections = [
        ("数据概况", f"<p>{html.escape(report.overview)}</p>"),
        ("核心发现", _ul(report.findings)),
        ("趋势变化", _ul(report.trends)),
        ("异常情况", _ul(report.anomalies)),
        ("可能原因（推断）", _ul(report.causes)),
        ("建议关注事项", _ul(report.recommendations)),
        ("数据质量提醒", _ul(report.quality_notes)),
    ]
    body = "\n".join(f"<h2>{t}</h2>\n{c}" for t, c in sections)
    source_label = "AI 模型" if report.source == "ai" else "本地模板"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>AI 数据分析报告</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; color: #222; }}
h1 {{ color: #1F6FEB; }} h2 {{ border-bottom: 1px solid #eee; padding-bottom: 4px; margin-top: 28px; }}
.chart {{ margin: 12px 0; }}
.caption {{ color: #666; font-size: 13px; }}
</style>
</head>
<body>
<h1>AI 数据分析报告</h1>
<p class="caption">生成时间：{report.generated_at:%Y-%m-%d %H:%M} ｜ 来源：{source_label}</p>
{body}
{chr(10).join(plot_divs)}
<hr>
<p class="caption">本报告由 AI Excel 数据处理助手生成，仅供参考，不视为专业审计或决策依据。</p>
</body>
</html>"""


def _ul(items: list[str]) -> str:
    if not items:
        return "<p>（无）</p>"
    # html.escape：防止 AI 输出/原始数据中的脚本注入 HTML 报告（分享型 XSS）
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"
