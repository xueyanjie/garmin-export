"""Date-range exporter with a Qt-free core (easy to test)."""

from __future__ import annotations

import gzip
import io
import logging
import re
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from .config import HEALTH_LABELS
from .paths import (
    APP_TITLE,
    APP_VERSION,
    human_size,
    write_bytes,
    write_json,
    write_text,
)

LOGGER = logging.getLogger(__name__)

ProgressCallback = Callable[[int | None, int | None, str], None]
LogCallback = Callable[[str], None]


class ExportCancelled(Exception):
    """Raised internally when the user presses Cancel."""


class ExportAborted(Exception):
    """Raised after repeated network failures make continuing pointless."""


@dataclass(slots=True)
class ExportOptions:
    start: date
    end: date
    activities: bool
    health: tuple[str, ...]
    skip_existing: bool = True
    request_delay: float = 0.35


@dataclass(slots=True)
class ExportResult:
    directory: Path
    status: str
    manifest: dict[str, Any] = field(default_factory=dict)


def iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class Exporter:
    """Export activities and daily health data for one account."""

    def __init__(
        self,
        garmin: Any,
        options: ExportOptions,
        target_dir: Path,
        *,
        account: dict[str, Any] | None = None,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        if options.start > options.end:
            raise ValueError("开始日期不能晚于结束日期")
        self.garmin = garmin
        self.options = options
        self.target = target_dir
        self.account = account or {}
        self._progress = progress or (lambda current, total, message: None)
        self._log = log or (lambda message: None)
        self.cancel_event = cancel_event or threading.Event()
        self._total = 0
        self._done = 0
        self._started_at = datetime.now(timezone.utc)
        self._counts: dict[str, Any] = {
            "activities": {
                "found": 0,
                "summary": 0,
                "details": 0,
                "fit": 0,
                "skipped": 0,
                "failed": 0,
            },
            "health": {"written": 0, "empty": 0, "skipped": 0, "failed": 0},
        }
        self._errors: list[dict[str, str]] = []
        self._manifest: dict[str, Any] = {}
        self._unknown_total = False
        self._consecutive_failures = 0
        self._days = list(iter_dates(options.start, options.end))

    # ------------------------------------------------------------------ public
    def run(self) -> ExportResult:
        self.target.mkdir(parents=True, exist_ok=True)
        self._manifest = {
            "app": APP_TITLE,
            "version": APP_VERSION,
            "account": self.account,
            "range": {
                "start": self.options.start.isoformat(),
                "end": self.options.end.isoformat(),
                "days": len(self._days),
            },
            "options": {
                "activities": self.options.activities,
                "health": list(self.options.health),
                "skip_existing": self.options.skip_existing,
            },
            "started_at": self._started_at.isoformat(timespec="seconds"),
            "finished_at": None,
            "status": "running",
            "counts": self._counts,
            "errors": self._errors,
        }

        status = "success"
        try:
            self._log(f"导出目录：{self.target}")
            if self.options.activities:
                self._export_activities_phase()
            else:
                self._set_total(len(self._days) * len(self.options.health))
            self._export_health_phase()
        except ExportCancelled:
            status = "cancelled"
            self._log("已取消导出，已完成的文件会保留。")
        except GarminConnectAuthenticationError as exc:
            status = "auth_error"
            self._record_error("登录会话", exc)
            self._log("登录会话已失效，导出中止。请重新登录后再试。")
        except Exception as exc:  # noqa: BLE001 - surfaced via manifest and UI
            status = "failed"
            self._record_error("导出", exc)
            self._log(f"导出中止：{exc}")
        finally:
            if status == "success" and self._errors:
                status = "partial"
            self._manifest["status"] = status
            self._manifest["finished_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self._write_manifest()
            self._write_readme()
            self._progress(
                self._done,
                self._total if self._total else None,
                "完成" if status == "success" else status,
            )

        if status == "auth_error":
            raise GarminConnectAuthenticationError("登录会话已失效，请重新登录")
        return ExportResult(directory=self.target, status=status, manifest=self._manifest)

    # ----------------------------------------------------------------- helpers
    def _set_total(self, total: int) -> None:
        self._total = max(0, total)
        self._progress(0, self._total, "准备导出…")

    def _tick(self, message: str) -> None:
        self._done += 1
        self._progress(self._done, self._total, message)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise ExportCancelled

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            self._check_cancel()
            time.sleep(min(0.2, end - time.monotonic()))

    def _call(self, label: str, func: Callable[[], Any]) -> Any:
        """Run one API call, with cancel checks and 429 backoff."""
        attempts = 3
        for attempt in range(1, attempts + 1):
            self._check_cancel()
            try:
                result = func()
                self._consecutive_failures = 0
                self._sleep(self.options.request_delay)
                return result
            except GarminConnectTooManyRequestsError:
                if attempt >= attempts:
                    raise
                wait = 45 * attempt
                self._log(
                    f"{label}触发了 Garmin 频率限制，等待 {wait} 秒后重试"
                    f"（{attempt}/{attempts - 1}）…"
                )
                self._sleep(wait)
            except GarminConnectAuthenticationError:
                raise
            except Exception as exc:  # noqa: BLE001
                if _is_no_data_error(exc):
                    self._consecutive_failures = 0
                    return None
                self._consecutive_failures += 1
                if self._consecutive_failures >= 5:
                    raise ExportAborted(
                        f"连续 {self._consecutive_failures} 次请求失败，已中止导出。"
                        f"最后一次错误：{exc}"
                    ) from exc
                raise
        raise RuntimeError("unreachable")

    def _record_error(self, scope: str, exc: BaseException) -> None:
        message = str(exc).strip()
        if len(message) > 800:
            message = message[:800] + "…"
        self._errors.append(
            {
                "scope": scope,
                "type": type(exc).__name__,
                "message": message,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        LOGGER.warning("%s: %s", scope, message)

    def _write_manifest(self) -> None:
        try:
            write_json(self.target / "manifest.json", self._manifest)
        except OSError as exc:
            self._log(f"写入 manifest.json 失败：{exc}")

    def _write_readme(self) -> None:
        text = f"""# {APP_TITLE} 导出说明

- 账号区服：{self.account.get("region_label", "")}
- 账号：{self.account.get("email", "")}
- 日期范围：{self.options.start.isoformat()} 至 {self.options.end.isoformat()}
- 导出时间：{self._started_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")}
- 状态：{self._manifest.get("status", "")}

## 目录结构

- `activities/activities.json`：日期范围内的活动列表（Garmin 原始 JSON）
- `activities/<日期>_<ID>_<名称>/activity.json`：活动概要
- `activities/<日期>_<ID>_<名称>/details.json`：活动详情（采样点/图表数据）
- `activities/<日期>_<ID>_<名称>/activity_<ID>.fit`：Garmin 原始 FIT 文件
- `health/YYYY-MM-DD_<类型>.json`：每日健康数据，`data` 字段为 Garmin 原始响应
- `manifest.json`：导出清单、统计与错误记录

健康类型包括：sleep（睡眠）、heart_rate（心率）、steps（步数）、
stress（压力）、body_battery（身体电量）、hrv（HRV）。

某天没有数据时仍会生成该 JSON，`data` 为 `null`、`[]` 或 `{{}}`。
活动列表可能包含 Garmin 自动识别的活动；个别活动没有 FIT 文件时会保留
`activity_<ID>_original.zip` 并在 `manifest.json` 中记录。
"""
        try:
            write_text(self.target / "README.md", text)
        except OSError:
            pass

    # -------------------------------------------------------------- activities
    def _export_activities_phase(self) -> None:
        self._progress(None, None, "正在获取活动列表…")
        self._log("正在获取活动列表…")
        activities: list[dict[str, Any]] = []
        try:
            raw = self._call(
                "活动列表",
                lambda: self.garmin.get_activities_by_date(
                    self.options.start.isoformat(),
                    self.options.end.isoformat(),
                    sortorder="asc",
                ),
            )
            if isinstance(raw, dict):
                raw = raw.get("activityList") or raw.get("activities") or []
            if isinstance(raw, list):
                activities = [item for item in raw if isinstance(item, dict)]
            self._counts["activities"]["found"] = len(activities)
            write_json(self.target / "activities" / "activities.json", activities)
            self._log(f"找到 {len(activities)} 个活动。")
        except ExportCancelled:
            raise
        except GarminConnectAuthenticationError:
            raise
        except ExportAborted:
            raise
        except Exception as exc:  # noqa: BLE001
            self._record_error("活动列表", exc)
            self._log(f"获取活动列表失败：{exc}")

        total = 1 + len(activities) * 3 + len(self._days) * len(self.options.health)
        self._total = total
        self._done = 1  # the list request
        self._progress(self._done, self._total, "活动列表完成")

        for index, activity in enumerate(activities, start=1):
            self._check_cancel()
            self._export_one_activity(activity, index, len(activities))

    def _export_one_activity(
        self, activity: dict[str, Any], index: int, count: int
    ) -> None:
        activity_id = activity.get("activityId")
        if activity_id in (None, ""):
            self._log(f"跳过无 activityId 的活动（{index}/{count}）。")
            self._tick("跳过无效活动")
            self._tick("跳过无效活动")
            self._tick("跳过无效活动")
            return
        activity_id = str(activity_id)
        folder = self._activity_folder(activity, activity_id)
        folder.mkdir(parents=True, exist_ok=True)
        name = activity.get("activityName") or folder.name
        self._log(f"[{index}/{count}] 活动 {name}（{activity_id}）")

        summary_path = folder / "activity.json"
        if self._skip(summary_path):
            self._counts["activities"]["skipped"] += 1
        else:
            try:
                summary = self._call(
                    f"活动 {activity_id} 概要",
                    lambda: self.garmin.get_activity(activity_id),
                )
                write_json(summary_path, summary)
                self._counts["activities"]["summary"] += 1
            except ExportCancelled:
                raise
            except GarminConnectAuthenticationError:
                raise
            except ExportAborted:
                raise
            except Exception as exc:  # noqa: BLE001
                self._counts["activities"]["failed"] += 1
                self._record_error(f"活动 {activity_id} 概要", exc)
        self._tick(f"活动概要 {name}")

        details_path = folder / "details.json"
        if self._skip(details_path):
            self._counts["activities"]["skipped"] += 1
        else:
            try:
                details = self._call(
                    f"活动 {activity_id} 详情",
                    lambda: self.garmin.get_activity_details(activity_id),
                )
                write_json(details_path, details)
                self._counts["activities"]["details"] += 1
            except ExportCancelled:
                raise
            except GarminConnectAuthenticationError:
                raise
            except ExportAborted:
                raise
            except Exception as exc:  # noqa: BLE001
                self._counts["activities"]["failed"] += 1
                self._record_error(f"活动 {activity_id} 详情", exc)
        self._tick(f"活动详情 {name}")

        fit_path = folder / f"activity_{activity_id}.fit"
        if self._skip(fit_path):
            self._counts["activities"]["skipped"] += 1
            self._tick(f"活动 FIT {name}")
            return
        try:
            raw = self._call(
                f"活动 {activity_id} FIT",
                lambda: self.garmin.download_activity(
                    activity_id,
                    self.garmin.ActivityDownloadFormat.ORIGINAL,
                ),
            )
            files = self._extract_fit(activity_id, raw, folder)
            if files:
                self._counts["activities"]["fit"] += 1
                self._log(
                    f"  FIT 已保存：{', '.join(p.name for p in files)}"
                    f"（{human_size(sum(p.stat().st_size for p in files))}）"
                )
            else:
                raise ValueError("Garmin 返回的原始文件中没有 FIT 文件")
        except ExportCancelled:
            raise
        except GarminConnectAuthenticationError:
            raise
        except ExportAborted:
            raise
        except Exception as exc:  # noqa: BLE001
            self._counts["activities"]["failed"] += 1
            self._record_error(f"活动 {activity_id} FIT", exc)
            self._log(f"  FIT 下载失败：{exc}")
        self._tick(f"活动 FIT {name}")

    def _activity_folder(self, activity: dict[str, Any], activity_id: str) -> Path:
        start = str(activity.get("startTimeLocal") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
            start = "unknown-date"
        name = activity.get("activityName")
        if not name:
            activity_type = activity.get("activityType")
            if isinstance(activity_type, dict):
                name = activity_type.get("typeKey")
        name = str(name or "activity")
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = re.sub(r"\s+", "_", name)
        name = re.sub(r"_+", "_", name).strip(" ._")
        name = name[:48] or "activity"
        return self.target / "activities" / f"{start}_{activity_id}_{name}"

    def _skip(self, path: Path) -> bool:
        if self.options.skip_existing and path.is_file():
            self._log(f"  已存在，跳过：{path.name}")
            return True
        return False

    def _extract_fit(
        self, activity_id: str, raw: Any, folder: Path
    ) -> list[Path]:
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            raise ValueError("下载内容为空")
        data = bytes(raw)

        # Some endpoints occasionally return a JSON error with HTTP 200.
        if data.lstrip().startswith(b"{"):
            snippet = data[:300].decode("utf-8", "replace")
            raise ValueError(f"Garmin 返回了错误信息：{snippet}")

        if data.startswith(b"\x1f\x8b"):
            data = gzip.decompress(data)

        if data.startswith(b"PK\x03\x04"):
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile as exc:
                raise ValueError("原始文件 ZIP 已损坏") from exc
            fit_names = [n for n in archive.namelist() if n.lower().endswith(".fit")]
            saved: list[Path] = []
            with archive:
                for index, member in enumerate(fit_names):
                    info = archive.getinfo(member)
                    if info.is_dir():
                        continue
                    suffix = "" if index == 0 else f"_{index + 1}"
                    target = folder / f"activity_{activity_id}{suffix}.fit"
                    write_bytes(target, archive.read(member))
                    saved.append(target)
            if not saved:
                fallback = folder / f"activity_{activity_id}_original.zip"
                write_bytes(fallback, data)
                self._log(f"  原始包中没有 FIT，已保留 ZIP：{fallback.name}")
            return saved

        # A bare FIT response starts with a 12/14-byte header and ".FIT" at offset 8.
        if len(data) >= 12 and data[8:12] == b".FIT":
            target = folder / f"activity_{activity_id}.fit"
            write_bytes(target, data)
            return [target]

        fallback = folder / f"activity_{activity_id}_original.bin"
        write_bytes(fallback, data)
        raise ValueError(f"无法识别的原始文件格式，已保存为 {fallback.name}")

    # ------------------------------------------------------------------ health
    def _export_health_phase(self) -> None:
        if not self.options.health:
            return
        self._log(
            f"开始导出 {len(self._days)} 天的健康数据（{len(self.options.health)} 类）…"
        )
        health_dir = self.target / "health"
        health_dir.mkdir(parents=True, exist_ok=True)
        for day in self._days:
            for key in self.options.health:
                self._check_cancel()
                path = health_dir / f"{day.isoformat()}_{key}.json"
                label = HEALTH_LABELS.get(key, key)
                if self._skip(path):
                    self._counts["health"]["skipped"] += 1
                    self._tick(f"{day.isoformat()} {label}（跳过）")
                    continue
                try:
                    data = self._fetch_health(key, day)
                    write_json(path, self._health_payload(day, key, label, data))
                    self._counts["health"]["written"] += 1
                    if data is None or data == [] or data == {}:
                        self._counts["health"]["empty"] += 1
                        self._log(f"{day.isoformat()} {label}：无数据")
                    else:
                        self._log(f"{day.isoformat()} {label}：已保存")
                except ExportCancelled:
                    raise
                except GarminConnectAuthenticationError:
                    raise
                except ExportAborted:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if _is_no_data_error(exc):
                        write_json(path, self._health_payload(day, key, label, None))
                        self._counts["health"]["written"] += 1
                        self._counts["health"]["empty"] += 1
                        self._log(f"{day.isoformat()} {label}：无数据")
                    else:
                        self._counts["health"]["failed"] += 1
                        self._record_error(f"{day.isoformat()} {label}", exc)
                        self._log(f"{day.isoformat()} {label}：失败（{exc}）")
                self._tick(f"{day.isoformat()} {label}")

    def _health_payload(
        self, day: date, key: str, label: str, data: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "date": day.isoformat(),
            "type": key,
            "label": label,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data,
        }
        if key == "steps":
            total = _steps_total(data)
            if total is not None:
                payload["summary"] = {"steps": total}
        return payload

    def _fetch_health(self, key: str, day: date) -> Any:
        iso = day.isoformat()
        if key == "sleep":
            return self._call("睡眠数据", lambda: self.garmin.get_sleep_data(iso))
        if key == "heart_rate":
            return self._call("心率数据", lambda: self.garmin.get_heart_rates(iso))
        if key == "steps":
            return self._call("步数数据", lambda: self.garmin.get_steps_data(iso))
        if key == "stress":
            return self._call("压力数据", lambda: self.garmin.get_stress_data(iso))
        if key == "body_battery":
            return self._call(
                "身体电量", lambda: self.garmin.get_body_battery(iso, iso)
            )
        if key == "hrv":
            return self._call("HRV 数据", lambda: self.garmin.get_hrv_data(iso))
        raise ValueError(f"未知健康数据类型：{key}")


def _is_no_data_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if text.strip() == "no data":
        return True
    # garminconnect uses several phrasings, e.g. "No data received from server"
    # and "No heart rate data received".
    return bool(
        re.search(r"\bno\b[^.]{0,40}\bdata\b[^.]{0,20}\b(received|found|available)\b", text)
    )


def _steps_total(data: Any) -> int | None:
    """Best-effort daily total from Garmin's intraday steps buckets."""
    if isinstance(data, dict):
        for key in ("totalSteps", "steps"):
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(value)
        return None
    if not isinstance(data, list):
        return None
    total = 0.0
    found = False
    for row in data:
        if not isinstance(row, dict):
            continue
        value = row.get("steps")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value)
            found = True
    return round(total) if found else None
