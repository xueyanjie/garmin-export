"""One-click launcher: create/repair .venv, install dependencies, start app.

This script deliberately uses only the standard library so it can run under any
Python 3 interpreter the user happens to have.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
APP = ROOT / "app.py"
STAMP = VENV / ".garmin_export_requirements"
MIN_PYTHON = (3, 12)
DEFAULT_INDEXES = (
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    None,  # official PyPI
    "https://mirrors.aliyun.com/pypi/simple/",
)


def say(message: str = "") -> None:
    print(message, flush=True)


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def python_ok(executable: str | list[str]) -> tuple[bool, str]:
    command = [executable] if isinstance(executable, str) else executable
    try:
        result = subprocess.run(
            [*command, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if result.returncode != 0:
        return False, ""
    version_text = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    try:
        major, minor = (int(part) for part in version_text.split(".", 1))
    except ValueError:
        return False, version_text
    return (major, minor) >= MIN_PYTHON, version_text


def find_base_python() -> tuple[list[str] | None, str]:
    candidates: list[list[str]] = []
    if sys.version_info >= MIN_PYTHON:
        candidates.append([sys.executable])
    if sys.platform == "win32":
        candidates.extend(
            [
                ["py", "-3.13"],
                ["py", "-3.12"],
                ["py", "-3"],
                ["python"],
                ["python3"],
            ]
        )
    else:
        candidates.extend(
            [
                ["python3.13"],
                ["python3.12"],
                ["python3"],
                ["/opt/homebrew/bin/python3"],
                ["/usr/local/bin/python3"],
                ["/usr/bin/python3"],
            ]
        )
    seen: set[str] = set()
    for command in candidates:
        key = " ".join(command)
        if key in seen:
            continue
        seen.add(key)
        ok, version = python_ok(command)
        if ok:
            return command, version
    return None, ""


def requirements_digest() -> str:
    payload = REQUIREMENTS.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def venv_ready(python: Path) -> bool:
    if not python.exists():
        return False
    try:
        stamp: str | None = STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        stamp = None
    if stamp is not None and stamp != requirements_digest():
        return False
    try:
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import PySide6, garminconnect, curl_cffi, requests",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    if stamp is None:
        try:
            STAMP.write_text(requirements_digest(), encoding="utf-8")
        except OSError:
            pass
    return True


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> None:
    say("  $ " + " ".join(command))
    subprocess.run(command, check=True, env=env)


def create_venv(base_command: list[str]) -> None:
    if VENV.exists():
        say("检测到不完整或过期的运行环境，正在重建 .venv …")
        shutil.rmtree(VENV, ignore_errors=True)
    say("正在创建 Python 虚拟环境（首次启动需要几分钟）…")
    run_checked([*base_command, "-m", "venv", str(VENV)])


def install_requirements(python: Path) -> None:
    say("正在安装依赖：PySide6、garminconnect、curl_cffi…")
    say("首次启动需要下载约 150 MB，请保持网络连接。")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    # A virtualenv created by uv can legitimately have no pip. Bootstrap pip
    # from the standard library so normal runs can repair the environment.
    probe = subprocess.run(
        [str(python), "-m", "pip", "--version"], capture_output=True, check=False
    )
    if probe.returncode != 0:
        say("正在初始化 pip…")
        run_checked([str(python), "-m", "ensurepip", "--upgrade"])
    base = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "-r",
        str(REQUIREMENTS),
    ]
    indexes: list[str | None]
    custom_index = os.environ.get("GARMIN_EXPORT_INDEX_URL") or os.environ.get(
        "PIP_INDEX_URL"
    )
    if custom_index:
        indexes = [custom_index]
    else:
        indexes = list(DEFAULT_INDEXES)
        say("优先使用清华镜像加速下载，失败时会自动回退到官方 PyPI。")
    errors: list[str] = []
    for index, index_url in enumerate(indexes):
        command = list(base)
        if index_url:
            say(f"使用软件源：{index_url}")
            command.extend(["--index-url", index_url])
        else:
            say("使用官方软件源：https://pypi.org/simple")
        try:
            run_checked(command, env=env)
            STAMP.write_text(requirements_digest(), encoding="utf-8")
            return
        except subprocess.CalledProcessError as exc:
            errors.append(str(exc))
            say("")
            say("该软件源安装失败，尝试下一个源…")
            say("")
    raise RuntimeError("依赖安装失败：\n" + "\n".join(errors[-3:]))


def launch(python: Path) -> int:
    say("")
    say("正在启动佳明数据导出…")
    if sys.platform == "win32":
        return subprocess.call([str(python), str(APP)], cwd=str(ROOT))
    os.chdir(ROOT)
    os.execv(str(python), [str(python), str(APP)])
    return 0


def pause_if_double_clicked() -> None:
    # On Windows the console window closes when the script exits; on macOS a
    # double-clicked .command window is also best kept open on error.
    if sys.platform == "win32" or sys.stdin.isatty():
        try:
            input("按回车键关闭窗口…")
        except EOFError:
            pass


def main() -> int:
    say("=" * 58)
    say("  佳明数据导出 · 一键启动")
    say("=" * 58)

    if not REQUIREMENTS.exists() or not APP.exists():
        say("启动失败：找不到 requirements.txt 或 app.py。")
        say("请确认整个程序目录完整，不要只复制单个文件。")
        pause_if_double_clicked()
        return 1

    python = venv_python()
    if python.exists() and venv_ready(python):
        return launch(python)

    base_command, base_version = find_base_python()
    if base_command is None:
        say("")
        say(f"未找到 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 或更高版本。")
        say("请先安装 Python，然后重新双击启动脚本：")
        say("  macOS / Windows 官网：https://www.python.org/downloads/")
        say("  Windows 也可以在终端执行：winget install Python.Python.3.12")
        say("  macOS 也可以在终端执行：brew install python@3.12")
        say("")
        say("安装时请勾选“Add Python to PATH”（Windows）。")
        pause_if_double_clicked()
        return 1

    say(f"使用 Python {base_version}（{' '.join(base_command)}）")
    try:
        if not python.exists():
            create_venv(base_command)
        elif not venv_ready(python):
            # Requirements changed or the environment was damaged. Reinstall
            # into the existing venv instead of deleting it when Python works.
            ok, _ = python_ok(str(python))
            if not ok:
                create_venv(base_command)
        if not venv_ready(python):
            install_requirements(python)
        if not venv_ready(python):
            raise RuntimeError("依赖安装完成，但导入检查仍然失败。")
        return launch(python)
    except subprocess.CalledProcessError as exc:
        say("")
        say(f"安装环境失败（退出码 {exc.returncode}）。")
        say("请检查网络、磁盘空间和 Python 安装，然后重试。")
        pause_if_double_clicked()
        return 1
    except Exception as exc:  # noqa: BLE001
        say("")
        say(f"启动失败：{exc}")
        pause_if_double_clicked()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
