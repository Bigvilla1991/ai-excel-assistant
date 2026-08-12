"""展示格式化工具：字段类型标签、通俗说明、数字格式。"""

from __future__ import annotations

from models.schemas import TypeName

# 字段类型 → 中文标签（UI 表格展示）
TYPE_LABELS: dict[str, str] = {
    "text": "文本",
    "int": "整数",
    "float": "小数",
    "bool": "布尔",
    "date": "日期",
    "category": "分类",
    "id": "编号",
}

# 字段类型 → 通俗说明（面向非技术用户）
TYPE_DESCRIPTIONS: dict[str, str] = {
    "text": "自由文本（如备注、地址），一般不适合直接做统计。",
    "int": "整数数值（如数量、次数），可参与求和、平均。",
    "float": "小数数值（如金额、单价），可参与求和、平均。",
    "bool": "是/否类标记（true/false）。",
    "date": "日期或时间（如 2024/1/5），可按日、周、月、季度分析趋势。",
    "category": "取值有限的分类（如地区、商品、渠道），适合分组统计和排名。",
    "id": "疑似编号（如订单号、证件号）。虽然可能全是数字，但**不参与求和**，只作唯一标识。",
}


# 类型说明展示顺序
TYPE_LABELS_ORDER: tuple[str, ...] = ("date", "int", "float", "bool", "category", "id", "text")


def type_label(type_name: TypeName | str) -> str:
    """类型 → 中文标签（未知类型原样返回）。"""
    return TYPE_LABELS.get(type_name, str(type_name))


def type_description(type_name: TypeName | str) -> str:
    """类型 → 通俗说明。"""
    return TYPE_DESCRIPTIONS.get(type_name, "")
