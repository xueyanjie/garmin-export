"""Persisted, non-secret user preferences."""

from __future__ import annotations

import copy
import json
from typing import Any

from .paths import (
    REGION_CN,
    REGIONS,
    config_path,
    default_export_dir,
    write_json,
)

HEALTH_KEYS = ("sleep", "heart_rate", "steps", "stress", "body_battery", "hrv")
HEALTH_LABELS = {
    "sleep": "睡眠",
    "heart_rate": "心率",
    "steps": "步数",
    "stress": "压力",
    "body_battery": "身体电量",
    "hrv": "HRV",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "region": REGION_CN,
    "email": "",
    "export_dir": str(default_export_dir()),
    "skip_existing": True,
    "export_activities": True,
    "health": {key: True for key in HEALTH_KEYS},
}


def _defaults() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def load_config() -> dict[str, Any]:
    config = _defaults()
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    if not isinstance(raw, dict):
        return config

    if raw.get("region") in REGIONS:
        config["region"] = raw["region"]
    if isinstance(raw.get("email"), str):
        config["email"] = raw["email"]
    if isinstance(raw.get("export_dir"), str) and raw["export_dir"].strip():
        config["export_dir"] = raw["export_dir"]
    if isinstance(raw.get("skip_existing"), bool):
        config["skip_existing"] = raw["skip_existing"]
    if isinstance(raw.get("export_activities"), bool):
        config["export_activities"] = raw["export_activities"]

    health = raw.get("health")
    if isinstance(health, dict):
        for key in HEALTH_KEYS:
            if isinstance(health.get(key), bool):
                config["health"][key] = health[key]
    return config


def save_config(config: dict[str, Any]) -> None:
    safe = _defaults()
    region = config.get("region")
    if region in REGIONS:
        safe["region"] = region
    email = config.get("email")
    if isinstance(email, str):
        safe["email"] = email.strip()
    export_dir = config.get("export_dir")
    if isinstance(export_dir, str) and export_dir.strip():
        safe["export_dir"] = export_dir
    for key in ("skip_existing", "export_activities"):
        if isinstance(config.get(key), bool):
            safe[key] = config[key]
    health = config.get("health")
    if isinstance(health, dict):
        for key in HEALTH_KEYS:
            if isinstance(health.get(key), bool):
                safe["health"][key] = health[key]
    try:
        write_json(config_path(), safe, private=True)
    except OSError:
        # Preferences are not essential enough to block the UI on disk errors.
        pass
