# 部署指南：GitHub + Streamlit Cloud

目标：把本项目部署为可公网访问的在线演示（免费）。

## 一、推送到 GitHub

### 方式 A：命令行（推荐）

1. 安装 GitHub CLI：`winget install GitHub.cli`
2. 登录（浏览器授权一次）：
   ```bash
   gh auth login
   # 选择 GitHub.com → HTTPS → 用浏览器登录，按提示在浏览器中确认
   ```
3. 创建仓库并推送：
   ```bash
   cd D:\AI Excel Assistant\ai-excel-assistant
   gh repo create ai-excel-assistant --public --source . --push
   ```

### 方式 B：网页操作

1. 打开 https://github.com/new 创建仓库 `ai-excel-assistant`（Public）
2. 本机执行：
   ```bash
   git remote add origin https://github.com/<你的用户名>/ai-excel-assistant.git
   git push -u origin master
   ```

> 注意：仓库不包含 `samples/` 数据文件（gitignore），部署后如需演示数据，
> 在 Streamlit Cloud 的终端（若有）或本地生成后另行处理；在线演示建议用
> 上传功能直接传 `demo_sales.xlsx`。

## 二、部署到 Streamlit Cloud

1. 打开 https://share.streamlit.io 或 https://streamlit.io/cloud，用 **GitHub 账号登录**
2. 点击 **New app** → 选择仓库 `ai-excel-assistant` → Branch `master` → Main file `app.py`
3. 点击 **Deploy**，等待 1~3 分钟构建完成（自动执行 `pip install -r requirements.txt`）
4. 部署完成后获得公网链接，如 `https://<app名>.streamlit.app`

## 三、配置 AI 密钥（可选）

1. 在应用页面点 **Manage app → Settings → Secrets**
2. 粘贴（对应本地 `.env` 内容）：
   ```toml
   DEEPSEEK_API_KEY = "sk-你的密钥"
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   DEEPSEEK_MODEL = "deepseek-chat"
   ```
3. 保存后点 **Rerun**，AI 模式即启用（不配置则自动使用本地模板，功能完整可用）

## 四、上线前检查清单

- [ ] 首页与「隐私与说明」页的在线演示数据规则已明示（已内置）
- [ ] 单文件 ≤ 20MB（已内置 `maxUploadSize`）
- [ ] 演示数据不含敏感信息
- [ ] 已知限制在 README 中说明（已内置）
- [ ] 验证在线流程：上传 → 体检 → 清洗 → 分析 → AI → 导出

## 五、常见问题

| 问题 | 处理 |
|---|---|
| 部署失败：依赖安装错误 | 查看 Deploy 日志；确认 `requirements.txt` 版本可被 pip 解析（已锁定） |
| 应用内存不足 | 社区版约 1GB，处理 10 万行以内数据足够；超限提示已内置 |
| 会话超时 | 社区版空闲 3 小时重置，属正常 |
| 国内访问慢 | 海外服务器所致；正式服务建议迁移到国内服务器或本地交付 |

## 六、取消部署

Streamlit Cloud → Manage app → Settings → Delete app（不影响 GitHub 仓库）。
