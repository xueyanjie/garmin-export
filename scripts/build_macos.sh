#!/bin/bash
# Build a macOS .app. Must run on macOS.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [ ! -d ".venv-build" ]; then
    "$PYTHON" -m venv .venv-build
fi
# shellcheck disable=SC1091
source .venv-build/bin/activate
# 默认使用清华镜像加速；可通过 PIP_INDEX_URL 覆盖。
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt

rm -rf build dist
pyinstaller --noconfirm --clean GarminExporter.spec

echo
echo "构建完成：dist/GarminDataExporter.app"
echo "提示：未签名应用首次打开如被拦截，请右键 → 打开。"
