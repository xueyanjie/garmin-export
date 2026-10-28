#!/bin/bash
# Terminal launcher (macOS/Linux). The double-click entry points are
# 启动.command (macOS) and 启动.bat (Windows).
cd "$(dirname "$0")/.." || exit 1
exec python3 bootstrap.py
