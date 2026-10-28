"""Paths and small file helpers for the Garmin exporter."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

APP_NAME = "GarminDataExporter"
APP_TITLE = "佳明数据导出"
APP_VERSION = "1.0.0"

REGION_CN = "cn"
REGION_GLOBAL = "global"
REGIONS = (REGION_CN, REGION_GLOBAL)


def app_data_dir() -> Path:
    """Return the per-user application data directory."""
    override = os.environ.get("GARMIN_EXPORTER_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def session_dir(region: str) -> Path:
    if region not in REGIONS:
        raise ValueError(f"Unknown region: {region}")
    return app_data_dir() / "sessions" / region


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_export_dir() -> Path:
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.is_dir() else Path.home()
    return base / "Garmin导出"


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: Any, *, private: bool = False) -> None:
    """Atomically write readable UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        if private:
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_bytes(path: Path, data: bytes, *, private: bool = False) -> None:
    """Atomically write binary data, so an interrupted export cannot leave a
    truncated file that a later "skip existing" run mistakes for complete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if private:
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if private:
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
