# AI Excel 数据处理助手（AI Excel Assistant）

面向行政、销售、运营、财务辅助人员和小微企业经营者，提供低门槛的 Excel 数据处理工具：

**上传文件 → 数据体检 → 一键清洗 → 统计分析 → 图表展示 → AI 解读 → 导出结果**

> 核心原则：**Python 负责准确计算，AI 负责解释数据。** 所有总计、平均值、排名、趋势和异常检测均由确定性代码完成，大模型只接收结构化汇总结果。

## 快速开始（Windows，约 5 分钟）

```bash
# 方式一：双击 run.bat（自动完成以下全部步骤）
run.bat

# 方式二：手动
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # 可选：编辑 .env 填入 DEEPSEEK_API_KEY
.venv\Scripts\streamlit run app.py
```

浏览器访问 http://localhost:8501，上传 `samples/demo_sales.xlsx` 即可体验完整流程。

> 不配置密钥也能完整使用：AI 报告将使用本地模板（数字全部可溯源）。

## 功能

- **数据体检**：空值、重复、类型、异常值、健康评分、问题清单
- **一键清洗**：去重、格式统一、缺失值策略、金额归一化，全程可预览/撤销
- **统计分析**：基础统计、维度分组、TOP/BOTTOM 排名、时间趋势（含环比）
- **图表**：折线（峰值标注）/ 柱状 / 横向排名 / 散点（Plotly 交互式，与汇总表同源）
- **AI 解读**：固定 7 段结构报告 + **数字交叉校验防幻觉**（DeepSeek，可关闭）
- **导出**：清洗数据、9 Sheet 分析工作簿、Markdown / HTML 报告（内嵌图表）

## 隐私与安全

| 模式 | 数据去向 |
|---|---|
| 本地模式 | 不发送任何数据给模型，仅本地计算 + 模板报告 |
| 安全 AI 模式（默认） | 仅发送字段名、汇总统计、趋势和异常摘要，不发送完整记录 |
| 增强 AI 模式 | 经你明确同意后，发送每字段最多 3 个样例值 |

- API 密钥只存于 `.env`（本地）或 Streamlit Cloud Secrets（线上），不进入代码库
- 上传校验扩展名/大小/解压体积/列数；导出时公式注入防护（`=` 开头的文本不触发公式）
- 日志只记录处理阶段与规模，不记录原始数据内容
- 对财务、医疗、人事等敏感数据，请先确认组织政策与数据授权

## 演示与测试数据

```bash
.venv\Scripts\python scripts\generate_sample_data.py   # 一键生成（可重复）
```

生成 8 个文件（见 `samples/`）：销售演示（含脏数据）、GBK 编码 CSV、
干净/脏数据/混合日期/中文字符/多 Sheet/5 万行大表等测试数据。

## 部署（Streamlit Cloud 在线演示）

1. 推送到 GitHub 仓库，在 [Streamlit Cloud](https://streamlit.io/cloud) 选择仓库与 `app.py`
2. 配置密钥：Settings → Secrets 填入（对应本地 `.env` 内容）：
   ```toml
   DEEPSEEK_API_KEY = "sk-..."
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   DEEPSEEK_MODEL = "deepseek-chat"
   ```
3. 建议线上环境限制：文件 ≤20MB（已内置）、会话超时提示（Streamlit Cloud 免费额度 3 小时）
4. 首页与「隐私与说明」页已明示数据处理规则：在线演示环境请勿上传真实敏感数据

## 已知限制（V1.0）

- 仅支持 `.xlsx` / `.csv`，单文件 ≤ 20MB，建议 ≤ 10 万行
- 不支持多 Sheet 批量处理与多文件合并（V1.1 规划）
- 不执行模型生成的任意代码
- 在线演示为单会话内存处理，不提供数据存储

## 目录结构

```
app.py                # 首页
pages/                # Streamlit 多页面（上传/体检/清洗/分析/AI/导出/隐私）
core/                 # 核心计算模块（无 Streamlit 依赖）
models/schemas.py     # 类型化模型（Pydantic）
utils/                # 工具（日志、文件、格式、会话、UI）
prompts/              # AI 提示词
scripts/              # 演示与测试数据生成
tests/                # 单元与集成测试（258+ 用例，覆盖率 96%）
samples/              # 演示数据（生成器产出，不提交）
```

## 开发

```bash
.venv\Scripts\ruff check .        # 静态检查
.venv\Scripts\ruff format .       # 代码格式化
.venv\Scripts\pytest              # 全量测试
.venv\Scripts\pytest --cov=core --cov=models --cov=utils   # 覆盖率
.venv\Scripts\streamlit run app.py
```

## 版本记录

- V1.0 MVP：六步主流程全通，14 天迭代完成（Day 1-13 已交付，Day 14 部署与试用）
