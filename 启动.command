#!/bin/bash
# Double-click this file in Finder to start the app.
cd "$(dirname "$0")" || exit 1

# Finder-launched shells do not inherit the user's full PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if command -v python3 >/dev/null 2>&1; then
    python3 bootstrap.py
else
    /usr/bin/python3 bootstrap.py
fi
status=$?

# bootstrap.py replaces this shell process with the GUI on success. If it
# returns, an error occurred, so keep the Terminal window open for the message.
if [ "$status" -ne 0 ]; then
    echo
    read -r -n 1 -s -p "按任意键关闭窗口…"
    echo
fi
exit "$status"
