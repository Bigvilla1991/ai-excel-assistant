"""DataProfiler 单元测试：类型推断、空值/重复/空白、IQR 异常、日期问题、健康评分。"""

from __future__ import annotations

import pandas as pd
import pytest

from core.profiler import profile


def _df(**columns: list[object]) -> pd.DataFrame:
    return pd.DataFrame(columns)


# ---------------------------------------------------------------- 类型推断


def test_infer_clean_types() -> None:
    df = _df(
        销售日期=["2024/1/5", "2024/1/6", "2024/1/7"],
        订单号=["ORD-001", "ORD-002", "ORD-003"],
        地区=["华东", "华北", "华东"],
        数量=[2, 5, 8],
        单价=[19.9, 50.5, 120.0],
        是否签约=["true", "false", "true"],
        备注=["正常", "加急", "正常"],
    )
    result = profile(df)
    by_name = {c.name: c for c in result.columns}

    assert by_name["销售日期"].inferred_type == "date"
    assert by_name["订单号"].inferred_type == "id"
    assert by_name["订单号"].is_id_like is True
    assert by_name["地区"].inferred_type == "category"
    assert by_name["数量"].inferred_type == "int"
    assert by_name["单价"].inferred_type == "float"
    assert by_name["是否签约"].inferred_type == "bool"
    assert by_name["备注"].inferred_type == "category"  # 3 个唯一值 → 分类


def test_high_cardinality_is_text() -> None:
    """高基数非唯一列 → 文本（唯一值 >30 且占比高）。"""
    df = _df(备注=[f"备注内容{i}" for i in range(100)])
    assert profile(df).columns[0].inferred_type == "text"


def test_id_by_name_keyword_even_if_numeric() -> None:
    """列名含编号关键词时，即使全为数字也不推断为数值。"""
    df = _df(证件编号=["110101199001011234", "310101199202022345", "440101199303033456"])
    result = profile(df)
    col = result.columns[0]
    assert col.inferred_type == "id"
    assert col.is_id_like is True


def test_all_unique_high_cardinality_is_id() -> None:
    """全唯一高基数列（非小数）判为编号列。"""
    df = _df(
        序列=[
            "A1001",
            "A1002",
            "A1003",
            "A1004",
            "A1005",
            "A1006",
            "A1007",
            "A1008",
            "A1009",
            "A1010",
        ]
    )
    col = profile(df).columns[0]
    assert col.inferred_type == "id"
    assert col.is_id_like is True


def test_float_column_not_misjudged_as_id() -> None:
    """小数列即使全唯一也不判编号（销售额场景）。"""
    df = _df(销售额=[100.5, 99.2, 200.1, 300.0, 150.7, 180.3, 90.8, 210.4, 320.6, 140.2])
    col = profile(df).columns[0]
    assert col.inferred_type == "float"
    assert col.is_id_like is False


def test_const_column() -> None:
    df = _df(来源=["线上", "线上", "线上"])
    col = profile(df).columns[0]
    assert col.is_constant is True
    assert col.inferred_type == "category"


# ---------------------------------------------------------------- 空值 / 重复 / 空白


def test_null_stats() -> None:
    df = _df(
        姓名=["张三", None, "李四", "", None],
        城市=["北京", "上海", "广州", "深圳", "杭州"],
    )
    result = profile(df)
    by_name = {c.name: c for c in result.columns}

    assert by_name["姓名"].null_count == 3  # None + "" 均计缺失
    assert by_name["姓名"].null_rate == pytest.approx(0.6)
    assert by_name["姓名"].high_missing is True
    assert by_name["城市"].null_count == 0
    assert result.null_cells == 3
    assert result.null_rate_total == pytest.approx(0.3)


def test_blank_rows_and_columns() -> None:
    df = _df(
        姓名=["张三", None, "李四"],
        城市=["北京", "", "上海"],
        备注=[None, None, None],
    )
    result = profile(df)
    assert result.blank_rows == 1  # 第 2 行全空
    assert result.blank_columns == ["备注"]


def test_duplicate_rows() -> None:
    df = _df(
        姓名=["张三", "张三", "李四", "李四", "李四"],
        城市=["北京", "北京", "上海", "上海", "南京"],
    )
    result = profile(df)
    assert result.duplicate_rows == 2  # (张三,北京) 与 (李四,上海) 各多 1 行


def test_empty_string_duplicate_ignored() -> None:
    """空字符串算缺失，但空值行不计入重复检测差异。"""
    df = _df(姓名=["张三", "", "李四"], 城市=["北京", "北京", "上海"])
    assert profile(df).duplicate_rows == 0


# ---------------------------------------------------------------- 异常值


def test_iqr_anomaly_detection() -> None:
    values = [float(i) for i in range(1, 101)]
    values += [10000.0, 20000.0]
    df = _df(数值=values)
    col = profile(df).columns[0]
    assert col.anomaly_count == 2  # 两个极端值


def test_iqr_small_sample_no_anomaly() -> None:
    df = _df(数值=[1.0, 2.0, 3.0, 4.0])
    assert profile(df).columns[0].anomaly_count == 0


# ---------------------------------------------------------------- 日期问题


def test_date_issues_detected() -> None:
    df = _df(日期=["2024/1/5", "2024-01-06", "2024年2月1日", "20240108", "不是日期"])
    col = profile(df).columns[0]
    assert col.inferred_type == "date"
    # 4 个候选格式全部解析成功 → date_issues=0；"不是日期"混入 → 类型冲突
    assert col.date_issues == 0
    assert col.type_conflict is True


def test_mixed_columns_not_dated() -> None:
    """多数值非日期格式（<80% 候选）不应推断为日期。"""
    df = _df(备注=["2024/1/5", "加急", "正常", "备注", "其他"])
    col = profile(df).columns[0]
    assert col.inferred_type != "date"
    assert col.date_issues == 0


# ---------------------------------------------------------------- 健康评分


def test_score_clean_data_100() -> None:
    df = _df(
        销售日期=["2024/1/5", "2024/1/6"],
        地区=["华东", "华北"],
        销售额=[100.5, 200.0],
    )
    assert profile(df).health_score == 100


def test_score_duplicates() -> None:
    df = _df(
        姓名=["张三", "张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十", "冯十一"],
        城市=["北京", "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安"],
    )
    # 重复占比 10% → 固定 5 + 10*0.5 = 扣 10 分
    assert profile(df).health_score == 90


def test_score_small_duplicates_floor() -> None:
    """重复占比很小（<10%）时固定 5 分兜底。"""
    df = _df(
        姓名=[
            "张三",
            "张三",
            "李四",
            "王五",
            "赵六",
            "孙七",
            "周八",
            "吴九",
            "郑十",
            "冯十一",
            "孙十二",
            "吴十三",
            "郑十四",
            "冯十五",
            "陈十六",
            "褚十七",
            "卫十八",
            "蒋十九",
            "沈二十",
            "韩廿一",
        ],
        城市=["城0", "城0"] + [f"城{i}" for i in range(2, 20)],
    )
    # 重复 1 行占比 5% → 固定 5 + 5*0.5 = 7.5 → 92.5 → 四舍五入 93
    assert profile(df).duplicate_rows == 1
    assert profile(df).health_score == 93


def test_score_blank_column_only_missing_deduction() -> None:
    """全空列按 100% 缺失扣 50 分（固定 3 分仅针对空白行）。"""
    df = _df(姓名=["张三", "李四"], 备注=[None, None])
    assert profile(df).health_score == 50


def test_score_missing() -> None:
    """高缺失列：空值率 50% → 扣 25 分（无其他扣分项干扰）。"""
    df = _df(
        姓名=["张三", None, None, "李四"],
        城市=["北京", "上海", "广州", "深圳"],
    )
    assert profile(df).health_score == 75


def test_score_constant() -> None:
    """常量列：扣 3 分（无缺失/重复干扰）。"""
    df = _df(
        姓名=["张三", "李四", "王五", "赵六"],
        来源=["线上", "线上", "线上", "线上"],
    )
    assert profile(df).health_score == 97


def test_score_date_and_type_conflict() -> None:
    df = _df(日期=["2024/1/5", "2024-01-06", "2024年2月1日", "20240108", "不是日期", "2024/3/3"])
    result = profile(df)
    # 5 个日期候选全部解析成功 → 无日期异常；"不是日期"占 1/6 → 类型冲突 5 分
    assert result.columns[0].date_issues == 0
    assert result.columns[0].type_conflict is True
    assert result.health_score == 95


def test_score_all_invalid_dates() -> None:
    """全列格式正确但值非法的日期（2024-99-99）：不静默降级，全部计入问题。"""
    df = _df(
        日期=["2024-99-99", "2024-13-45", "2024-02-30", "2024-00-10", "2024-01-00", "2024-99-01"]
    )
    col = profile(df).columns[0]
    assert col.inferred_type == "date"
    assert col.date_issues == 6
    assert col.type_conflict is True
    # 日期异常 5 + 类型冲突 5
    assert profile(df).health_score == 90


def test_score_blank_rows() -> None:
    df = _df(姓名=["张三", None], 城市=["北京", None])
    # 1 空白行 → 扣 3；姓名/城市空值率 50% → 各扣 25
    assert profile(df).health_score == 47


# ---------------------------------------------------------------- 边界与约束


def test_profile_does_not_modify_df() -> None:
    df = _df(姓名=["张三", None, "李四"], 数值=["1", "2", "3"])
    snapshot = df.copy(deep=True)
    profile(df)
    pd.testing.assert_frame_equal(df, snapshot)


def test_empty_dataframe() -> None:
    result = profile(pd.DataFrame())
    assert result.row_count == 0
    assert result.column_count == 0
    assert result.health_score == 100


def test_sample_values_preview() -> None:
    df = _df(姓名=["张三", "李四", "王五", "赵六", "孙七", "周八"])
    col = profile(df).columns[0]
    assert col.sample_values == ["张三", "李四", "王五", "赵六", "孙七"]


def test_null_rate_rounded() -> None:
    df = _df(姓名=["张三", None, "李四"])
    assert profile(df).columns[0].null_rate == pytest.approx(1 / 3, abs=0.0001)


# ---------------------------------------------------------------- reviewer 补测


def test_url_column_not_id() -> None:
    """URL 列全唯一也不判编号（编码风格判定排除 URL）。"""
    df = _df(链接=[f"https://example.com/page{i}.html" for i in range(10)])
    col = profile(df).columns[0]
    assert col.is_id_like is False
    assert col.inferred_type in ("text", "category")


def test_symbol_column_not_id() -> None:
    """列名含"号"但为类别值（符号 ✓/✗）不判编号。"""
    df = _df(符号=["✓", "✗", "✓", "✗", "✓", "✗", "✓", "✗", "✓", "✗"])
    col = profile(df).columns[0]
    assert col.is_id_like is False
    assert col.inferred_type == "category"


def test_model_column_is_id() -> None:
    """型号列名关键词仍正常判编号。"""
    df = _df(型号=[f"IPHONE-{i}" for i in range(10)])
    assert profile(df).columns[0].inferred_type == "id"


def test_chinese_year_month_date() -> None:
    """中文年月（无日）应推断为日期。"""
    df = _df(月份=["2024年2月", "2024年3月", "2024年4月", "2024年5月", "2024年6月"])
    col = profile(df).columns[0]
    assert col.inferred_type == "date"
    assert col.date_issues == 0


def test_zero_one_column_is_int_not_bool() -> None:
    """0/1 数字列推断为整数（数值优先级高于布尔）。"""
    df = _df(标记=[0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
    assert profile(df).columns[0].inferred_type == "int"


def test_iqr_five_row_boundary() -> None:
    """恰好 5 行且无异常：不误报。"""
    df = _df(数值=[10.0, 11.0, 12.0, 13.0, 100.0])
    assert profile(df).columns[0].anomaly_count == 1  # 100 超上界


def test_severity_high_duplicates_error() -> None:
    """重复占比 >5% → error 级问题。"""
    df = _df(
        姓名=["A", "A", "A", "B", "C", "D", "E", "F", "G", "H"],
        城市=["城0", "城0", "城0", "城3", "城4", "城5", "城6", "城7", "城8", "城9"],
    )
    issues = [i for i in profile(df).issues if i.category == "duplicate"]
    assert issues and issues[0].severity == "error"


def test_severity_extreme_missing_error() -> None:
    """空值率 ≥90% → error 级问题。"""
    df = _df(
        姓名=["A", None, None, None, None, None, None, None, None, None],
        城市=[f"城{i}" for i in range(10)],
    )
    issues = [i for i in profile(df).issues if i.category == "missing"]
    assert issues and issues[0].severity == "error"
