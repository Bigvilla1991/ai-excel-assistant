# AI Excel 数据处理助手（AI Excel Assistant）

面向行政、销售、运营、财务辅助人员和小微企业经营者，提供低门槛的 Excel 数据处理工具：

**上传文件 → 数据体检 → 一键清洗 → 统计分析 → 图表展示 → AI 解读 → 导出结果**

> 核心原则：**Python 负责准确计算，AI 负责解释数据。** 所有总计、平均值、排名、趋势和异常检测均由确定性代码完成，大模型只接收结构化汇总结果。

## 快速开始

```bash
# 1. 创建虚拟环境（Python 3.12）
py -3.12 -m venv .venv

# 2. 安装依赖
.venv\Scripts\pip install -r requirements.txt
# 或 Windows 双击 run.bat 一键完成 2/3 步

# 3. 配置密钥（可选，不配置则使用模板报告）
copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 4. 启动
.venv\Scripts\streamlit run app.py
```

## 功能

- 数据体检：空值、重复、类型、异常值、健康评分
- 一键清洗：去重、格式统一、缺失值策略、金额归一化，全部可撤销
- 统计分析：基础统计、维度分组、TOP/BOTTOM 排名、时间趋势
- 图表：折线 / 柱状 / 横向排名 / 散点（Plotly 交互式）
- AI 解读：基于结构化结果生成固定格式报告（DeepSeek，可关闭）
- 导出：清洗数据、多 Sheet 分析工作簿、HTML 报告

## 隐私与安全

- 本地模式：数据不发送给任何模型
- 安全 AI 模式（默认）：仅发送字段名、汇总统计、趋势和异常摘要，不发送完整记录
- 增强 AI 模式：经你明确同意后，发送少量脱敏样本
- 密钥只存于 `.env`（本地）或 Streamlit Cloud Secrets（线上），不进入代码库

## 已知限制（V1.0）

- 仅支持 `.xlsx` / `.csv`，单文件 ≤ 20MB，建议 ≤ 10 万行
- 不支持多 Sheet 批量处理与多文件合并（V1.1 规划）
- 不执行模型生成的任意代码

## 目录结构

```
app.py                # 首页
pages/                # Streamlit 多页面
core/                 # 核心计算模块（无 Streamlit 依赖）
models/schemas.py     # 类型化模型（Pydantic）
utils/                # 工具（日志、文件、格式）
prompts/              # AI 提示词
scripts/              # 演示与测试数据生成
tests/                # 单元与集成测试
samples/              # 演示数据
```

## 开发

```bash
.venv\Scripts\ruff check .        # 静态检查
.venv\Scripts\pytest              # 测试
.venv\Scripts\streamlit run app.py
```
