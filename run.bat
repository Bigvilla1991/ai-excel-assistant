@echo off
rem AI Excel 数据处理助手 - 一键启动
rem 首次运行会自动创建虚拟环境并安装依赖；再次运行直接启动。
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境（Python 3.12）...
    py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
    if errorlevel 1 (
        echo 创建虚拟环境失败，请先安装 Python 3.12 并勾选 "Add to PATH"。
        pause
        exit /b 1
    )
)

echo [2/3] 检查依赖...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

if not exist ".env" (
    echo [3/3] 生成 .env 配置文件（可选配置 DEEPSEEK_API_KEY）...
    copy ".env.example" ".env" >nul
)

echo 启动应用：浏览器将自动打开 http://localhost:8501
".venv\Scripts\streamlit" run app.py
pause
