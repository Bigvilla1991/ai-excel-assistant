"""演示与测试数据一键生成（方案 §18.1）。

用法：
    python scripts/generate_sample_data.py          # 生成全部
    python scripts/generate_sample_data.py --clean   # 生成前先清空 samples/

产物（samples/ 目录，已 gitignore）：
    demo_sales.xlsx         1200 行销售演示数据（含脏数据：空值/异常值/重复/带空格）
    demo_sales_gbk.csv      GBK 编码版（编码检测演示）
    test_clean.xlsx         干净的标准销售数据
    test_dirty.xlsx         空值、重复、异常值数据
    test_dates.xlsx         混合日期格式（含中文年月、非法日期）
    test_chinese.xlsx       中文字段与特殊字符数据
    test_sheets.xlsx        多 Sheet + 空 Sheet + 仅表头 Sheet
    test_large.csv          50,000 行（行数上限附近，性能演示）

确定性：随机种子固定，重复生成结果一致。
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

SALESMEN = ["张伟", "李娜", "王芳", "刘洋", "陈静", "杨帆"]
REGIONS = ["华东", "华北", "华南", "西南"]
PRODUCTS = ["产品A", "产品B", "产品C", "产品D"]


def _sales_frame(n: int, seed: int = 42) -> pd.DataFrame:
    """标准销售数据（干净）。"""
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime(
        pd.date_range("2024-01-01", periods=n, freq="6h")
        .to_series()
        .sample(n, random_state=seed)
        .values
    )
    rows = pd.DataFrame(
        {
            "销售日期": dates.strftime("%Y/%m/%d"),
            "订单号": [f"ORD-{10000 + i:05d}" for i in range(n)],
            "销售人员": rng.choice(SALESMEN, size=n),
            "地区": rng.choice(REGIONS, size=n),
            "商品": rng.choice(PRODUCTS, size=n),
            "数量": rng.integers(1, 50, size=n),
            "单价": rng.uniform(10, 500, size=n).round(2),
        }
    )
    rows["销售额"] = (rows["数量"] * rows["单价"]).round(2)
    return rows


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


def generate_all(clean: bool = False) -> list[Path]:
    """生成全部样例，返回产物路径列表。"""
    if clean and SAMPLES_DIR.exists():
        shutil.rmtree(SAMPLES_DIR)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / ".gitkeep").touch()  # 保持空目录可被 git 跟踪

    produced: list[Path] = []

    # 1. 演示销售数据（1200 行 + 脏数据注入）
    demo = _sales_frame(1200)
    demo.loc[10, "销售人员"] = None
    demo.loc[20, "销售日期"] = "2024/13/45"  # 非法日期
    demo.loc[30, "销售额"] = None
    demo.loc[100, "销售额"] = 99_999_999  # 异常值
    demo.loc[120, "订单号"] = "ORD-10020"  # 重复（整行复制）
    demo.loc[121] = demo.loc[120]
    demo.loc[125, "地区"] = " 华东 "  # 带空格
    demo_path = SAMPLES_DIR / "demo_sales.xlsx"
    _write_xlsx(demo_path, {"销售明细": demo})
    produced.append(demo_path)

    # GBK 编码 CSV（编码检测演示）
    gbk_path = SAMPLES_DIR / "demo_sales_gbk.csv"
    demo.head(200).to_csv(gbk_path, index=False, encoding="gbk")
    produced.append(gbk_path)

    # 2. 测试数据：干净
    clean_df = _sales_frame(300, seed=1)
    p = SAMPLES_DIR / "test_clean.xlsx"
    _write_xlsx(p, {"数据": clean_df})
    produced.append(p)

    # 3. 测试数据：脏（空值/重复/异常）
    dirty = _sales_frame(300, seed=2)
    dirty.loc[:200, "销售人员"] = None  # 高缺失（66%）
    dirty = pd.concat([dirty, dirty.loc[100:101]], ignore_index=True)  # 追加完整重复
    dirty.loc[150, "销售额"] = 9_999_999  # 异常值
    dirty.loc[60, "数量"] = None
    p = SAMPLES_DIR / "test_dirty.xlsx"
    _write_xlsx(p, {"数据": dirty})
    produced.append(p)

    # 4. 测试数据：混合日期格式
    dates_df = pd.DataFrame(
        {
            "日期": [
                "2024/1/5", "2024-01-06", "2024年2月1日", "20240108",
                "2024年3月", "2024-04-30", "2024/5/12", "2024-13-45",
                "2024年6月3日", "2024/7/7",
            ],
            "数值": [str(i) for i in range(10)],
        }
    )
    p = SAMPLES_DIR / "test_dates.xlsx"
    _write_xlsx(p, {"数据": dates_df})
    produced.append(p)

    # 5. 测试数据：中文字段与特殊字符
    chinese = pd.DataFrame(
        {
            "姓名": ["张三", "李四", "王五", "赵六", "孙七"],
            "备注": ["含￥符号", "含，中文逗号", "含\t制表符", "含 空格", "正常"],
            "数值": ["1,234.50", "2,345", "100", "200.5", "300"],
        }
    )
    p = SAMPLES_DIR / "test_chinese.xlsx"
    _write_xlsx(p, {"数据": chinese})
    produced.append(p)

    # 6. 测试数据：多 Sheet / 空 Sheet / 仅表头
    header_only = pd.DataFrame(columns=["姓名", "城市", "数值"])
    p = SAMPLES_DIR / "test_sheets.xlsx"
    _write_xlsx(
        p,
        {
            "销售": _sales_frame(50, seed=3),
            "空Sheet": pd.DataFrame(),
            "仅表头": header_only,
        },
    )
    produced.append(p)

    # 7. 测试数据：接近行数上限（50,000 行 CSV）
    large = _sales_frame(50_000, seed=4)
    large_path = SAMPLES_DIR / "test_large.csv"
    large.to_csv(large_path, index=False, encoding="utf-8")
    produced.append(large_path)

    return produced


def main() -> None:
    parser = argparse.ArgumentParser(description="生成演示与测试数据")
    parser.add_argument("--clean", action="store_true", help="生成前清空 samples/ 目录")
    args = parser.parse_args()

    produced = generate_all(clean=args.clean)
    print(f"已生成 {len(produced)} 个样例文件：")
    for path in produced:
        print(f"  {path.relative_to(SAMPLES_DIR.parent)}  ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
