#!/usr/bin/env bash
# ============================================================
#  pose-mirror 一键安装脚本（Linux / macOS）
#  功能：检查 Python、创建虚拟环境 .venv、安装依赖
#  注意：本脚本只做环境安装，不会自动爬图和建索引
#  用法：bash setup.sh
# ============================================================
set -euo pipefail

# ---- 1. 检查 python3 命令是否存在 ----
if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+（https://www.python.org/downloads/）"
  exit 1
fi

# ---- 2. 检查 Python 版本是否 >= 3.10 ----
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "[错误] 需要 Python 3.10 或更高版本，当前：$(python3 --version 2>&1)"
  echo "请升级 Python 后重试。"
  exit 1
fi
echo "[OK] Python 检查通过：$(python3 --version 2>&1)"

# ---- 3. 创建虚拟环境（已存在则跳过） ----
if [ ! -d ".venv" ]; then
  echo "[1/3] 正在创建虚拟环境 .venv ..."
  python3 -m venv .venv
else
  echo "[1/3] 虚拟环境 .venv 已存在，跳过创建。"
fi

# ---- 4. 安装依赖（可能需要几分钟） ----
echo "[2/3] 正在安装依赖 ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

# ---- 5. 以开发模式安装本项目（之后可直接 python -m posemirror.xxx） ----
echo "[3/3] 正在注册项目包 ..."
.venv/bin/python -m pip install -e . --no-deps -q || echo "[警告] 项目包注册失败，但依赖已装好，可继续手动使用。"

echo ""
echo "============================================================"
echo " 安装完成！接下来三步（复制粘贴即可）："
echo "   1. 爬取参考图： .venv/bin/python -m posemirror.crawl_wikimedia --limit 50"
echo "   2. 构建索引：   .venv/bin/python -m posemirror.build_index"
echo "   3. 启动服务：   .venv/bin/python -m posemirror.server"
echo " 然后浏览器打开 http://127.0.0.1:8000"
echo "============================================================"
