@echo off
REM ============================================================
REM  pose-mirror 一键安装脚本（Windows）
REM  功能：检查 Python、创建虚拟环境 .venv、安装依赖
REM  注意：本脚本只做环境安装，不会自动爬图和建索引
REM ============================================================
chcp 65001 >nul
setlocal

REM ---- 1. 检查 python 命令是否存在 ----
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python 命令。
    echo 请先从 https://www.python.org/downloads/ 下载安装 Python 3.10+，
    echo 安装时务必勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)

REM ---- 2. 检查 Python 版本是否 >= 3.10 ----
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [错误] 需要 Python 3.10 或更高版本，当前版本：
    python --version
    echo 请去 https://www.python.org/downloads/ 下载新版。
    pause
    exit /b 1
)
echo [OK] Python 检查通过：
python --version

REM ---- 3. 创建虚拟环境（已存在则跳过） ----
if not exist ".venv" (
    echo [1/3] 正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
) else (
    echo [1/3] 虚拟环境 .venv 已存在，跳过创建。
)

REM ---- 4. 安装依赖（可能需要几分钟） ----
echo [2/3] 正在安装依赖 ...
".venv\Scripts\python" -m pip install --upgrade pip
if errorlevel 1 (
    echo [错误] pip 升级失败，请检查网络后重试。
    pause
    exit /b 1
)
".venv\Scripts\python" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

REM ---- 5. 以开发模式安装本项目（之后可直接 python -m posemirror.xxx） ----
echo [3/3] 正在注册项目包 ...
".venv\Scripts\python" -m pip install -e . --no-deps >nul
if errorlevel 1 (
    echo [警告] 项目包注册失败，但依赖已装好，可继续手动使用。
)

echo.
echo ============================================================
echo  安装完成！接下来三步（复制粘贴即可）：
echo    1. 爬取参考图： .venv\Scripts\python -m posemirror.crawl_wikimedia --limit 50
echo    2. 构建索引：   .venv\Scripts\python -m posemirror.build_index
echo    3. 启动服务：   .venv\Scripts\python -m posemirror.server
echo  然后浏览器打开 http://127.0.0.1:8000
echo ============================================================
pause
