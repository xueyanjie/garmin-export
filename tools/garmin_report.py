#!/usr/bin/env python3
"""生成一份自包含的中文佳明数据 HTML 分析报告。

用法:
    python tools/garmin_report.py "/path/to/garmin_export_2026-10-22_2026-10-28"

只使用 Python 标准库；图表全部是内联 SVG，不依赖 CDN 或网络。
"""
from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

CN = timezone(timedelta(hours=8), "CST")
UTC = timezone.utc
WEEKDAYS = "一二三四五六日"

# ---------- 基础工具 ----------


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def num(value: Any, digits: int = 0, dash: str = "—") -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return dash
    if digits == 0:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def fmt_hm(seconds: Any, *, pad_hours: bool = False) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours or pad_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def fmt_short(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    return f"{hours}:{rem // 60:02d}"


def fmt_hm_cn(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}小时{minutes:02d}分"
    return f"{minutes}分"


def fmt_pace(seconds_per_km: Any) -> str:
    if not isinstance(seconds_per_km, (int, float)) or seconds_per_km <= 0:
        return "—"
    total = int(round(seconds_per_km))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def fmt_km(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value / 1000:.{digits}f}"


def weekday_cn(date_str: str) -> str:
    try:
        return "周" + WEEKDAYS[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    except ValueError:
        return ""


def day_md(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d")
    except ValueError:
        return date_str


def hhmm_from_garmin_local(ms: Any) -> str:
    if not isinstance(ms, (int, float)):
        return "—"
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%H:%M")


def minutes_from_midnight(ms: Any) -> float | None:
    if not isinstance(ms, (int, float)):
        return None
    dt = datetime.fromtimestamp(ms / 1000, UTC)
    return dt.hour * 60 + dt.minute + dt.second / 60


def safe_div(a: Any, b: Any) -> float | None:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or b == 0:
        return None
    return a / b


def safe_mean(values: Sequence[Any]) -> float | None:
    clean = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(clean) / len(clean) if clean else None


def pearson(xs: Sequence[Any], ys: Sequence[Any]) -> float | None:
    pairs = [
        (x, y)
        for x, y in zip(xs, ys)
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and not isinstance(x, bool)
        and not isinstance(y, bool)
    ]
    if len(pairs) < 3:
        return None
    mx = sum(p[0] for p in pairs) / len(pairs)
    my = sum(p[1] for p in pairs) / len(pairs)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mx) ** 2 for x, _ in pairs) * sum((y - my) ** 2 for _, y in pairs)
    )
    return numerator / denominator if denominator else None


def lerp_color(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    a = tuple(int(c1[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# ---------- SVG 工具 ----------


class Plot:
    def __init__(
        self,
        width: int,
        height: int,
        *,
        left: int = 52,
        right: int = 22,
        top: int = 30,
        bottom: int = 44,
    ) -> None:
        self.w = width
        self.h = height
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
        self.iw = width - left - right
        self.ih = height - top - bottom

    def x(self, index: int, count: int) -> float:
        return self.left + (index + 0.5) * self.iw / max(1, count)

    def y(self, value: float, lo: float, hi: float) -> float:
        if hi == lo:
            return self.top + self.ih / 2
        return self.top + (hi - value) / (hi - lo) * self.ih


def svg_text(
    x: float,
    y: float,
    text: Any,
    *,
    anchor: str = "start",
    cls: str = "ax",
    extra: str = "",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'class="{cls}" {extra}>{esc(text)}</text>'
    )


def svg_line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str = "#e2e8f0",
    width: float = 1,
    dash: str = "",
    extra: str = "",
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{width}"{dash_attr} {extra}/>'
    )


def svg_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str,
    rx: float = 3,
    extra: str = "",
    title: str = "",
) -> str:
    title_tag = f"<title>{esc(title)}</title>" if title else ""
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(0.0, w):.1f}" '
        f'height="{max(0.0, h):.1f}" rx="{rx}" fill="{fill}" {extra}>'
        f"{title_tag}</rect>"
    )


def svg_circle(
    x: float, y: float, r: float, *, fill: str, stroke: str = "#fff", sw: float = 1.5, title: str = ""
) -> str:
    title_tag = f"<title>{esc(title)}</title>" if title else ""
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}">{title_tag}</circle>'
    )


def seg_paths(points: Sequence[tuple[float | None, float | None]]) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, y in points:
        if x is None or y is None:
            if current:
                segments.append(current)
                current = []
        else:
            current.append((x, y))
    if current:
        segments.append(current)
    return segments


def path_d(points: Sequence[tuple[float | None, float | None]]) -> str:
    parts: list[str] = []
    for segment in seg_paths(points):
        parts.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in segment))
    return " ".join(parts)


def area_d(points: Sequence[tuple[float | None, float | None]], base_y: float) -> str:
    parts: list[str] = []
    for segment in seg_paths(points):
        parts.append(
            f"M{segment[0][0]:.1f},{base_y:.1f} "
            + " L".join(f"{x:.1f},{y:.1f}" for x, y in segment)
            + f" L{segment[-1][0]:.1f},{base_y:.1f} Z"
        )
    return " ".join(parts)


def svg_doc(width: int, height: int, body: str, label: str) -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{esc(label)}">'
        f"{body}</svg>"
    )


def hgrid(
    plot: Plot,
    lo: float,
    hi: float,
    ticks: Sequence[float],
    *,
    fmt=lambda v: f"{v:g}",
    right: bool = False,
    dash: str = "",
) -> str:
    parts: list[str] = []
    for tick in ticks:
        y = plot.y(tick, lo, hi)
        parts.append(
            svg_line(
                plot.left,
                y,
                plot.left + plot.iw,
                y,
                stroke="#e8edf4",
                dash=dash,
            )
        )
        if right:
            parts.append(
                svg_text(
                    plot.left + plot.iw + 8,
                    y + 4,
                    fmt(tick),
                    anchor="start",
                    cls="ax",
                )
            )
        else:
            parts.append(
                svg_text(plot.left - 8, y + 4, fmt(tick), anchor="end", cls="ax")
            )
    return "".join(parts)


def day_xlabels(plot: Plot, days: Sequence[dict[str, Any]], *, y: float | None = None) -> str:
    y = y if y is not None else plot.top + plot.ih + 22
    parts = []
    for i, day in enumerate(days):
        x = plot.x(i, len(days))
        parts.append(svg_text(x, y, day_md(day["date"]), anchor="middle", cls="ax-strong"))
        parts.append(svg_text(x, y + 14, weekday_cn(day["date"]), anchor="middle", cls="ax2"))
    return "".join(parts)


# ---------- 数据加载 ----------


def build_activity(root: Path, activity: dict[str, Any]) -> dict[str, Any] | None:
    activity_id = str(activity.get("activityId"))
    folders = [
        p
        for p in (root / "activities").iterdir()
        if p.is_dir() and f"_{activity_id}_" in p.name
    ]
    folder = folders[0] if folders else None
    detail = load_json(folder / "details.json") if folder else None

    points: list[dict[str, Any]] = []
    if detail:
        descriptors = {
            item.get("key"): item.get("metricsIndex")
            for item in detail.get("metricDescriptors", [])
        }
        for row in detail.get("activityDetailMetrics", []):
            metrics = row.get("metrics", [])

            def get(key: str) -> Any:
                idx = descriptors.get(key)
                if idx is None or not isinstance(idx, int) or idx >= len(metrics):
                    return None
                return metrics[idx]

            distance = get("sumDistance")
            duration = get("sumDuration")
            if distance is None or duration is None:
                continue
            points.append(
                {
                    "dist": distance,
                    "dur": duration,
                    "hr": get("directHeartRate"),
                    "speed": get("directSpeed"),
                    "cad": get("directRunCadence"),
                    "lat": get("directLatitude"),
                    "lon": get("directLongitude"),
                    "alt": get("directElevation"),
                }
            )

    splits: list[dict[str, Any]] = []
    if points:
        prev = points[0]
        next_km = 1000.0
        end_distance = points[-1]["dist"]
        crossings: list[tuple[float, float, Any, Any]] = []
        for point in points[1:]:
            d0, t0 = prev["dist"], prev["dur"]
            d1, t1 = point["dist"], point["dur"]
            while d1 >= next_km and next_km <= end_distance:
                frac = (next_km - d0) / (d1 - d0) if d1 > d0 else 1.0
                crossing_time = t0 + (t1 - t0) * frac
                crossings.append((next_km, crossing_time, point["hr"], point["cad"]))
                next_km += 1000.0
            prev = point

        last_time = points[0]["dur"]
        for km, crossing_time, hr, cad in crossings:
            seconds = crossing_time - last_time
            last_time = crossing_time
            if seconds <= 0:
                continue
            splits.append(
                {
                    "km": int(km // 1000),
                    "sec": seconds,
                    "hr": hr,
                    "cad": (cad * 2 if isinstance(cad, (int, float)) else None),
                }
            )

    zone_seconds = [
        activity.get(f"hrTimeInZone_{i}") or 0 for i in range(1, 6)
    ]
    zone_total = sum(zone_seconds)
    zone_pct = [z / zone_total * 100 for z in zone_seconds] if zone_total else []

    route = [
        (p["lat"], p["lon"])
        for p in points
        if isinstance(p["lat"], (int, float))
        and isinstance(p["lon"], (int, float))
        and p["lat"] != 0
        and p["lon"] != 0
    ]

    distance = activity.get("distance") or 0
    duration = activity.get("duration") or 0
    moving = activity.get("movingDuration") or duration
    km = distance / 1000 if distance else 0

    return {
        "id": activity_id,
        "name": activity.get("activityName") or "跑步",
        "start": activity.get("startTimeLocal") or "",
        "date": (activity.get("startTimeLocal") or "")[:10],
        "time": (activity.get("startTimeLocal") or "")[11:16],
        "km": km,
        "distance": distance,
        "duration": duration,
        "moving": moving,
        "elapsed": activity.get("elapsedDuration") or duration,
        "pace": safe_div(duration, km) if km else None,
        "moving_pace": safe_div(moving, km) if km else None,
        "hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "cadence": activity.get("averageRunningCadenceInStepsPerMinute"),
        "stride": activity.get("avgStrideLength"),
        "gct": activity.get("avgGroundContactTime"),
        "vertical_osc": activity.get("avgVerticalOscillation"),
        "vertical_ratio": activity.get("avgVerticalRatio"),
        "power": activity.get("avgPower"),
        "norm_power": activity.get("normPower"),
        "te": activity.get("aerobicTrainingEffect"),
        "anaerobic_te": activity.get("anaerobicTrainingEffect"),
        "te_label": activity.get("trainingEffectLabel"),
        "load": activity.get("activityTrainingLoad") or 0,
        "calories": activity.get("calories"),
        "vo2max": activity.get("vO2MaxValue"),
        "elevation": activity.get("elevationGain"),
        "steps": activity.get("steps"),
        "bb_delta": activity.get("differenceBodyBattery"),
        "zone_seconds": zone_seconds,
        "zone_pct": zone_pct,
        "fastest_1k": activity.get("fastestSplit_1000"),
        "fastest_5k": activity.get("fastestSplit_5000"),
        "fastest_10k": activity.get("fastestSplit_10000"),
        "fastest_half": activity.get("fastestSplit_21098"),
        "splits": splits,
        "route": route,
        "folder": folder,
    }


def build_day(root: Path, date_str: str) -> dict[str, Any]:
    sleep_raw = load_json(root / "health" / f"{date_str}_sleep.json") or {}
    sleep = sleep_raw.get("data") or {}
    dto = sleep.get("dailySleepDTO") or {}
    hr_raw = load_json(root / "health" / f"{date_str}_heart_rate.json") or {}
    hr = hr_raw.get("data") or {}
    stress_raw = load_json(root / "health" / f"{date_str}_stress.json") or {}
    stress = stress_raw.get("data") or {}
    bb_raw = load_json(root / "health" / f"{date_str}_body_battery.json") or {}
    bb_data = bb_raw.get("data") or []
    bb = bb_data[0] if bb_data else {}
    hrv_raw = load_json(root / "health" / f"{date_str}_hrv.json") or {}
    hrv = hrv_raw.get("data") or {}
    hrv_summary = hrv.get("hrvSummary") or {}
    steps_raw = load_json(root / "health" / f"{date_str}_steps.json") or {}
    steps_data = steps_raw.get("data") or []
    steps_summary = steps_raw.get("summary") or {}

    sleep_total = dto.get("sleepTimeSeconds") or 0
    nap = dto.get("napTimeSeconds") or 0
    deep = dto.get("deepSleepSeconds") or 0
    rem = dto.get("remSleepSeconds") or 0
    awake = dto.get("awakeSleepSeconds") or 0
    light = max(0, sleep_total - deep - rem - awake)

    score_obj = ((dto.get("sleepScores") or {}).get("overall") or {})
    score = score_obj.get("value")
    score_qual = score_obj.get("qualifierKey") or ""

    sleep_need = dto.get("sleepNeed") or {}
    alignment = dto.get("sleepAlignment") or {}

    stress_values = [
        value
        for _, value in stress.get("stressValuesArray") or []
        if isinstance(value, (int, float)) and 0 <= value <= 100
    ]
    zones = {
        "rest": sum(1 for v in stress_values if v <= 25),
        "low": sum(1 for v in stress_values if 26 <= v <= 50),
        "med": sum(1 for v in stress_values if 51 <= v <= 75),
        "high": sum(1 for v in stress_values if v >= 76),
    }
    zone_total = sum(zones.values()) or 1
    stress_zones = {k: v / zone_total * 100 for k, v in zones.items()}

    bb_values = [
        item[2]
        for item in stress.get("bodyBatteryValuesArray") or []
        if len(item) >= 3 and isinstance(item[2], (int, float))
    ]

    step_hours = [0] * 24
    for bucket in steps_data:
        start_gmt = bucket.get("startGMT")
        if not start_gmt:
            continue
        try:
            dt = datetime.fromisoformat(start_gmt.replace("Z", "+00:00")).astimezone(CN)
        except ValueError:
            continue
        value = bucket.get("steps") or 0
        if 0 <= dt.hour < 24:
            step_hours[dt.hour] += value

    def curve(pairs: Iterable[Sequence[Any]], *, index: int = 1) -> list[float | None]:
        values: list[float | None] = [None] * 97
        for item in pairs:
            if len(item) <= index:
                continue
            ts, value = item[0], item[index]
            if not isinstance(ts, (int, float)) or not isinstance(value, (int, float)):
                continue
            if value < 0:
                continue
            dt = datetime.fromtimestamp(ts / 1000, CN)
            if dt.strftime("%Y-%m-%d") != date_str:
                continue
            idx = round((dt.hour * 60 + dt.minute) / 15)
            if 0 <= idx <= 96:
                values[idx] = value
        return values

    hrv_readings = [
        item.get("hrvValue")
        for item in hrv.get("hrvReadings") or []
        if isinstance(item.get("hrvValue"), (int, float))
    ]

    hr_values = [
        value
        for _, value in hr.get("heartRateValues") or []
        if isinstance(value, (int, float)) and value > 0
    ]

    data_end = None
    for ts in (
        [item[0] for item in stress.get("stressValuesArray") or [] if item]
        + [item[0] for item in stress.get("bodyBatteryValuesArray") or [] if item]
        + [item[0] for item in hr.get("heartRateValues") or [] if item]
    ):
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts / 1000, CN)
            if dt.strftime("%Y-%m-%d") == date_str:
                minutes = dt.hour * 60 + dt.minute
                data_end = minutes if data_end is None else max(data_end, minutes)

    return {
        "date": date_str,
        "sleep_total": sleep_total,
        "nap": nap,
        "sleep_all": sleep_total + nap,
        "deep": deep,
        "light": light,
        "rem": rem,
        "awake": awake,
        "score": score,
        "score_qual": score_qual,
        "bed": hhmm_from_garmin_local(dto.get("sleepStartTimestampLocal")),
        "wake": hhmm_from_garmin_local(dto.get("sleepEndTimestampLocal")),
        "bed_min": minutes_from_midnight(dto.get("sleepStartTimestampLocal")),
        "wake_min": minutes_from_midnight(dto.get("sleepEndTimestampLocal")),
        "sleep_hr": dto.get("avgHeartRate"),
        "sleep_stress": dto.get("avgSleepStress"),
        "spo2": dto.get("averageSpO2Value"),
        "spo2_low": dto.get("lowestSpO2Value"),
        "resp": dto.get("averageRespirationValue"),
        "skin": sleep.get("avgSkinTempDeviationC"),
        "restless": sleep.get("restlessMomentsCount"),
        "need_actual": sleep_need.get("actual"),
        "need_baseline": sleep_need.get("baseline"),
        "need_feedback": sleep_need.get("feedback"),
        "need_training": sleep_need.get("trainingFeedback"),
        "alignment": alignment.get("status"),
        "rhr": hr.get("restingHeartRate"),
        "rhr7": hr.get("lastSevenDaysAvgRestingHeartRate"),
        "hr_max": hr.get("maxHeartRate"),
        "hr_min": hr.get("minHeartRate"),
        "hr_values": hr_values,
        "stress_avg": stress.get("avgStressLevel"),
        "stress_max": stress.get("maxStressLevel"),
        "stress_zones": stress_zones,
        "stress_curve": curve(stress.get("stressValuesArray") or []),
        "bb_start": bb_values[0] if bb_values else None,
        "bb_end": bb_values[-1] if bb_values else None,
        "bb_min": min(bb_values) if bb_values else None,
        "bb_max": max(bb_values) if bb_values else None,
        "bb_curve": curve(stress.get("bodyBatteryValuesArray") or [], index=2),
        "charged": bb.get("charged"),
        "drained": bb.get("drained"),
        "hrv_last": hrv_summary.get("lastNightAvg"),
        "hrv_week": hrv_summary.get("weeklyAvg"),
        "hrv_high": hrv_summary.get("lastNight5MinHigh"),
        "hrv_status": hrv_summary.get("status"),
        "hrv_baseline": hrv_summary.get("baseline") or {},
        "hrv_values": hrv_readings,
        "steps": steps_summary.get("steps") or 0,
        "step_hours": step_hours,
        "data_end": data_end,
    }

# ---------- 图表 ----------

C = {
    "ink": "#0f172a",
    "muted": "#64748b",
    "grid": "#e8edf4",
    "blue": "#2563eb",
    "sky": "#60a5fa",
    "lightblue": "#dbeafe",
    "teal": "#0f766e",
    "mint": "#5eead4",
    "amber": "#d97706",
    "orange": "#f97316",
    "red": "#dc2626",
    "rose": "#e11d48",
    "violet": "#7c3aed",
    "slate": "#94a3b8",
}

SLEEP_COLORS = {
    "deep": "#1e3a8a",
    "light": "#60a5fa",
    "rem": "#a78bfa",
    "awake": "#fbbf24",
    "nap": "#14b8a6",
}

STRESS_COLORS = {
    "rest": "#86efac",
    "low": "#93c5fd",
    "med": "#fbbf24",
    "high": "#ef4444",
}

ZONE_COLORS = ["#bfdbfe", "#93c5fd", "#fbbf24", "#fb923c", "#dc2626"]

QUAL_LABEL = {
    "EXCELLENT": "优秀",
    "GOOD": "良好",
    "FAIR": "一般",
    "POOR": "较差",
}

QUAL_COLOR = {
    "EXCELLENT": "#0f766e",
    "GOOD": "#2563eb",
    "FAIR": "#d97706",
    "POOR": "#dc2626",
}


def chart_daily_rhythm(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 320
    plot = Plot(width, height, left=58, right=62, top=38, bottom=54)
    body: list[str] = []
    steps_max = 30000
    sleep_max = 9.0
    step_ticks = [0, 10000, 20000, 30000]
    sleep_ticks = [0, 3, 6, 9]
    body.append(hgrid(plot, 0, steps_max, step_ticks, fmt=lambda v: f"{int(v / 1000)}k"))
    for tick in sleep_ticks:
        y = plot.y(tick, 0, sleep_max)
        body.append(
            svg_text(
                plot.left + plot.iw + 8,
                y + 4,
                f"{tick:g}h",
                anchor="start",
                cls="ax",
            )
        )
    body.append(svg_text(plot.left, 18, "步数", cls="ax-strong"))
    body.append(
        svg_text(plot.left + plot.iw, 18, "睡眠", anchor="end", cls="ax-strong")
    )

    bar_w = min(40, plot.iw / len(days) * 0.52)
    sleep_points: list[tuple[float | None, float | None]] = []
    for i, day in enumerate(days):
        cx = plot.x(i, len(days))
        steps = day["steps"] or 0
        y0 = plot.y(0, 0, steps_max)
        y1 = plot.y(steps, 0, steps_max)
        fill = "#818cf8" if steps >= 22000 else "#c7d2fe"
        body.append(
            svg_rect(
                cx - bar_w / 2,
                y1,
                bar_w,
                y0 - y1,
                fill=fill,
                rx=4,
                title=f'{day["date"]} 步数 {steps:,}',
            )
        )
        body.append(
            svg_text(
                cx,
                y1 + 15,
                f"{steps / 1000:.1f}k",
                anchor="middle",
                cls="val-s",
                extra='fill="#ffffff"' if steps >= 22000 else 'fill="#3730a3"',
            )
        )
        sleep_h = (day["sleep_all"] or 0) / 3600
        sleep_points.append((cx, plot.y(sleep_h, 0, sleep_max)))
        body.append(
            svg_circle(
                cx,
                plot.y(sleep_h, 0, sleep_max),
                5,
                fill="#0f766e",
                title=f'{day["date"]} 睡眠 {fmt_hm(day["sleep_all"])}',
            )
        )
        body.append(
            svg_text(
                cx,
                plot.y(sleep_h, 0, sleep_max) - 10,
                f"{sleep_h:.1f}h",
                anchor="middle",
                cls="val-s",
            )
        )
    body.append(
        f'<path d="{path_d(sleep_points)}" fill="none" stroke="#0f766e" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    body.append(day_xlabels(plot, days))
    body.append(svg_text(plot.left, height - 8, "柱：每日步数　线：睡眠时长（含午睡）", cls="ax2"))
    return svg_doc(width, height, "".join(body), "每日步数与睡眠")


def chart_sleep_stacked(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 320
    plot = Plot(width, height, left=52, right=22, top=42, bottom=54)
    body: list[str] = []
    max_hours = 9.0
    body.append(hgrid(plot, 0, max_hours, [0, 2, 4, 6, 8], fmt=lambda v: f"{v:g}h"))
    body.append(
        svg_line(
            plot.left,
            plot.y(7.5, 0, max_hours),
            plot.left + plot.iw,
            plot.y(7.5, 0, max_hours),
            stroke="#94a3b8",
            width=1.2,
            dash="5 5",
        )
    )
    body.append(
        svg_text(
            plot.left + plot.iw - 2,
            plot.y(7.5, 0, max_hours) - 6,
            "7.5h 参考线",
            anchor="end",
            cls="ax2",
        )
    )
    bar_w = min(46, plot.iw / len(days) * 0.54)
    for i, day in enumerate(days):
        cx = plot.x(i, len(days))
        cursor = 0.0
        stages = [
            ("deep", day["deep"] / 3600, SLEEP_COLORS["deep"]),
            ("light", day["light"] / 3600, SLEEP_COLORS["light"]),
            ("rem", day["rem"] / 3600, SLEEP_COLORS["rem"]),
            ("awake", day["awake"] / 3600, SLEEP_COLORS["awake"]),
        ]
        if day["nap"]:
            stages.append(("nap", day["nap"] / 3600, SLEEP_COLORS["nap"]))
        for key, hours, color in stages:
            if hours <= 0:
                continue
            y_bottom = plot.y(cursor, 0, max_hours)
            y_top = plot.y(cursor + hours, 0, max_hours)
            body.append(
                svg_rect(
                    cx - bar_w / 2,
                    y_top,
                    bar_w,
                    y_bottom - y_top,
                    fill=color,
                    rx=0,
                    title=f"{day['date']} {key} {fmt_hm(hours * 3600)}",
                )
            )
            cursor += hours
        total = day["sleep_all"] / 3600
        body.append(
            svg_text(
                cx,
                plot.y(total, 0, max_hours) - 10,
                f"{day['score'] or '—'}",
                anchor="middle",
                cls="big",
                extra=f'fill="{QUAL_COLOR.get(day["score_qual"], C["ink"])}"',
            )
        )
        if total >= 2.2:
            body.append(
                svg_text(
                    cx,
                    plot.y(total / 2, 0, max_hours),
                    fmt_short(day["sleep_all"]),
                    anchor="middle",
                    cls="val-s",
                    extra='fill="#ffffff" opacity="0.94"',
                )
            )
    body.append(day_xlabels(plot, days))
    body.append(
        svg_text(plot.left, height - 8, "柱顶数字：睡眠评分；柱内数字：总睡眠（含午睡）", cls="ax2")
    )
    return svg_doc(width, height, "".join(body), "睡眠阶段堆叠图")


def chart_sleep_timing(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 300
    left, right, top, bottom = 88, 72, 30, 36
    plot = Plot(width, height, left=left, right=right, top=top, bottom=bottom)
    body: list[str] = []
    row_h = plot.ih / len(days)

    def x_at(minutes: float) -> float:
        if minutes < 1200:
            minutes += 1440
        return plot.left + (minutes - 1200) / 720 * plot.iw

    band_x1 = x_at(22 * 60 + 30)
    band_x2 = x_at(6 * 60 + 30)
    body.append(
        svg_rect(
            band_x1,
            plot.top,
            band_x2 - band_x1,
            plot.ih,
            fill="#ecfdf5",
            rx=6,
        )
    )
    body.append(
        svg_text(
            (band_x1 + band_x2) / 2,
            plot.top - 12,
            "推荐睡眠窗口 22:30–06:30",
            anchor="middle",
            cls="ax2",
        )
    )
    for hour in (20, 22, 0, 2, 4, 6, 8):
        minutes = hour * 60 if hour >= 12 else hour * 60 + 1440
        x = x_at(minutes)
        body.append(
            svg_line(x, plot.top, x, plot.top + plot.ih, stroke="#e8edf4", dash="3 4")
        )
        label = f"{hour:02d}:00"
        body.append(
            svg_text(x, plot.top + plot.ih + 22, label, anchor="middle", cls="ax")
        )
    for i, day in enumerate(days):
        row_top = plot.top + i * row_h
        if i % 2 == 0:
            body.append(
                svg_rect(
                    plot.left,
                    row_top,
                    plot.iw,
                    row_h,
                    fill="#fbfcfe",
                    rx=4,
                )
            )
        bed = day["bed_min"]
        wake = day["wake_min"]
        if bed is None or wake is None:
            continue
        if wake < bed:
            wake += 1440
        x1 = x_at(bed)
        x2 = x_at(wake)
        color = QUAL_COLOR.get(day["score_qual"], C["blue"])
        y = row_top + row_h / 2 - 8
        body.append(
            svg_rect(
                x1,
                y,
                max(2.0, x2 - x1),
                16,
                fill=color,
                rx=8,
                title=f'{day["date"]} {day["bed"]}–{day["wake"]}',
            )
        )
        body.append(
            svg_text(
                plot.left - 10,
                row_top + row_h / 2 + 1,
                f'{day_md(day["date"])} {weekday_cn(day["date"])}',
                anchor="end",
                cls="ax-strong",
            )
        )
        body.append(
            svg_text(
                plot.left - 10,
                row_top + row_h / 2 + 13,
                day["date"][:4],
                anchor="end",
                cls="ax2",
            )
        )
        body.append(
            svg_text(
                plot.left + plot.iw + 8,
                row_top + row_h / 2 + 4,
                fmt_short(day["sleep_all"]),
                anchor="start",
                cls="ax-strong",
            )
        )
    body.append(
        svg_text(plot.left, height - 10, "条形为实际入睡—起床时间；10/23 另有 46 分钟午睡未画入", cls="ax2")
    )
    return svg_doc(width, height, "".join(body), "睡眠时间带")


def chart_rhr(days: Sequence[dict[str, Any]]) -> str:
    width, height = 480, 250
    plot = Plot(width, height, left=44, right=18, top=30, bottom=42)
    body: list[str] = []
    lo, hi = 38, 50
    body.append(hgrid(plot, lo, hi, [40, 44, 48], fmt=lambda v: f"{v:g}"))
    body.append(svg_text(plot.left, 18, "bpm", cls="ax2"))
    points = [
        (plot.x(i, len(days)), plot.y(day["rhr"], lo, hi))
        for i, day in enumerate(days)
        if isinstance(day["rhr"], (int, float))
    ]
    body.append(
        f'<path d="{path_d(points)}" fill="none" stroke="#0f766e" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    avg_points = [
        (plot.x(i, len(days)), plot.y(day["rhr7"], lo, hi))
        for i, day in enumerate(days)
        if isinstance(day["rhr7"], (int, float))
    ]
    body.append(
        f'<path d="{path_d(avg_points)}" fill="none" stroke="#94a3b8" stroke-width="1.4" '
        'stroke-dasharray="4 4"/>'
    )
    for i, day in enumerate(days):
        if not isinstance(day["rhr"], (int, float)):
            continue
        x = plot.x(i, len(days))
        y = plot.y(day["rhr"], lo, hi)
        color = "#dc2626" if day["rhr"] >= 47 else "#0f766e"
        body.append(
            svg_circle(
                x,
                y,
                4.5,
                fill=color,
                title=f'{day["date"]} 静息心率 {day["rhr"]} bpm',
            )
        )
        body.append(svg_text(x, y - 10, f'{day["rhr"]:.0f}', anchor="middle", cls="val-s"))
    body.append(day_xlabels(plot, days, y=plot.top + plot.ih + 20))
    body.append(svg_text(plot.left, height - 6, "实线：每日静息心率　虚线：设备 7 日均值", cls="ax2"))
    return svg_doc(width, height, "".join(body), "静息心率趋势")


def chart_hrv(days: Sequence[dict[str, Any]]) -> str:
    width, height = 480, 250
    plot = Plot(width, height, left=44, right=18, top=30, bottom=42)
    body: list[str] = []
    lo, hi = 95, 120
    body.append(
        svg_rect(
            plot.left,
            plot.y(117, lo, hi),
            plot.iw,
            plot.y(102, lo, hi) - plot.y(117, lo, hi),
            fill="#dcfce7",
            rx=2,
        )
    )
    body.append(
        svg_text(
            plot.left + 6,
            plot.y(117, lo, hi) + 13,
            "平衡区间 102–117",
            cls="ax2",
        )
    )
    body.append(hgrid(plot, lo, hi, [100, 110, 120], fmt=lambda v: f"{v:g}"))
    body.append(svg_text(plot.left, 18, "ms", cls="ax2"))
    points = [
        (plot.x(i, len(days)), plot.y(day["hrv_last"], lo, hi))
        for i, day in enumerate(days)
        if isinstance(day["hrv_last"], (int, float))
    ]
    body.append(
        f'<path d="{path_d(points)}" fill="none" stroke="#7c3aed" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    for i, day in enumerate(days):
        if not isinstance(day["hrv_last"], (int, float)):
            continue
        x = plot.x(i, len(days))
        y = plot.y(day["hrv_last"], lo, hi)
        color = "#dc2626" if day["hrv_last"] < 102 else "#7c3aed"
        body.append(
            svg_circle(
                x,
                y,
                4.5,
                fill=color,
                title=f'{day["date"]} 夜间 HRV {day["hrv_last"]} ms',
            )
        )
        body.append(
            svg_text(x, y - 10, f'{day["hrv_last"]:.0f}', anchor="middle", cls="val-s")
        )
    body.append(day_xlabels(plot, days, y=plot.top + plot.ih + 20))
    body.append(svg_text(plot.left, height - 6, "实线：夜间平均 HRV　绿带：设备平衡区间", cls="ax2"))
    return svg_doc(width, height, "".join(body), "HRV 趋势")


def chart_body_battery(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 290
    plot = Plot(width, height, left=52, right=20, top=32, bottom=54)
    body: list[str] = []
    body.append(hgrid(plot, 0, 100, [0, 20, 40, 60, 80, 100], fmt=lambda v: f"{v:g}"))
    body.append(
        svg_line(
            plot.left,
            plot.y(20, 0, 100),
            plot.left + plot.iw,
            plot.y(20, 0, 100),
            stroke="#fca5a5",
            dash="5 5",
        )
    )
    body.append(
        svg_text(
            plot.left + plot.iw - 2,
            plot.y(20, 0, 100) - 6,
            "低电量参考 20",
            anchor="end",
            cls="ax2",
        )
    )
    bar_w = min(28, plot.iw / len(days) * 0.2)
    for i, day in enumerate(days):
        cx = plot.x(i, len(days))
        start = day["bb_start"]
        end = day["bb_end"]
        if isinstance(start, (int, float)):
            y0 = plot.y(0, 0, 100)
            y1 = plot.y(start, 0, 100)
            body.append(
                svg_rect(
                    cx - bar_w - 2,
                    y1,
                    bar_w,
                    y0 - y1,
                    fill="#99f6e4",
                    rx=3,
                    title=f'{day["date"]} 晨起电量 {start}',
                )
            )
        if isinstance(end, (int, float)):
            y0 = plot.y(0, 0, 100)
            y1 = plot.y(end, 0, 100)
            body.append(
                svg_rect(
                    cx + 2,
                    y1,
                    bar_w,
                    y0 - y1,
                    fill="#0f766e",
                    rx=3,
                    title=f'{day["date"]} 日终电量 {end}',
                )
            )
            body.append(
                svg_text(cx + 2 + bar_w / 2, y1 - 6, f"{end}", anchor="middle", cls="val-s")
            )
        if isinstance(day["bb_min"], (int, float)):
            body.append(
                svg_circle(
                    cx,
                    plot.y(day["bb_min"], 0, 100),
                    3.8,
                    fill="#dc2626",
                    title=f'{day["date"]} 最低电量 {day["bb_min"]}',
                )
            )
    body.append(day_xlabels(plot, days))
    body.append(
        svg_text(plot.left, height - 8, "浅色：晨起电量　深色：日终电量　红点：当日最低", cls="ax2")
    )
    return svg_doc(width, height, "".join(body), "身体电量")


def chart_stress(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 290
    plot = Plot(width, height, left=52, right=20, top=36, bottom=54)
    body: list[str] = []
    body.append(hgrid(plot, 0, 100, [0, 25, 50, 75, 100], fmt=lambda v: f"{v:g}%"))
    bar_w = min(48, plot.iw / len(days) * 0.52)
    for i, day in enumerate(days):
        cx = plot.x(i, len(days))
        cursor = 0.0
        for key in ("rest", "low", "med", "high"):
            value = day["stress_zones"].get(key, 0)
            if value <= 0:
                continue
            y_bottom = plot.y(cursor, 0, 100)
            y_top = plot.y(cursor + value, 0, 100)
            body.append(
                svg_rect(
                    cx - bar_w / 2,
                    y_top,
                    bar_w,
                    y_bottom - y_top,
                    fill=STRESS_COLORS[key],
                    rx=0,
                    title=f"{day['date']} {key} {value:.0f}%",
                )
            )
            cursor += value
        body.append(
            svg_text(
                cx,
                plot.y(100, 0, 100) - 10,
                f'{day["stress_avg"] or "—"}',
                anchor="middle",
                cls="big",
            )
        )
        body.append(
            svg_text(
                cx,
                plot.y(100, 0, 100) - 22,
                f'最高 {day["stress_max"] or "—"}',
                anchor="middle",
                cls="ax2",
            )
        )
    body.append(day_xlabels(plot, days))
    body.append(
        svg_text(plot.left, height - 8, "柱顶：日均压力 / 当日最高；柱内为压力区间占比", cls="ax2")
    )
    return svg_doc(width, height, "".join(body), "每日压力构成")


def chart_load(activities: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 310
    plot = Plot(width, height, left=56, right=20, top=38, bottom=62)
    body: list[str] = []
    max_load = 700
    body.append(hgrid(plot, 0, max_load, [0, 200, 400, 600], fmt=lambda v: f"{int(v)}"))
    body.append(svg_text(plot.left, 20, "训练负荷", cls="ax-strong"))
    n = len(activities)
    bar_w = min(52, plot.iw / max(1, n) * 0.56)
    avg_load = sum(a["load"] for a in activities) / n if n else 0
    body.append(
        svg_line(
            plot.left,
            plot.y(avg_load, 0, max_load),
            plot.left + plot.iw,
            plot.y(avg_load, 0, max_load),
            stroke="#94a3b8",
            dash="4 4",
        )
    )
    body.append(
        svg_text(
            plot.left + plot.iw - 2,
            plot.y(avg_load, 0, max_load) - 5,
            f"课均 {avg_load:.0f}",
            anchor="end",
            cls="ax2",
        )
    )
    for i, act in enumerate(activities):
        cx = plot.x(i, n)
        load = act["load"] or 0
        y0 = plot.y(0, 0, max_load)
        y1 = plot.y(load, 0, max_load)
        if load >= 300:
            fill = "#dc2626"
        elif load >= 100:
            fill = "#f97316"
        elif load > 0:
            fill = "#3b82f6"
        else:
            fill = "#cbd5e1"
        body.append(
            svg_rect(
                cx - bar_w / 2,
                y1,
                bar_w,
                y0 - y1,
                fill=fill,
                rx=4,
                title=f'{act["date"]} {act["time"]} {act["name"]} 负荷 {load:.0f}',
            )
        )
        body.append(
            svg_text(cx, y1 - 6, f"{load:.0f}", anchor="middle", cls="val-s")
        )
        body.append(
            svg_text(cx, y0 + 17, day_md(act["date"]), anchor="middle", cls="ax-strong")
        )
        body.append(
            svg_text(cx, y0 + 31, act["time"], anchor="middle", cls="ax2")
        )
        if i > 0 and act["date"] != activities[i - 1]["date"]:
            boundary = (plot.x(i - 1, n) + cx) / 2
            body.append(
                svg_line(
                    boundary,
                    plot.top,
                    boundary,
                    plot.top + plot.ih,
                    stroke="#e2e8f0",
                    dash="3 4",
                )
            )
    body.append(
        svg_text(plot.left, height - 6, "柱高为单次活动训练负荷；10/25 半马测试 635，占本周 56%", cls="ax2")
    )
    return svg_doc(width, height, "".join(body), "单次训练负荷")


def chart_zones(activities: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 430
    left, right, top, bottom = 196, 54, 28, 34
    row_h = (height - top - bottom) / len(activities)
    body: list[str] = []
    x0 = left
    x1 = width - right
    body.append(svg_text(x0, 16, "心率区间占比", cls="ax-strong"))
    for pct in (0, 25, 50, 75, 100):
        x = x0 + (x1 - x0) * pct / 100
        body.append(svg_line(x, top - 4, x, height - bottom, stroke="#f1f5f9"))
        body.append(svg_text(x, height - 12, f"{pct}%", anchor="middle", cls="ax2"))
    for i, act in enumerate(activities):
        y = top + i * row_h
        name = act["name"]
        if len(name) > 20:
            name = name[:19] + "…"
        body.append(
            svg_text(
                left - 12,
                y + row_h / 2 - 2,
                f'{day_md(act["date"])} {act["time"]}',
                anchor="end",
                cls="ax-strong",
            )
        )
        body.append(
            svg_text(left - 12, y + row_h / 2 + 12, name, anchor="end", cls="ax2")
        )
        cursor = 0.0
        bar_y = y + 7
        bar_h = row_h - 16
        pct_values = act["zone_pct"]
        if not pct_values:
            body.append(svg_rect(x0, bar_y, x1 - x0, bar_h, fill="#f1f5f9", rx=4))
            continue
        for zone_idx, pct in enumerate(pct_values):
            if pct <= 0:
                continue
            seg_x = x0 + (x1 - x0) * cursor / 100
            seg_w = (x1 - x0) * pct / 100
            body.append(
                svg_rect(
                    seg_x,
                    bar_y,
                    seg_w,
                    bar_h,
                    fill=ZONE_COLORS[zone_idx],
                    rx=0,
                    title=f'{act["date"]} {act["name"]} Z{zone_idx + 1} {pct:.0f}%',
                )
            )
            if pct >= 9:
                body.append(
                    svg_text(
                        seg_x + seg_w / 2,
                        bar_y + bar_h / 2 + 4,
                        f"{pct:.0f}%",
                        anchor="middle",
                        cls="val-s",
                        extra='fill="#ffffff"' if zone_idx >= 3 else 'fill="#0f172a"',
                    )
                )
            cursor += pct
        z45 = sum(pct_values[3:])
        body.append(
            svg_text(
                x1 + 8,
                bar_y + bar_h / 2 + 4,
                f"{z45:.0f}%",
                anchor="start",
                cls="val-s",
            )
        )
    return svg_doc(width, height, "".join(body), "活动心率区间分布")


def chart_splits(activity: dict[str, Any]) -> str:
    width, height = 1000, 270
    plot = Plot(width, height, left=56, right=58, top=30, bottom=46)
    body: list[str] = []
    splits = activity["splits"]
    if not splits:
        body.append(svg_text(width / 2, height / 2, "无分段数据", anchor="middle", cls="ax"))
        return svg_doc(width, height, "".join(body), "分段配速")
    paces = [s["sec"] for s in splits]
    lo = max(120.0, min(paces) - 12)
    hi = max(paces) + 12
    if hi - lo < 30:
        pad = (30 - (hi - lo)) / 2
        lo -= pad
        hi += pad

    def y_pace(pace: float) -> float:
        return plot.top + (pace - lo) / (hi - lo) * plot.ih

    ticks = [lo + (hi - lo) * i / 4 for i in range(5)]
    for tick in ticks:
        y = y_pace(tick)
        body.append(svg_line(plot.left, y, plot.left + plot.iw, y, stroke="#e8edf4"))
        body.append(svg_text(plot.left - 8, y + 4, fmt_pace(tick), anchor="end", cls="ax"))
    body.append(hgrid(plot, 100, 200, [120, 150, 180], right=True, fmt=lambda v: f"{int(v)}"))
    body.append(svg_text(plot.left + plot.iw + 8, 18, "HR", cls="ax2"))
    body.append(svg_text(plot.left - 8, 18, "配速", anchor="end", cls="ax2"))

    base_y = plot.top + plot.ih
    bar_w = min(44, plot.iw / len(splits) * 0.62)
    hr_points: list[tuple[float | None, float | None]] = []
    for i, split in enumerate(splits):
        cx = plot.x(i, len(splits))
        y = y_pace(split["sec"])
        fill = "#93c5fd" if split["sec"] <= sum(paces) / len(paces) else "#bfdbfe"
        body.append(
            svg_rect(
                cx - bar_w / 2,
                y,
                bar_w,
                base_y - y,
                fill=fill,
                rx=3,
                title=f'{activity["date"]} 第 {split["km"]} km · {fmt_pace(split["sec"])} /km · HR {split["hr"] or "—"}',
            )
        )
        if isinstance(split["hr"], (int, float)):
            hr_points.append((cx, plot.y(split["hr"], 100, 200)))
        if len(splits) <= 12 or split["km"] % 2 == 0:
            body.append(
                svg_text(
                    cx,
                    base_y + 18,
                    str(split["km"]),
                    anchor="middle",
                    cls="ax-strong" if len(splits) <= 12 else "ax",
                )
            )
    avg_pace = sum(paces) / len(paces)
    body.append(
        svg_line(
            plot.left,
            y_pace(avg_pace),
            plot.left + plot.iw,
            y_pace(avg_pace),
            stroke="#64748b",
            dash="4 4",
        )
    )
    body.append(
        svg_text(
            plot.left + 4,
            y_pace(avg_pace) - 6,
            f"均 {fmt_pace(avg_pace)}",
            cls="ax2",
        )
    )
    if len(hr_points) >= 2:
        body.append(
            f'<path d="{path_d(hr_points)}" fill="none" stroke="#e11d48" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for x, y in hr_points:
        body.append(svg_circle(x, y, 2.8, fill="#e11d48", sw=1))
    body.append(svg_text(width / 2, height - 10, "公里", anchor="middle", cls="ax2"))
    return svg_doc(width, height, "".join(body), "分段配速与心率")


def step_heat_color(value: int) -> str:
    if value <= 0:
        return "#f1f5f9"
    t = min(1.0, math.sqrt(value / 2400))
    return lerp_color("#dbeafe", "#0f766e", t)


def chart_steps_heatmap(days: Sequence[dict[str, Any]]) -> str:
    width, height = 1000, 330
    left, right, top, bottom = 82, 76, 34, 30
    cell_w = (width - left - right) / 24
    cell_h = (height - top - bottom) / len(days)
    body: list[str] = []
    body.append(svg_text(left, 18, "每小时的步数强度", cls="ax-strong"))
    for hour in range(24):
        if hour % 2 == 0:
            body.append(
                svg_text(
                    left + hour * cell_w + cell_w / 2,
                    top - 8,
                    f"{hour:02d}",
                    anchor="middle",
                    cls="ax2",
                )
            )
    for row, day in enumerate(days):
        y = top + row * cell_h
        body.append(
            svg_text(
                left - 10,
                y + cell_h / 2 - 1,
                f'{day_md(day["date"])} {weekday_cn(day["date"])}',
                anchor="end",
                cls="ax-strong",
            )
        )
        body.append(
            svg_text(
                left - 10,
                y + cell_h / 2 + 12,
                f'{day["steps"]:,}',
                anchor="end",
                cls="ax2",
            )
        )
        for hour, value in enumerate(day["step_hours"]):
            x = left + hour * cell_w
            fill = step_heat_color(value)
            body.append(
                svg_rect(
                    x + 1,
                    y + 1,
                    cell_w - 2,
                    cell_h - 2,
                    fill=fill,
                    rx=2,
                    title=f'{day["date"]} {hour:02d}:00–{hour + 1:02d}:00 · {value:,} 步',
                )
            )
            if value >= 300 and cell_w >= 28:
                text_color = "#ffffff" if value >= 1200 else "#0f172a"
                body.append(
                    svg_text(
                        x + cell_w / 2,
                        y + cell_h / 2 + 4,
                        f"{value:,}",
                        anchor="middle",
                        cls="heat-label",
                        extra=f'fill="{text_color}"',
                    )
                )
        body.append(
            svg_text(
                width - right + 8,
                y + cell_h / 2 + 4,
                f'{day["steps"] / 1000:.1f}k',
                anchor="start",
                cls="val-s",
            )
        )
    for hour in range(25):
        x = left + hour * cell_w
        body.append(svg_line(x, top, x, top + cell_h * len(days), stroke="#ffffff", width=1))
    return svg_doc(width, height, "".join(body), "每日小时步数热力图")


def chart_day_curve(day: dict[str, Any]) -> str:
    width, height = 330, 126
    left, right, top, bottom = 8, 8, 8, 18
    plot = Plot(width, height, left=left, right=right, top=top, bottom=bottom)
    body: list[str] = []
    for hour in (6, 12, 18):
        x = plot.left + plot.iw * hour / 24
        body.append(svg_line(x, plot.top, x, plot.top + plot.ih, stroke="#eef2f7"))
    for level in (25, 50, 75):
        y = plot.y(level, 0, 100)
        body.append(svg_line(plot.left, y, plot.left + plot.iw, y, stroke="#f4f6fa"))
    bb_points = [
        (
            plot.left + plot.iw * i / 96,
            plot.y(v, 0, 100) if isinstance(v, (int, float)) else None,
        )
        for i, v in enumerate(day["bb_curve"])
    ]
    body.append(
        f'<path d="{area_d(bb_points, plot.top + plot.ih)}" fill="#14b8a6" opacity="0.14"/>'
    )
    body.append(
        f'<path d="{path_d(bb_points)}" fill="none" stroke="#0f766e" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    stress_points = [
        (
            plot.left + plot.iw * i / 96,
            plot.y(v, 0, 100) if isinstance(v, (int, float)) else None,
        )
        for i, v in enumerate(day["stress_curve"])
    ]
    body.append(
        f'<path d="{path_d(stress_points)}" fill="none" stroke="#f97316" stroke-width="1.3" '
        'opacity="0.9" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    for hour, label in ((0, "00"), (6, "06"), (12, "12"), (18, "18"), (24, "24")):
        x = plot.left + plot.iw * hour / 24
        body.append(
            svg_text(x, height - 5, label, anchor="middle", cls="ax2")
        )
    return svg_doc(width, height, "".join(body), "身体电量与压力日曲线")


def simplify_route(route: Sequence[tuple[float, float]], max_points: int = 90) -> list[tuple[float, float]]:
    if len(route) <= max_points:
        return list(route)
    step = len(route) / max_points
    sampled = [route[min(len(route) - 1, int(i * step))] for i in range(max_points)]
    if sampled[-1] != route[-1]:
        sampled.append(route[-1])
    return sampled


def route_svg(activity: dict[str, Any]) -> str:
    width, height = 300, 168
    route = simplify_route(activity["route"])
    if len(route) < 2:
        return (
            f'<svg class="route-map" viewBox="0 0 {width} {height}" role="img" '
            'aria-label="无轨迹数据"><rect width="300" height="168" rx="12" fill="#f8fafc"/>'
            '<text x="150" y="88" text-anchor="middle" class="ax">无轨迹数据</text></svg>'
        )
    lats = [p[0] for p in route]
    lons = [p[1] for p in route]
    mean_lat = sum(lats) / len(lats)
    xs = [(lon - min(lons)) * math.cos(math.radians(mean_lat)) for lon in lons]
    ys = [lat - min(lats) for lat in lats]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    pad = 20
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y) if span_x and span_y else 1
    offset_x = (width - span_x * scale) / 2
    offset_y = (height - span_y * scale) / 2
    coords = [
        (offset_x + (x - min(xs)) * scale, height - offset_y - (y - min(ys)) * scale)
        for x, y in zip(xs, ys)
    ]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    sx, sy = coords[0]
    ex, ey = coords[-1]
    body = [
        f'<rect width="{width}" height="{height}" rx="12" fill="#f8fafc"/>',
        f'<polyline points="{points}" fill="none" stroke="#cbd5e1" stroke-width="7" '
        'stroke-linecap="round" stroke-linejoin="round"/>',
        f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="3.2" '
        'stroke-linecap="round" stroke-linejoin="round"/>',
        svg_circle(sx, sy, 5.2, fill="#0f766e", title="起点"),
        svg_circle(ex, ey, 5.2, fill="#e11d48", title="终点"),
        svg_text(width - 10, height - 9, "轨迹示意", anchor="end", cls="route-note"),
    ]
    return (
        f'<svg class="route-map" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{esc(activity["date"] + " 路线轨迹")}">'
        + "".join(body)
        + "</svg>"
    )


def route_card(activity: dict[str, Any]) -> str:
    return f"""
    <article class="route-card">
      <div class="route-head">
        <div>
          <div class="route-date">{esc(day_md(activity['date']))} {esc(weekday_cn(activity['date']))} · {esc(activity['time'])}</div>
          <div class="route-name">{esc(activity['name'])}</div>
        </div>
        <div class="route-dist">{activity['km']:.2f}<span>km</span></div>
      </div>
      {route_svg(activity)}
      <div class="route-stats">
        <span>{fmt_pace(activity['pace'])} /km</span>
        <span>HR {num(activity['hr'])}</span>
        <span>负荷 {num(activity['load'])}</span>
      </div>
    </article>
    """


# ---------- 汇总上下文 ----------


def build_context(root: Path) -> dict[str, Any]:
    manifest = load_json(root / "manifest.json") or {}
    raw_activities = load_json(root / "activities" / "activities.json") or []
    activities = [
        activity
        for activity in (build_activity(root, item) for item in raw_activities)
        if activity is not None
    ]
    activities.sort(key=lambda item: item["start"])

    date_strs = sorted(
        path.name.split("_")[0] for path in (root / "health").glob("*_sleep.json")
    )
    days = [build_day(root, date_str) for date_str in date_strs]
    days = [day for day in days if day["sleep_total"] or day["steps"]]

    by_date: dict[str, list[dict[str, Any]]] = {}
    for activity in activities:
        by_date.setdefault(activity["date"], []).append(activity)

    total_km = sum(a["km"] for a in activities)
    total_duration = sum(a["duration"] for a in activities)
    total_moving = sum(a["moving"] for a in activities)
    total_load = sum(a["load"] for a in activities)
    total_calories = sum(a["calories"] or 0 for a in activities)
    total_run_steps = sum(a["steps"] or 0 for a in activities)
    avg_pace = safe_div(total_duration, total_km)

    hard_dates = [d for d in ("2026-10-25", "2026-10-27", "2026-10-28") if d in by_date]
    hard_km = sum(a["km"] for d in hard_dates for a in by_date[d])
    hard_share = hard_km / total_km * 100 if total_km else 0
    back_to_back = sum(
        a["km"] for d in ("2026-10-27", "2026-10-28") for a in by_date.get(d, [])
    )

    race_act = next(
        (a for a in activities if a["date"] == "2026-10-25" and a["km"] > 15), None
    )
    long_act = next(
        (a for a in activities if a["date"] == "2026-10-28" and a["km"] > 15), None
    )
    threshold_act = next(
        (
            a
            for a in activities
            if a["date"] == "2026-10-27" and a["km"] > 10
        ),
        None,
    )

    sleep_total = sum(day["sleep_all"] for day in days)
    night_total = sum(day["sleep_total"] for day in days)
    sleep_avg = sleep_total / len(days) if days else 0
    night_avg = night_total / len(days) if days else 0
    sleep_debt = len(days) * 7.5 * 3600 - sleep_total
    scores = [d["score"] for d in days if isinstance(d["score"], (int, float))]
    avg_score = sum(scores) / len(scores) if scores else None
    best_sleep = max(days, key=lambda d: d["score"] or -1) if days else None
    worst_sleep = min(days, key=lambda d: d["score"] or 999) if days else None
    nights_under_6 = [d for d in days if d["sleep_total"] and d["sleep_total"] < 6 * 3600]
    deep_avg = sum(d["deep"] for d in days) / len(days) if days else 0
    rem_avg = sum(d["rem"] for d in days) / len(days) if days else 0
    awake_total = sum(d["awake"] for d in days)

    rhr_values = [d["rhr"] for d in days if isinstance(d["rhr"], (int, float))]
    rhr_avg = sum(rhr_values) / len(rhr_values) if rhr_values else None
    rhr_max = max(rhr_values) if rhr_values else None
    hrv_values = [d["hrv_last"] for d in days if isinstance(d["hrv_last"], (int, float))]
    hrv_avg = sum(hrv_values) / len(hrv_values) if hrv_values else None
    hrv_min = min(hrv_values) if hrv_values else None
    hrv_max = max(hrv_values) if hrv_values else None

    bb_mornings = [d["bb_start"] for d in days if isinstance(d["bb_start"], (int, float))]
    bb_morning_avg = sum(bb_mornings) / len(bb_mornings) if bb_mornings else None
    low_mornings = [v for v in bb_mornings if v <= 22]
    stress_avg_week = safe_mean([d["stress_avg"] for d in days])

    steps_total = sum(d["steps"] for d in days)
    complete_days = [d for d in days if (d["data_end"] or 0) >= 20 * 60]
    steps_complete_avg = (
        sum(d["steps"] for d in complete_days) / len(complete_days)
        if complete_days
        else None
    )

    corr_defs = [
        ("sleep", "睡眠时长", [d["sleep_all"] / 3600 for d in days]),
        ("score", "睡眠评分", [d["score"] for d in days]),
        ("rhr", "静息心率", [d["rhr"] for d in days]),
        ("hrv", "夜间 HRV", [d["hrv_last"] for d in days]),
        ("steps", "步数", [d["steps"] for d in days]),
        ("stress", "平均压力", [d["stress_avg"] for d in days]),
        ("bb", "日终电量", [d["bb_end"] for d in days]),
    ]
    corr_matrix = {
        key: {
            other: pearson(values, other_values)
            for other, _, other_values in corr_defs
        }
        for key, _, values in corr_defs
    }

    finished = manifest.get("finished_at")
    export_finished = "—"
    if finished:
        try:
            export_finished = (
                datetime.fromisoformat(finished).astimezone(CN).strftime("%Y-%m-%d %H:%M")
            )
        except ValueError:
            export_finished = finished

    partial_days = [d for d in days if (d["data_end"] or 1440) < 20 * 60]

    return {
        "root": root,
        "manifest": manifest,
        "account": manifest.get("account") or {},
        "activities": activities,
        "days": days,
        "by_date": by_date,
        "total_km": total_km,
        "total_duration": total_duration,
        "total_moving": total_moving,
        "total_load": total_load,
        "total_calories": total_calories,
        "total_run_steps": total_run_steps,
        "avg_pace": avg_pace,
        "hard_dates": hard_dates,
        "hard_km": hard_km,
        "hard_share": hard_share,
        "back_to_back": back_to_back,
        "race_act": race_act,
        "long_act": long_act,
        "threshold_act": threshold_act,
        "sleep_total": sleep_total,
        "night_total": night_total,
        "sleep_avg": sleep_avg,
        "night_avg": night_avg,
        "sleep_debt": sleep_debt,
        "avg_score": avg_score,
        "best_sleep": best_sleep,
        "worst_sleep": worst_sleep,
        "nights_under_6": nights_under_6,
        "deep_avg": deep_avg,
        "rem_avg": rem_avg,
        "awake_total": awake_total,
        "rhr_values": rhr_values,
        "rhr_avg": rhr_avg,
        "rhr_max": rhr_max,
        "hrv_values": hrv_values,
        "hrv_avg": hrv_avg,
        "hrv_min": hrv_min,
        "hrv_max": hrv_max,
        "bb_mornings": bb_mornings,
        "bb_morning_avg": bb_morning_avg,
        "low_mornings": low_mornings,
        "stress_avg_week": stress_avg_week,
        "steps_total": steps_total,
        "steps_complete_avg": steps_complete_avg,
        "corr_defs": corr_defs,
        "corr_matrix": corr_matrix,
        "export_finished": export_finished,
        "partial_days": partial_days,
        "generated_at": datetime.now(CN).strftime("%Y-%m-%d %H:%M"),
    }


# ---------- 样式 ----------

CSS = r"""
:root{
  --bg:#f3f5f8;
  --paper:#ffffff;
  --ink:#0f172a;
  --muted:#64748b;
  --soft:#94a3b8;
  --line:#e4e9f1;
  --navy:#0b1220;
  --teal:#0f766e;
  --blue:#2563eb;
  --rose:#e11d48;
  --amber:#d97706;
  --radius:18px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  background:
    radial-gradient(1200px 500px at 15% -10%, rgba(37,99,235,.07), transparent 60%),
    radial-gradient(900px 400px at 90% 0%, rgba(15,118,110,.06), transparent 55%),
    var(--bg);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:15px;
  line-height:1.68;
  -webkit-font-smoothing:antialiased;
  font-variant-numeric:tabular-nums;
}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
.hero{
  position:relative;
  overflow:hidden;
  color:#fff;
  background:
    radial-gradient(900px 420px at 85% 0%, rgba(225,29,72,.25), transparent 60%),
    radial-gradient(700px 420px at 0% 100%, rgba(20,184,166,.16), transparent 60%),
    linear-gradient(135deg,#0b1220 0%,#111c33 60%,#0b1220 100%);
  padding:58px 0 34px;
}
.hero:after{
  content:"";
  position:absolute;
  right:-120px;top:-180px;
  width:520px;height:520px;
  border:1px solid rgba(255,255,255,.08);
  border-radius:50%;
  box-shadow:0 0 0 70px rgba(255,255,255,.025),0 0 0 140px rgba(255,255,255,.018);
  pointer-events:none;
}
.eyebrow{
  display:flex;align-items:center;gap:10px;
  font-size:11px;letter-spacing:.18em;font-weight:700;
  color:#94a3b8;text-transform:uppercase;
}
.eyebrow:before{content:"";width:30px;height:1px;background:#e11d48;display:inline-block}
.hero h1{
  margin:14px 0 10px;
  font-size:clamp(30px,4.2vw,50px);
  line-height:1.12;
  letter-spacing:-.02em;
  font-weight:750;
}
.hero h1 em{font-style:normal;color:#fda4af}
.hero .sub{
  max-width:780px;
  color:#aebbd0;
  font-size:16px;
  margin:0;
}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}
.chip{
  display:inline-flex;align-items:center;gap:7px;
  padding:6px 11px;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.055);
  border-radius:999px;
  font-size:12px;color:#cbd5e1;
}
.chip b{color:#fff;font-weight:650}
.kpis{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:10px;
  margin-top:30px;
}
.kpi{
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.1);
  border-radius:14px;
  padding:13px 14px 12px;
  backdrop-filter:blur(8px);
}
.kpi .k{font-size:11px;color:#94a3b8;letter-spacing:.04em}
.kpi .v{font-size:23px;font-weight:720;line-height:1.25;margin-top:3px;letter-spacing:-.02em}
.kpi .v small{font-size:11px;color:#94a3b8;font-weight:500;margin-left:3px;letter-spacing:0}
.kpi .n{font-size:10.5px;color:#7f8da3;margin-top:2px}
nav{
  position:sticky;top:0;z-index:40;
  background:rgba(243,245,248,.9);
  backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line);
}
nav .wrap{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
nav .wrap::-webkit-scrollbar{display:none}
nav a{
  display:block;white-space:nowrap;
  padding:12px 12px;
  font-size:12.5px;color:#64748b;text-decoration:none;
  border-bottom:2px solid transparent;
}
nav a:hover{color:var(--ink);border-color:var(--ink)}
main{padding:30px 0 80px}
section{margin:38px 0;scroll-margin-top:62px}
.sec-head{display:flex;align-items:flex-start;gap:14px;margin-bottom:18px}
.sec-num{
  flex:0 0 auto;
  font-size:11px;font-weight:750;letter-spacing:.14em;
  color:var(--rose);
  padding-top:8px;
}
h2{
  margin:0;
  font-size:clamp(23px,2.6vw,30px);
  line-height:1.25;letter-spacing:-.015em;
}
.lede{color:var(--muted);font-size:14px;margin:6px 0 0;max-width:860px}
.card{
  background:var(--paper);
  border:1px solid var(--line);
  border-radius:var(--radius);
  padding:22px;
  box-shadow:0 1px 2px rgba(15,23,42,.03),0 10px 30px rgba(15,23,42,.025);
}
.card-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:8px}
.card-title{font-size:14px;font-weight:700;letter-spacing:.01em}
.card-note{font-size:11.5px;color:var(--soft)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.chart{width:100%;height:auto;display:block;overflow:visible}
.chart text{font-family:inherit}
.ax{fill:#64748b;font-size:11px}
.ax2{fill:#94a3b8;font-size:10px}
.ax-strong{fill:#334155;font-size:11.5px;font-weight:650}
.val{fill:#0f172a;font-size:11px;font-weight:650}
.val-s{fill:#475569;font-size:10px;font-weight:650}
.big{fill:#0f172a;font-size:13px;font-weight:750}
.heat-label{font-size:8.5px;font-weight:600}
.route-note{fill:#94a3b8;font-size:9px}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;font-size:11.5px;color:#64748b}
.legend span{display:inline-flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:3px;display:inline-block}
.verdict{
  margin-top:16px;
  display:grid;
  grid-template-columns:1.25fr 1fr;
  gap:0;
  background:#0f172a;
  color:#e2e8f0;
  border-radius:16px;
  overflow:hidden;
  border:1px solid #1e293b;
}
.verdict-main{padding:20px 22px}
.verdict-kicker{font-size:10px;letter-spacing:.16em;color:#fda4af;font-weight:750}
.verdict-title{font-size:19px;line-height:1.45;font-weight:650;margin-top:6px}
.verdict-title b{color:#fff}
.verdict-side{
  background:rgba(255,255,255,.045);
  border-left:1px solid rgba(255,255,255,.08);
  padding:18px 20px;
  display:flex;flex-direction:column;justify-content:center;gap:8px;
}
.verdict-side div{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#94a3b8}
.verdict-side b{color:#fff;font-weight:650}
.week{display:grid;grid-template-columns:repeat(7,1fr);gap:7px;margin-top:4px}
.day-card{
  position:relative;
  background:#fff;border:1px solid var(--line);border-radius:13px;
  padding:12px 11px 11px;
  min-height:148px;
  display:flex;flex-direction:column;
  overflow:hidden;
}
.day-card:before{
  content:"";position:absolute;left:0;right:0;top:0;height:4px;background:#cbd5e1;
}
.day-card.high:before{background:#dc2626}
.day-card.mid:before{background:#f97316}
.day-card.low:before{background:#3b82f6}
.day-card.rest:before{background:#cbd5e1}
.dc-date{font-size:11px;color:#64748b;display:flex;justify-content:space-between;gap:4px}
.dc-date b{color:#0f172a;font-weight:700}
.dc-main{font-size:19px;font-weight:750;line-height:1.3;margin-top:8px;letter-spacing:-.02em}
.dc-main small{font-size:10px;color:#64748b;font-weight:500;margin-left:1px}
.dc-sub{font-size:10.5px;color:#64748b;line-height:1.5;min-height:30px}
.dc-meta{margin-top:auto;padding-top:7px;border-top:1px solid #f1f5f9;font-size:10px;color:#64748b;display:grid;gap:3px}
.dc-meta span{display:flex;justify-content:space-between;gap:5px}
.dc-meta b{color:#334155;font-weight:650}
.pill{
  display:inline-flex;align-items:center;gap:5px;
  padding:2px 8px;border-radius:999px;
  font-size:10.5px;font-weight:650;line-height:1.7;
}
.pill.good{background:#ecfdf5;color:#0f766e}
.pill.warn{background:#fffbeb;color:#b45309}
.pill.bad{background:#fff1f2;color:#be123c}
.pill.info{background:#eff6ff;color:#1d4ed8}
.pill.neutral{background:#f1f5f9;color:#475569}
.callout{
  border-left:3px solid var(--rose);
  background:#fff7f8;
  border-radius:0 12px 12px 0;
  padding:13px 16px;
  color:#3f1f2a;
  font-size:13px;
}
.callout.good{border-color:#0f766e;background:#f0fdfa;color:#134e4a}
.callout.warn{border-color:#d97706;background:#fffbeb;color:#78350f}
.callout b{color:#0f172a}
.stat-row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px}
.stat{
  background:#f8fafc;border:1px solid #eef2f7;border-radius:10px;
  padding:7px 11px;font-size:11px;color:#64748b;
}
.stat b{display:block;color:#0f172a;font-size:15px;line-height:1.4;font-weight:700}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:#fff}
table{width:100%;border-collapse:collapse;font-size:12.5px;min-width:820px}
th{
  text-align:left;color:#64748b;font-weight:650;font-size:10.5px;
  letter-spacing:.03em;background:#f8fafc;
  padding:10px 10px;border-bottom:1px solid var(--line);white-space:nowrap;
}
td{padding:9px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle;white-space:nowrap}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:#fbfdff}
td.num{text-align:right}
td.wrap{white-space:normal;min-width:160px}
.t-main{font-weight:650;color:#0f172a}
.t-sub{font-size:10.5px;color:#94a3b8}
.te{font-weight:700}
.te.high{color:#dc2626}
.te.mid{color:#d97706}
.te.low{color:#2563eb}
.mini-zone{display:flex;height:5px;width:88px;border-radius:999px;overflow:hidden;background:#f1f5f9}
.mini-zone i{display:block;height:100%}
.session{
  background:#fff;border:1px solid var(--line);border-radius:18px;
  padding:20px 22px;margin-top:16px;
  box-shadow:0 1px 2px rgba(15,23,42,.03);
}
.session-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:10px}
.s-kicker{font-size:10.5px;letter-spacing:.06em;color:var(--rose);font-weight:700}
.session h3{margin:3px 0 0;font-size:21px;line-height:1.3;letter-spacing:-.01em}
.s-badge{
  flex:0 0 auto;text-align:right;
  font-size:10px;color:#64748b;line-height:1.5;
}
.s-badge b{display:block;font-size:17px;color:#0f172a;line-height:1.2}
.session p{font-size:13px;color:#475569;margin:10px 0}
details{margin-top:10px;border-top:1px solid #f1f5f9;padding-top:9px}
summary{cursor:pointer;font-size:11.5px;color:#64748b;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}
summary:before{content:"＋";display:inline-block;margin-right:6px;color:#94a3b8}
details[open] summary:before{content:"－"}
.split-table{min-width:0;font-size:11.5px}
.split-table td,.split-table th{padding:5px 8px}
.route-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}
.route-card{
  background:#fff;border:1px solid var(--line);border-radius:15px;
  padding:13px;overflow:hidden;
}
.route-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.route-date{font-size:10.5px;color:#94a3b8}
.route-name{font-size:13px;font-weight:700;margin-top:1px;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.route-dist{font-size:19px;font-weight:750;letter-spacing:-.02em;white-space:nowrap}
.route-dist span{font-size:9px;color:#94a3b8;font-weight:500;margin-left:2px}
.route-map{width:100%;height:auto;display:block;margin:8px 0 6px;border-radius:12px}
.route-stats{display:flex;justify-content:space-between;gap:5px;font-size:10px;color:#64748b;border-top:1px solid #f1f5f9;padding-top:7px}
.curve-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.curve-card{background:#fff;border:1px solid var(--line);border-radius:13px;padding:10px 11px 8px}
.curve-head{display:flex;justify-content:space-between;gap:8px;font-size:10.5px;color:#64748b}
.curve-head b{color:#0f172a;font-size:11.5px}
.curve-foot{display:flex;justify-content:space-between;gap:8px;font-size:9.5px;color:#94a3b8;margin-top:2px}
.corr-wrap{overflow-x:auto}
.corr{border-collapse:separate;border-spacing:3px;min-width:760px;width:100%;font-size:11px}
.corr th{border:0;background:transparent;padding:4px;text-align:center;font-size:10px;color:#64748b;white-space:normal}
.corr th.row{text-align:right;padding-right:8px;white-space:nowrap}
.corr td{
  border:0;padding:9px 4px;text-align:center;border-radius:7px;
  font-weight:700;font-size:11px;
}
.insight-list{display:grid;gap:9px;margin-top:12px}
.insight{display:flex;gap:10px;align-items:flex-start;font-size:12.5px;color:#475569}
.insight .n{
  flex:0 0 22px;height:22px;border-radius:7px;background:#f1f5f9;color:#475569;
  display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;
}
.insight b{color:#0f172a}
.rec-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}
.rec-card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px}
.rec-card h3{margin:0 0 8px;font-size:16px}
.rec-card p,.rec-card li{font-size:12.5px;color:#475569}
.rec-card ul{margin:6px 0 0;padding-left:18px}
.rec-card li{margin:5px 0}
.rec-num{font-size:10px;letter-spacing:.12em;color:var(--rose);font-weight:750}
.redlines{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.redline{background:#fff7f8;border:1px solid #fecdd3;border-radius:10px;padding:9px 10px;font-size:10.5px;color:#9f1239}
.redline b{display:block;font-size:13px;color:#be123c}
.checklist{display:grid;gap:7px;margin-top:8px}
.check{display:flex;gap:8px;align-items:flex-start;font-size:12px;color:#475569}
.check:before{content:"";flex:0 0 7px;height:7px;border-radius:50%;background:#0f766e;margin-top:7px}
.cover-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.cover{background:#f8fafc;border:1px solid #eef2f7;border-radius:11px;padding:11px 12px}
.cover b{display:block;font-size:19px;line-height:1.3}
.cover span{font-size:10.5px;color:#64748b}
.notes{font-size:12px;color:#64748b}
.notes li{margin:6px 0}
.footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:#94a3b8;font-size:10.5px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.toc-note{font-size:10.5px;color:#94a3b8;margin-top:8px}
@media(max-width:980px){
  .kpis{grid-template-columns:repeat(3,1fr)}
  .week{grid-template-columns:repeat(4,1fr)}
  .grid2,.grid3,.grid4{grid-template-columns:1fr}
  .route-grid{grid-template-columns:1fr 1fr}
  .curve-grid{grid-template-columns:1fr 1fr}
  .verdict{grid-template-columns:1fr}
  .verdict-side{border-left:0;border-top:1px solid rgba(255,255,255,.08)}
  .rec-grid{grid-template-columns:1fr}
  .redlines{grid-template-columns:1fr 1fr}
  .cover-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:620px){
  .wrap{padding:0 16px}
  .hero{padding:40px 0 24px}
  .kpis{grid-template-columns:1fr 1fr}
  .week{grid-template-columns:1fr 1fr}
  .route-grid,.curve-grid{grid-template-columns:1fr}
  .redlines{grid-template-columns:1fr}
  .card,.session{padding:16px}
  .sec-head{gap:8px}
  th,td{padding:7px 8px}
}
@media print{
  body{background:#fff}
  nav{display:none}
  .hero{padding:28px 0 20px}
  .kpis{grid-template-columns:repeat(3,1fr)}
  main{padding-top:10px}
  section{margin:24px 0}
  .card,.session,.route-card,.curve-card{box-shadow:none;break-inside:avoid}
  .chart{break-inside:avoid}
}
"""


# ---------- HTML 片段 ----------


def zone_mini(activity: dict[str, Any]) -> str:
    pct = activity["zone_pct"]
    if not pct:
        return '<span class="t-sub">—</span>'
    segments = "".join(
        f'<i style="width:{value:.2f}%;background:{ZONE_COLORS[i]}"></i>'
        for i, value in enumerate(pct)
        if value > 0
    )
    z45 = sum(pct[3:])
    return (
        f'<div class="mini-zone" title="Z1–Z5 占比">{segments}</div>'
        f'<div class="t-sub">Z4–5 {z45:.0f}%</div>'
    )


def te_class(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "low"
    if value >= 4:
        return "high"
    if value >= 2.5:
        return "mid"
    return "low"


def render_activity_table(ctx: dict[str, Any]) -> str:
    rows: list[str] = []
    for act in ctx["activities"]:
        stride = (
            f"{act['stride'] / 100:.2f} m"
            if isinstance(act["stride"], (int, float))
            else "—"
        )
        gct = (
            f"{act['gct']:.0f} ms"
            if isinstance(act["gct"], (int, float))
            else "—"
        )
        vo = (
            f"{act['vertical_osc']:.1f} cm"
            if isinstance(act["vertical_osc"], (int, float))
            else "—"
        )
        rows.append(
            f"""
        <tr>
          <td><div class="t-main">{esc(day_md(act['date']))}</div><div class="t-sub">{esc(weekday_cn(act['date']))} {esc(act['time'])}</div></td>
          <td class="wrap"><div class="t-main">{esc(act['name'])}</div><div class="t-sub">{esc(act['te_label'] or '')}</div></td>
          <td class="num"><b>{act['km']:.2f}</b> km</td>
          <td class="num">{esc(fmt_hm(act['duration']))}</td>
          <td class="num">{esc(fmt_pace(act['pace']))}</td>
          <td class="num">{num(act['hr'])} / {num(act['max_hr'])}</td>
          <td class="num">{num(act['cadence'])}</td>
          <td class="num">{stride}</td>
          <td class="num">{gct}</td>
          <td class="num">{vo}</td>
          <td>{zone_mini(act)}</td>
          <td class="num"><span class="te {te_class(act['te'])}">{act['te']:.1f}</span><div class="t-sub">负荷 {num(act['load'])}</div></td>
        </tr>
        """
        )
    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>日期</th><th>课次</th><th>距离</th><th>用时</th><th>配速</th>
          <th>平均/最大 HR</th><th>步频</th><th>步幅</th><th>触地</th><th>垂直振幅</th>
          <th>心率区间</th><th>TE / 负荷</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def render_split_details(activity: dict[str, Any], label: str = "分段") -> str:
    splits = activity["splits"]
    if not splits:
        return ""
    rows = "".join(
        f"""
        <tr>
          <td class="num">{split['km']}</td>
          <td class="num">{esc(fmt_pace(split['sec']))}</td>
          <td class="num">{num(split['hr'])}</td>
          <td class="num">{num(split['cad'])}</td>
        </tr>
        """
        for split in splits
    )
    return f"""
    <details>
      <summary>查看 {len(splits)} 个完整 1 km 分段</summary>
      <div class="table-wrap">
        <table class="split-table">
          <thead><tr><th>km</th><th>配速 /km</th><th>平均 HR</th><th>步频</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </details>
    """


def render_week_strip(ctx: dict[str, Any]) -> str:
    cards: list[str] = []
    for day in ctx["days"]:
        acts = ctx["by_date"].get(day["date"], [])
        load = sum(a["load"] for a in acts)
        if acts:
            km = sum(a["km"] for a in acts)
            duration = sum(a["duration"] for a in acts)
            pace = safe_div(duration, km)
            main = f"{km:.2f}<small> km</small>"
            sub = (
                f"{len(acts)} 次 · {fmt_hm(duration)}<br>{fmt_pace(pace)} /km"
                if len(acts) > 1
                else f"{fmt_hm(duration)} · {fmt_pace(pace)} /km"
            )
            klass = "high" if load >= 300 else ("mid" if load >= 100 else "low")
        elif day["steps"]:
            main = "休息"
            sub = "无跑步记录"
            klass = "rest"
        else:
            main = "—"
            sub = "无数据"
            klass = "rest"
        score = day["score"]
        score_pill = (
            f'<span class="pill {"good" if score and score >= 80 else ("warn" if score and score >= 70 else "bad")}">{score} 分</span>'
            if score
            else '<span class="pill neutral">—</span>'
        )
        cards.append(
            f"""
        <div class="day-card {klass}">
          <div class="dc-date"><b>{esc(day_md(day['date']))}</b><span>{esc(weekday_cn(day['date']))}</span></div>
          <div class="dc-main">{main}</div>
          <div class="dc-sub">{sub}</div>
          <div class="dc-meta">
            <span>负荷 <b>{num(load)}</b></span>
            <span>睡眠 <b>{esc(fmt_short(day['sleep_all']))}</b></span>
            <span>评分 {score_pill}</span>
            <span>RHR <b>{num(day['rhr'])}</b></span>
          </div>
        </div>
        """
        )
    return f'<div class="week">{"".join(cards)}</div>'


def render_header(ctx: dict[str, Any]) -> str:
    days = ctx["days"]
    first = days[0]["date"] if days else ""
    last = days[-1]["date"] if days else ""
    if first and last:
        range_label = (
            f"{first[:4]}年{int(first[5:7])}月{int(first[8:10])}日 – "
            f"{int(last[5:7])}月{int(last[8:10])}日"
        )
    else:
        range_label = "—"
    account_name = ctx["account"].get("display_name") or "佳明用户"
    region = ctx["account"].get("region_label") or "中国区"
    root = ctx["root"]
    fit_count = sum(1 for _ in root.rglob("*.fit"))
    json_count = sum(1 for _ in root.rglob("*.json"))
    md_count = sum(1 for _ in root.rglob("*.md"))
    file_count = fit_count + json_count + md_count
    avg_sleep = ctx["sleep_avg"] / 3600
    score_text = f"{ctx['avg_score']:.1f}" if ctx["avg_score"] is not None else "—"
    return f"""
    <header class="hero">
      <div class="wrap">
        <div class="eyebrow">Garmin Data Review · 2026 W43</div>
        <h1>一周训练与恢复<br><em>全方位分析</em></h1>
        <p class="sub">{esc(range_label)} · {esc(account_name)} · {esc(region)}账号。把 9 次跑步、42 份健康数据和 9 个 FIT 文件放在一起看，重点不是“跑了多少”，而是训练刺激与恢复能力是否匹配。</p>
        <div class="meta">
          <span class="chip"><b>7</b> 天连续数据</span>
          <span class="chip"><b>{len(ctx['activities'])}</b> 次跑步</span>
          <span class="chip"><b>{file_count}</b> 个文件</span>
          <span class="chip"><b>{fit_count}</b> 个 FIT</span>
          <span class="chip">数据截至 <b>10/28 12:10</b></span>
          <span class="chip">生成于 <b>{esc(ctx['generated_at'])}</b></span>
        </div>
        <div class="kpis">
          <div class="kpi"><div class="k">总距离</div><div class="v">{ctx['total_km']:.2f}<small>km</small></div><div class="n">{len(ctx['activities'])} 次跑步</div></div>
          <div class="kpi"><div class="k">总用时</div><div class="v">{esc(fmt_hm(ctx['total_duration']))}</div><div class="n">移动 {esc(fmt_hm(ctx['total_moving']))}</div></div>
          <div class="kpi"><div class="k">整体配速</div><div class="v">{esc(fmt_pace(ctx['avg_pace']))}<small>/km</small></div><div class="n">按总用时计算</div></div>
          <div class="kpi"><div class="k">训练负荷</div><div class="v">{num(ctx['total_load'])}</div><div class="n">单次最高 635</div></div>
          <div class="kpi"><div class="k">平均睡眠</div><div class="v">{esc(fmt_short(ctx['night_avg']))}<small>h</small></div><div class="n">含午睡 {esc(fmt_short(ctx['sleep_avg']))}</div></div>
          <div class="kpi"><div class="k">睡眠评分</div><div class="v">{score_text}<small>/100</small></div><div class="n">7 晚平均</div></div>
        </div>
        <div class="verdict">
          <div class="verdict-main">
            <div class="verdict-kicker">核心判断</div>
            <div class="verdict-title">半马测试把训练负荷拉满，<b>睡眠不足</b>是当前更值得优先处理的变量。</div>
            <div class="toc-note" style="color:#94a3b8;margin-top:8px">10/25 单次负荷占本周 56%，随后 10/27–28 背靠背完成 41.36 km；HRV 仍稳定，但 10/28 晨起 RHR 47、睡眠 4:27，恢复端已经出现压力信号。</div>
          </div>
          <div class="verdict-side">
            <div><span>10/25 单次负荷</span><b>635 / {num(ctx['total_load'])}</b></div>
            <div><span>睡眠债（vs 7.5h/晚）</span><b>{ctx['sleep_debt'] / 3600:.1f} h</b></div>
            <div><span>HRV 状态</span><b>7/7 BALANCED</b></div>
            <div><span>10/28 晨起 RHR</span><b>47 bpm</b></div>
          </div>
        </div>
      </div>
    </header>
    <nav><div class="wrap">
      <a href="#overview">概览</a>
      <a href="#training">训练负荷</a>
      <a href="#sessions">关键课</a>
      <a href="#zones">区间与技术</a>
      <a href="#sleep">睡眠</a>
      <a href="#recovery">恢复</a>
      <a href="#steps">日常活动</a>
      <a href="#correlation">关联</a>
      <a href="#recommendations">建议</a>
      <a href="#data">数据说明</a>
    </div></nav>
    """


def render_overview(ctx: dict[str, Any]) -> str:
    days = ctx["days"]
    hard_labels = "、".join(day_md(d) for d in ctx["hard_dates"])
    total_steps = ctx["steps_total"]
    return f"""
    <section id="overview">
      <div class="sec-head">
        <div class="sec-num">01</div>
        <div><h2>本周速览</h2><p class="lede">七天里安排了 9 次跑步、1 个完整休息日；跑量高度集中在半马测试和随后两天的背靠背训练。睡眠是唯一持续低于目标的维度。</p></div>
      </div>
      {render_week_strip(ctx)}
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">每日步数与睡眠</div><div class="card-note">柱：步数　线：睡眠（含午睡）</div></div>
        {chart_daily_rhythm(days)}
        <div class="legend"><span><i class="dot" style="background:#c7d2fe"></i>步数</span><span><i class="dot" style="background:#0f766e"></i>睡眠时长</span><span><i class="dot" style="background:#fbbf24"></i>睡眠评分</span></div>
      </div>
      <div class="grid3" style="margin-top:14px">
        <div class="card">
          <span class="pill bad">训练刺激</span>
          <div style="font-size:31px;font-weight:750;line-height:1.25;margin-top:8px;letter-spacing:-.02em">635</div>
          <div style="font-size:12px;color:#64748b">10/25 半马测试的单次负荷，占本周总负荷 56%。TE 5.0 被设备标记为“过度负荷”，不是普通长距离。</div>
        </div>
        <div class="card">
          <span class="pill bad">恢复缺口</span>
          <div style="font-size:31px;font-weight:750;line-height:1.25;margin-top:8px;letter-spacing:-.02em">4:27</div>
          <div style="font-size:12px;color:#64748b">10/28 夜间睡眠，评分 55，REM 仅 10 分钟；随后仍完成 22.75 km 长距离。</div>
        </div>
        <div class="card">
          <span class="pill warn">早期信号</span>
          <div style="font-size:31px;font-weight:750;line-height:1.25;margin-top:8px;letter-spacing:-.02em">47</div>
          <div style="font-size:12px;color:#64748b">10/28 晨起静息心率，周内最高；HRV 仍在平衡区，说明尚未明显抑制，但 RHR 已先动。</div>
        </div>
      </div>
      <div class="callout" style="margin-top:14px">
        <b>一句话总结：</b>{hard_labels} 三天合计 {ctx['hard_km']:.1f} km，占本周跑量 {ctx['hard_share']:.1f}%；10/27–28 背靠背 {ctx['back_to_back']:.1f} km。训练刺激足够，恢复（尤其睡眠）没有跟上。本周总步数 {total_steps:,} 步，跑步贡献约 {ctx['total_run_steps']:,} 步。
      </div>
    </section>
    """


def render_training(ctx: dict[str, Any]) -> str:
    acts = ctx["activities"]
    quality = [a for a in acts if (a["te"] or 0) >= 3]
    easy = [a for a in acts if (a["te"] or 0) < 3 and a["km"] < 15]
    long_runs = [a for a in acts if a["km"] >= 15]
    return f"""
    <section id="training">
      <div class="sec-head">
        <div class="sec-num">02</div>
        <div><h2>训练负荷与课表</h2><p class="lede">总跑量 {ctx['total_km']:.2f} km，总负荷 {num(ctx['total_load'])}。负荷曲线只有一个明显尖峰：10/25 半马测试。之后没有完全恢复，就又叠加了两天较大跑量。</p></div>
      </div>
      <div class="stat-row">
        <div class="stat"><b>{ctx['total_km']:.2f} km</b>总跑量</div>
        <div class="stat"><b>{esc(fmt_hm(ctx['total_duration']))}</b>总用时</div>
        <div class="stat"><b>{esc(fmt_pace(ctx['avg_pace']))} /km</b>整体配速</div>
        <div class="stat"><b>{num(ctx['total_load'])}</b>训练负荷</div>
        <div class="stat"><b>{num(ctx['total_calories'])}</b>活动热量 kcal</div>
        <div class="stat"><b>{len(quality)} / {len(easy)} / {len(long_runs)}</b>质量 / 轻松 / 长距离</div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">单次训练负荷</div><div class="card-note">按活动时间排序；红线为 10/25 半马测试</div></div>
        {chart_load(acts)}
        <div class="callout" style="margin-top:12px"><b>负荷结构：</b>10/25 的 635 相当于本周其余 8 次总和的 1.26 倍；10/27 的 169 和 10/28 的 110 都不算“轻松”，两天合计又完成 {ctx['back_to_back']:.1f} km。</div>
      </div>
      <div style="margin-top:16px">
        <div class="card-head"><div class="card-title">活动明细</div><div class="card-note">滑动查看完整表格</div></div>
        {render_activity_table(ctx)}
        <p class="notes" style="margin:8px 2px 0">注：10/22 的分段含明显停顿与心率伪差（第 6 km 平均 HR 85），不按持续跑解读；10/27 为一个早晨的 4 段训练，表中拆开显示。</p>
      </div>
    </section>
    """


def render_sessions(ctx: dict[str, Any]) -> str:
    race = ctx["race_act"]
    threshold = ctx["threshold_act"]
    long_run = ctx["long_act"]
    if not race or not long_run:
        return ""
    race_z5 = race["zone_pct"][4] if len(race["zone_pct"]) > 4 else 0
    threshold_day = ctx["by_date"].get(threshold["date"], []) if threshold else []
    threshold_day_km = sum(a["km"] for a in threshold_day)
    threshold_stats = (
        f"{threshold['km']:.2f} km / {fmt_hm(threshold['duration'])} / {fmt_pace(threshold['pace'])}"
        if threshold
        else "—"
    )
    return f"""
    <section id="sessions">
      <div class="sec-head">
        <div class="sec-num">03</div>
        <div><h2>三节关键课</h2><p class="lede">一节接近比赛的半马全力输出，一节被拆成 4 段的阈值课，以及一节在严重缺觉后完成的长距离。它们共同解释了本周的负荷曲线。</p></div>
      </div>

      <article class="session">
        <div class="session-head">
          <div><div class="s-kicker">10/25 · 房山区 · 半马测试</div><h3>{race['km']:.2f} km @ {fmt_pace(race['pace'])} /km</h3></div>
          <div class="s-badge"><b>TE {race['te']:.1f}</b>负荷 {num(race['load'])}<br>有氧 5.0 / 无氧 {race['anaerobic_te']:.1f}</div>
        </div>
        <div class="stat-row">
          <div class="stat"><b>{esc(fmt_hm(race['duration']))}</b>用时</div>
          <div class="stat"><b>{num(race['hr'])} / {num(race['max_hr'])}</b>平均 / 最大 HR</div>
          <div class="stat"><b>{num(race['cadence'])}</b>步频 spm</div>
          <div class="stat"><b>{race['stride'] / 100:.2f} m</b>步幅</div>
          <div class="stat"><b>{race['gct']:.0f} ms</b>触地时间</div>
          <div class="stat"><b>{race_z5:.0f}%</b>Z5 占比</div>
        </div>
        {chart_splits(race)}
        <p>前半 10 km 约 38:04，后半 10 km 约 39:01，前后只差 57 秒，配速控制很稳；最快 5 km {fmt_hm(race['fastest_5k'])}，最快 21.098 km {fmt_hm(race['fastest_half'])}。前 16 km 心率多在 176–192，后 5 km 降至 154–165，而配速与步频没有同步下降——这更像心率带/佩戴或个体数据异常，不建议直接解释为“后程轻松”。</p>
        <p>设备给出有氧 TE 5.0（OVERREACHING）与 635 的训练负荷，说明恢复成本远高于普通长距离。赛后身体电量从 46 降到 21、最低 7，压力均值 37（周内最高），与“全力输出”一致。</p>
        {render_split_details(race)}
      </article>

      <article class="session">
        <div class="session-head">
          <div><div class="s-kicker">10/27 · 海淀区 · 阈值课拆成 4 段</div><h3>{threshold_day_km:.2f} km 总跑量 · 主课 {threshold_stats}</h3></div>
          <div class="s-badge"><b>TE {threshold['te']:.1f}</b>日负荷 {num(sum(a['load'] for a in threshold_day))}<br>4 段 / 18.61 km</div>
        </div>
        <div class="stat-row">
          <div class="stat"><b>{num(threshold['hr'])} / {num(threshold['max_hr'])}</b>主课平均 / 最大 HR</div>
          <div class="stat"><b>{fmt_pace(threshold['pace'])}</b>主课配速</div>
          <div class="stat"><b>{num(threshold['cadence'])}</b>步频 spm</div>
          <div class="stat"><b>{sum(a['km'] for a in threshold_day):.2f} km</b>当日合计</div>
        </div>
        {chart_splits(threshold)}
        <p>一个早晨拆成热身 2.84 km、阈值段 2.40 km、主课 12.02 km、冷身 1.35 km。主课前 2–3 km 跑到 4:22 / 4:18、HR 154 / 158，随后回落到 5:00 左右；2.40 km 段 4:09、HR 153。负荷 169 不算高，但“分段多 + 总量大”让它成为 10/28 长距离前的重要前置疲劳。</p>
        {render_split_details(threshold)}
      </article>

      <article class="session">
        <div class="session-head">
          <div><div class="s-kicker">10/28 · 海淀区 · 缺觉后的长距离</div><h3>{long_run['km']:.2f} km @ {fmt_pace(long_run['pace'])} /km</h3></div>
          <div class="s-badge"><b>TE {long_run['te']:.1f}</b>负荷 {num(long_run['load'])}<br>睡眠 4:27 / 评分 55</div>
        </div>
        <div class="stat-row">
          <div class="stat"><b>{esc(fmt_hm(long_run['duration']))}</b>用时</div>
          <div class="stat"><b>{num(long_run['hr'])} / {num(long_run['max_hr'])}</b>平均 / 最大 HR</div>
          <div class="stat"><b>{num(long_run['cadence'])}</b>步频 spm</div>
          <div class="stat"><b>{long_run['stride'] / 100:.2f} m</b>步幅</div>
          <div class="stat"><b>{long_run['gct']:.0f} ms</b>触地时间</div>
          <div class="stat"><b>2 km</b>快速段（13–14 km）</div>
        </div>
        {chart_splits(long_run)}
        <p>平均 5:21，但在 13–14 km 突然提速到 3:51 / 3:48（HR 157 / 166），随后回落到 5:40 左右。这使一节“长距离”同时包含了接近马配的快速段，训练价值不低；代价是它发生在前一晚仅 4:27 睡眠、且前一天刚跑 18.6 km 的背景下。</p>
        <p>设备把这次判为有氧基础（TE 3.2、负荷 110），从单次看不算过量；把 10/27–28 连起来看，才是本周最需要警惕的组合。</p>
        {render_split_details(long_run)}
      </article>
    </section>
    """


def render_tech_table(ctx: dict[str, Any]) -> str:
    rows = []
    for act in ctx["activities"]:
        rows.append(
            f"""
        <tr>
          <td><div class="t-main">{esc(day_md(act['date']))} {esc(act['time'])}</div><div class="t-sub">{esc(act['name'])}</div></td>
          <td class="num">{esc(fmt_pace(act['pace']))}</td>
          <td class="num">{num(act['cadence'])}</td>
          <td class="num">{act['stride'] / 100:.2f} m</td>
          <td class="num">{act['gct']:.0f} ms</td>
          <td class="num">{act['vertical_osc']:.1f} cm</td>
          <td class="num">{act['vertical_ratio']:.1f}%</td>
          <td class="num"><span class="te {te_class(act['te'])}">{act['te']:.1f}</span></td>
        </tr>
        """
        )
    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr><th>课次</th><th>配速</th><th>步频 spm</th><th>步幅</th><th>触地</th><th>垂直振幅</th><th>垂直比</th><th>TE</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def render_zones(ctx: dict[str, Any]) -> str:
    acts = ctx["activities"]
    zone_totals = [sum(a["zone_seconds"][i] for a in acts) for i in range(5)]
    zone_sum = sum(zone_totals)
    week_pct = [z / zone_sum * 100 for z in zone_totals] if zone_sum else [0] * 5
    race = ctx["race_act"]
    race_z5 = race["zone_pct"][4] if race and len(race["zone_pct"]) > 4 else 0
    return f"""
    <section id="zones">
      <div class="sec-head">
        <div class="sec-num">04</div>
        <div><h2>心率区间与跑步技术</h2><p class="lede">本周心率分布呈明显两极：10/25 几乎全部在 Z5，轻松跑则集中在 Z1–Z2。技术指标随配速自然变化，没有看到明显的过度跨步。</p></div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">每次活动的心率区间</div><div class="card-note">设备区间 Z1–Z5；右侧为 Z4–5 合计</div></div>
        {chart_zones(acts)}
        <div class="legend">
          <span><i class="dot" style="background:{ZONE_COLORS[0]}"></i>Z1</span>
          <span><i class="dot" style="background:{ZONE_COLORS[1]}"></i>Z2</span>
          <span><i class="dot" style="background:{ZONE_COLORS[2]}"></i>Z3</span>
          <span><i class="dot" style="background:{ZONE_COLORS[3]}"></i>Z4</span>
          <span><i class="dot" style="background:{ZONE_COLORS[4]}"></i>Z5</span>
        </div>
        <div class="callout" style="margin-top:12px"><b>区间结构：</b>周合计 Z1–Z2 {week_pct[0] + week_pct[1]:.0f}%、Z3 {week_pct[2]:.0f}%、Z4–5 {week_pct[3] + week_pct[4]:.0f}%。10/25 单次 Z5 占 {race_z5:.0f}%，是典型的半马比赛/测试强度；10/27 主课和 10/28 快速段把 Z4–5 又补了一部分。</div>
        <div class="card-head" style="margin-top:18px"><div class="card-title">跑步技术</div><div class="card-note">步幅 = 设备 avgStrideLength / 100；垂直比 = 垂直振幅 / 步幅</div></div>
        {render_tech_table(ctx)}
        <p class="notes" style="margin:8px 2px 0">步频 176–188 spm，10/25 最高 188；触地 209–269 ms，10/25 最短；垂直振幅 7.6–8.8 cm。轻松跑步频略低、触地略长是正常的配速效应，不必单独纠正。设备估算 VO₂max 稳定在 62。</p>
      </div>
    </section>
    """


def render_sleep(ctx: dict[str, Any]) -> str:
    days = ctx["days"]
    best = ctx["best_sleep"]
    worst = ctx["worst_sleep"]
    need_text = "—"
    if worst and worst["need_actual"]:
        need_text = f"{worst['need_actual'] // 60}h{worst['need_actual'] % 60:02d}"
    rows = []
    for day in days:
        nap = f"（+午睡 {day['nap'] // 60}m）" if day["nap"] else ""
        need = (
            f"{int(day['need_actual']) // 60}:{int(day['need_actual']) % 60:02d}"
            if day["need_actual"]
            else "—"
        )
        skin = (
            f"{day['skin']:+.1f}°C"
            if isinstance(day["skin"], (int, float))
            else "—"
        )
        rows.append(
            f"""
        <tr>
          <td><div class="t-main">{esc(day_md(day['date']))}</div><div class="t-sub">{esc(weekday_cn(day['date']))}</div></td>
          <td>{esc(day['bed'])}–{esc(day['wake'])}</td>
          <td><b>{esc(fmt_short(day['sleep_total']))}</b><div class="t-sub">{esc(nap)}</div></td>
          <td class="num">{day['deep'] // 60} min</td>
          <td class="num">{day['rem'] // 60} min</td>
          <td class="num">{day['awake'] // 60} min</td>
          <td><span class="pill {'good' if (day['score'] or 0) >= 80 else ('warn' if (day['score'] or 0) >= 70 else 'bad')}">{day['score'] or '—'} 分</span><div class="t-sub">{esc(QUAL_LABEL.get(day['score_qual'], day['score_qual']))}</div></td>
          <td class="num">{need}</td>
          <td class="num">{num(day['spo2'])} / {num(day['spo2_low'])}%</td>
          <td class="num">{num(day['resp'])}</td>
          <td class="num">{skin}</td>
        </tr>
        """
        )
    return f"""
    <section id="sleep">
      <div class="sec-head">
        <div class="sec-num">05</div>
        <div><h2>睡眠：最大的恢复短板</h2><p class="lede">平均每晚 5 小时 52 分（含午睡 5 小时 59 分），7 晚中有 4 晚夜间睡眠不足 6 小时。设备建议的睡眠需求是 7 小时 20 分到 8 小时，实际连续低于下限。</p></div>
      </div>
      <div class="grid3" style="margin-bottom:14px">
        <div class="card"><div class="stat"><b>{esc(fmt_short(ctx['night_avg']))}</b>夜间平均</div><div class="t-sub" style="font-size:11px;color:#64748b">含午睡 {esc(fmt_short(ctx['sleep_avg']))}</div></div>
        <div class="card"><div class="stat"><b>{ctx['sleep_debt'] / 3600:.1f} h</b>睡眠债（vs 7.5h/晚）</div><div class="t-sub" style="font-size:11px;color:#64748b">相当于少睡约 {ctx['sleep_debt'] / 3600 / 7.5:.1f} 晚</div></div>
        <div class="card"><div class="stat"><b>{len(ctx['nights_under_6'])} 晚</b>夜间睡眠 &lt; 6h</div><div class="t-sub" style="font-size:11px;color:#64748b">最低 10/28：4:27</div></div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">睡眠阶段与评分</div><div class="card-note">柱顶数字：评分；柱内：总睡眠</div></div>
        {chart_sleep_stacked(days)}
        <div class="legend">
          <span><i class="dot" style="background:{SLEEP_COLORS['deep']}"></i>深睡</span>
          <span><i class="dot" style="background:{SLEEP_COLORS['light']}"></i>浅睡</span>
          <span><i class="dot" style="background:{SLEEP_COLORS['rem']}"></i>REM</span>
          <span><i class="dot" style="background:{SLEEP_COLORS['awake']}"></i>清醒</span>
          <span><i class="dot" style="background:{SLEEP_COLORS['nap']}"></i>午睡</span>
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">入睡与起床时间</div><div class="card-note">绿色区域为 22:30–06:30 参考窗口</div></div>
        {chart_sleep_timing(days)}
      </div>
      <div style="margin-top:16px">
        <div class="card-head"><div class="card-title">逐日睡眠明细</div><div class="card-note">SpO₂ 为平均 / 最低值；皮温为相对基线偏差</div></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>日期</th><th>睡眠窗口</th><th>总睡眠</th><th>深睡</th><th>REM</th><th>清醒</th><th>评分</th><th>设备需求</th><th>SpO₂</th><th>呼吸</th><th>皮温</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        <p class="notes" style="margin:8px 2px 0">睡眠阶段为设备估算；SpO₂ 最低值 82–86% 多与佩戴松动、体动或测量伪差有关，单次低值不构成临床判断。10/23 的 6:07 为夜间 5:21 + 午睡 46 分钟。</p>
      </div>
      <div class="callout warn" style="margin-top:14px">
        <b>最需要记住的一晚：</b>10/28 00:44 入睡、05:25 起床，总睡眠 4:27，评分 55，REM 仅 10 分钟；设备建议需求 {need_text}。这不是“少睡一点”，而是明显不足以支撑随后 22.75 km 长距离的恢复。
      </div>
    </section>
    """


def render_recovery(ctx: dict[str, Any]) -> str:
    days = ctx["days"]
    race = ctx["race_act"]
    curves = "".join(
        f"""
        <div class="curve-card">
          <div class="curve-head"><b>{esc(day_md(day['date']))} {esc(weekday_cn(day['date']))}</b><span>{day['score'] or '—'} 分 · {esc(QUAL_LABEL.get(day['score_qual'], day['score_qual']))}</span></div>
          {chart_day_curve(day)}
          <div class="curve-foot"><span>BB {num(day['bb_start'])} → {num(day['bb_end'])}</span><span>压力 {num(day['stress_avg'])}</span></div>
        </div>
        """
        for day in days
    )
    return f"""
    <section id="recovery">
      <div class="sec-head">
        <div class="sec-num">06</div>
        <div><h2>恢复：HRV 稳定，但“电量”一直不高</h2><p class="lede">HRV 七天全部处于 BALANCED，说明自主神经没有明显被抑制；但静息心率在 10/28 升到 47，身体电量晨起长期在 11–22，睡眠债已经在另一条曲线上体现。</p></div>
      </div>
      <div class="grid2">
        <div class="card">
          <div class="card-head"><div class="card-title">静息心率</div><div class="card-note">实线：每日　虚线：7 日均值</div></div>
          {chart_rhr(days)}
        </div>
        <div class="card">
          <div class="card-head"><div class="card-title">夜间 HRV</div><div class="card-note">绿带：设备平衡区间</div></div>
          {chart_hrv(days)}
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">身体电量：晨起与日终</div><div class="card-note">红点为当日最低值；10/28 为半日数据</div></div>
        {chart_body_battery(days)}
        <div class="legend">
          <span><i class="dot" style="background:#99f6e4"></i>晨起</span>
          <span><i class="dot" style="background:#0f766e"></i>日终</span>
          <span><i class="dot" style="background:#dc2626"></i>当日最低</span>
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">压力构成</div><div class="card-note">柱顶：日均 / 最高；柱内：休息、低、中、高压力占比</div></div>
        {chart_stress(days)}
        <div class="legend">
          <span><i class="dot" style="background:{STRESS_COLORS['rest']}"></i>休息 ≤25</span>
          <span><i class="dot" style="background:{STRESS_COLORS['low']}"></i>低 26–50</span>
          <span><i class="dot" style="background:{STRESS_COLORS['med']}"></i>中 51–75</span>
          <span><i class="dot" style="background:{STRESS_COLORS['high']}"></i>高 ≥76</span>
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">每日身体电量 / 压力曲线</div><div class="card-note">青色面积：身体电量　橙线：压力　每 15 分钟采样</div></div>
        <div class="curve-grid">{curves}</div>
      </div>
      <div class="callout warn" style="margin-top:14px">
        <b>恢复读数：</b>RHR 周均 {ctx['rhr_avg']:.1f} bpm，10/28 升至 {num(ctx['rhr_max'])}；HRV 范围 {num(ctx['hrv_min'])}–{num(ctx['hrv_max'])} ms，全部 BALANCED；晨起身体电量平均 {ctx['bb_morning_avg']:.1f}，有 {len(ctx['low_mornings'])}/7 天 ≤22。比赛日（10/25）身体电量 46 → 21、最低 7，压力均值 37、最高 98，是本周恢复成本最高的一天。
      </div>
      <div class="insight-list">
        <div class="insight"><span class="n">A</span><div><b>HRV 正常不代表恢复充分。</b>HRV 反映自主神经张力，睡眠时长、睡眠结构和身体电量反映“恢复量”；本周两者出现分歧，优先看睡眠与 RHR 趋势。</div></div>
        <div class="insight"><span class="n">B</span><div><b>RHR 的上升发生在最后一天。</b>10/25 赛后 RHR 41、10/26 43、10/27 44、10/28 47；与睡眠时长高度相关（r={ctx['corr_matrix']['sleep']['rhr']:+.2f}，仅 7 个样本），值得继续观察。</div></div>
        <div class="insight"><span class="n">C</span><div><b>身体电量“晨起低”是主线。</b>7 天里只有 10/25 晨起达到 46，其余多数在 20 附近；说明夜间充电不足，而不是白天消耗不够。</div></div>
      </div>
    </section>
    """


def render_steps(ctx: dict[str, Any]) -> str:
    days = ctx["days"]
    max_day = max(days, key=lambda d: d["steps"]) if days else None
    rest_day = min(days, key=lambda d: d["steps"]) if days else None
    return f"""
    <section id="steps">
      <div class="sec-head">
        <div class="sec-num">07</div>
        <div><h2>日常活动量</h2><p class="lede">七天总步数 {ctx['steps_total']:,} 步，完整日平均 {ctx['steps_complete_avg']:,.0f} 步。跑步贡献约 {ctx['total_run_steps']:,} 步，其余来自通勤、散步和日常活动。</p></div>
      </div>
      <div class="grid4" style="margin-bottom:14px">
        <div class="card"><div class="stat"><b>{ctx['steps_total']:,}</b>总步数</div></div>
        <div class="card"><div class="stat"><b>{ctx['steps_complete_avg']:,.0f}</b>完整日平均</div></div>
        <div class="card"><div class="stat"><b>{max_day['steps']:,}</b>最高日 {esc(day_md(max_day['date']))}</div></div>
        <div class="card"><div class="stat"><b>{rest_day['steps']:,}</b>最低日 {esc(day_md(rest_day['date']))}</div></div>
      </div>
      <div class="card">
        <div class="card-head"><div class="card-title">小时步数热力图</div><div class="card-note">颜色越深，单位小时步数越高；10/28 仅到 12:10</div></div>
        {chart_steps_heatmap(days)}
        <p class="notes" style="margin:8px 2px 0">跑步通常集中在 06:00–09:00，10/27 的 4 段训练把上午切得很碎；10/28 截至 12:10 已 25,701 步，是本周同期最高。10/26 为完整休息日，仅 6,419 步，与“减量日”相符。</p>
      </div>
    </section>
    """


def render_correlation(ctx: dict[str, Any]) -> str:
    defs = ctx["corr_defs"]
    matrix = ctx["corr_matrix"]
    header = "".join(f"<th>{esc(label)}</th>" for _, label, _ in defs)
    rows = []
    for row_key, row_label, _ in defs:
        cells = []
        for col_key, _, _ in defs:
            value = matrix[row_key][col_key]
            if row_key == col_key:
                cells.append('<td style="background:#f1f5f9;color:#94a3b8">—</td>')
                continue
            if value is None:
                cells.append('<td style="background:#f8fafc;color:#94a3b8">—</td>')
                continue
            alpha = 0.10 + 0.62 * min(1.0, abs(value))
            color = (
                f"rgba(15,118,110,{alpha:.2f})"
                if value >= 0
                else f"rgba(225,29,72,{alpha:.2f})"
            )
            text_color = "#ffffff" if abs(value) >= 0.55 else "#0f172a"
            cells.append(
                f'<td style="background:{color};color:{text_color}" title="n=7，探索性相关">{value:+.2f}</td>'
            )
        rows.append(
            f'<tr><th class="row">{esc(row_label)}</th>{"".join(cells)}</tr>'
        )
    return f"""
    <section id="correlation">
      <div class="sec-head">
        <div class="sec-num">08</div>
        <div><h2>多维关联：睡眠是枢纽</h2><p class="lede">把睡眠、心率、HRV、步数、压力和身体电量放在同一张相关矩阵里，睡眠时长与静息心率、压力的关系最突出。样本只有 7 天，以下只作为观察线索，不当作因果结论。</p></div>
      </div>
      <div class="card">
        <div class="corr-wrap">
          <table class="corr">
            <thead><tr><th></th>{header}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        <div class="legend"><span><i class="dot" style="background:#0f766e"></i>正相关</span><span><i class="dot" style="background:#e11d48"></i>负相关</span><span>颜色越深，|r| 越大；对角线不计算</span></div>
        <div class="insight-list">
          <div class="insight"><span class="n">1</span><div><b>睡眠时长 ↔ 静息心率：r = {matrix['sleep']['rhr']:+.2f}。</b>睡得越短，第二天 RHR 越高；10/28 睡眠 4:27、RHR 47 是最典型的一天。</div></div>
          <div class="insight"><span class="n">2</span><div><b>睡眠时长 ↔ 平均压力：r = {matrix['sleep']['stress']:+.2f}。</b>睡眠不足与白天压力偏高同向出现，但无法区分“睡不好导致压力高”还是“高压力导致睡不好”。</div></div>
          <div class="insight"><span class="n">3</span><div><b>步数 ↔ 平均压力：r = {matrix['steps']['stress']:+.2f}。</b>活动量大的日子压力分也高，可能反映训练/比赛的交感兴奋，而不是心理压力。</div></div>
          <div class="insight"><span class="n">4</span><div><b>HRV ↔ 日终电量：r = {matrix['hrv']['bb']:+.2f}。</b>关系较弱；HRV 稳定但身体电量低，说明“神经张力正常”和“恢复量不足”可以同时存在。</div></div>
        </div>
        <p class="notes" style="margin:10px 2px 0">统计口径：Pearson 相关，n=7；未做多重比较校正。睡眠时长含午睡，步数为当日总步数，压力为日均值，日终电量为当天最后一个有效值。相关不等于因果。</p>
      </div>
    </section>
    """


def render_recommendations(ctx: dict[str, Any]) -> str:
    return f"""
    <section id="recommendations">
      <div class="sec-head">
        <div class="sec-num">09</div>
        <div><h2>接下来怎么练</h2><p class="lede">目标不是“补回本周跑量”，而是把恢复补上，再恢复质量课。以下按“未来 72 小时”和“下一周”分开，跑量从 87 km 降到 50–55 km，质量课最多 1 次。</p></div>
      </div>
      <div class="rec-grid">
        <div class="rec-card">
          <div class="rec-num">NEXT 72 HOURS</div>
          <h3>先恢复，不加刺激</h3>
          <ul>
            <li><b>10/29：</b>完全休息或散步 20–30 分钟；不跑、不做力量。</li>
            <li><b>10/30：</b>轻松跑 30–40 分钟，心率 &lt;135，能完整说话；感觉累就改成走路。</li>
            <li><b>10/31：</b>休息，或 20 分钟髋/踝灵活性 + 核心；不做下肢大重量。</li>
            <li>三天目标睡眠 <b>8–9 小时/晚</b>；晚上 22:30 前上床，午睡 20–30 分钟。</li>
          </ul>
        </div>
        <div class="rec-card">
          <div class="rec-num">SLEEP PRESCRIPTION</div>
          <h3>把睡眠当作训练课</h3>
          <div class="checklist">
            <div class="check">固定上床时间 22:30–23:00，目标 7.5–8 小时</div>
            <div class="check">咖啡因截止 14:00；睡前 1 小时降光、降屏</div>
            <div class="check">午睡 20–30 分钟，不晚于 15:00</div>
            <div class="check">卧室 18–20°C，尽量遮光；睡前不大量饮酒</div>
            <div class="check">训练后 1 小时内补碳水 + 蛋白，避免“练完不吃”</div>
          </div>
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">下一周训练框架</div><div class="card-note">总量 50–55 km；质量课 1 次；长距离 1 次</div></div>
        <div class="table-wrap">
          <table style="min-width:720px">
            <thead><tr><th>日期</th><th>安排</th><th>强度 / 配速</th><th>目的</th></tr></thead>
            <tbody>
              <tr><td>10/29 周四</td><td>完全休息 / 散步</td><td>HR &lt;110</td><td>卸掉比赛与背靠背疲劳</td></tr>
              <tr><td>10/30 周五</td><td>轻松跑 30–40 min</td><td>HR &lt;135；6:00–6:30 /km</td><td>恢复血流，不追加负荷</td></tr>
              <tr><td>10/31 周六</td><td>休息 / 灵活性 20 min</td><td>—</td><td>睡眠优先</td></tr>
              <tr><td>11/01 周日</td><td>轻松跑 40–50 min</td><td>HR &lt;135；能对话</td><td>恢复有氧，不追配速</td></tr>
              <tr><td>11/02 周一</td><td>休息或轻松跑 30 min</td><td>HR &lt;130</td><td>根据晨起 RHR / BB 调整</td></tr>
              <tr><td>11/03 周二</td><td>阈值课 3×8 min</td><td>4:10–4:20 /km；间歇 2 min 慢跑；总 10–12 km</td><td>维持阈值刺激，仅 1 次质量课</td></tr>
              <tr><td>11/04 周三</td><td>轻松跑 30 min</td><td>HR &lt;135</td><td>恢复</td></tr>
              <tr><td>11/05 周四</td><td>长距离 14–16 km</td><td>5:30–5:45 /km；HR &lt;140</td><td>有氧耐力，不再加快速段</td></tr>
            </tbody>
          </table>
        </div>
        <p class="notes" style="margin:8px 2px 0">如果 10/29–30 晨起 RHR ≥47 或身体电量 ≤20，取消 10/30 的轻松跑，改为完全休息；如果 11/03 前睡眠评分仍 &lt;60，阈值课顺延。</p>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">监测红线</div><div class="card-note">出现任意两条，先减量/休息，再谈训练</div></div>
        <div class="redlines">
          <div class="redline"><b>RHR ≥47</b>连续 2 天，或比个人基线高 5+ bpm</div>
          <div class="redline"><b>HRV &lt;102 ms</b>连续 2 天，或明显低于平衡区间</div>
          <div class="redline"><b>睡眠评分 &lt;60</b>或睡眠 &lt;5h 连续 2 晚</div>
          <div class="redline"><b>晨起 BB ≤20</b>或出现关节/肌腱疼痛</div>
        </div>
        <div class="callout good" style="margin-top:12px"><b>本周值得保留的优点：</b>半马配速控制稳定（前后 10 km 只差 57 秒）；步频 188、触地 209 ms，技术效率好；HRV 七天全平衡；休息日执行到位（10/26 仅 6,419 步）。下一阶段不是“更努力”，而是把睡眠和强度日间隔补齐。</div>
        <p class="notes" style="margin:10px 2px 0">以上为基于设备数据的训练参考，不构成医疗建议。若出现持续心悸、胸痛、异常气短或失眠，请咨询专业医生。</p>
      </div>
    </section>
    """


def render_data(ctx: dict[str, Any]) -> str:
    root = ctx["root"]
    fit_count = sum(1 for _ in root.rglob("*.fit"))
    json_count = sum(1 for _ in root.rglob("*.json"))
    md_count = sum(1 for _ in root.rglob("*.md"))
    file_count = fit_count + json_count + md_count
    counts = (ctx["manifest"].get("counts") or {})
    activities_count = counts.get("activities") or {}
    health_count = counts.get("health") or {}
    partial = ctx["partial_days"]
    partial_text = "、".join(
        f"{day_md(d['date'])}（截至 {d['data_end'] // 60:02d}:{d['data_end'] % 60:02d}）"
        for d in partial
    ) or "无"
    return f"""
    <section id="data">
      <div class="sec-head">
        <div class="sec-num">10</div>
        <div><h2>数据说明与边界</h2><p class="lede">报告基于本地导出文件生成，未上传到任何外部服务。为了可复现，下面列出数据覆盖、口径和已知异常。</p></div>
      </div>
      <div class="cover-grid">
        <div class="cover"><b>7 天</b><span>2026-10-22 – 10-28</span></div>
        <div class="cover"><b>{len(ctx['activities'])} 次</b><span>活动 {activities_count.get('found', '—')} 个，FIT {fit_count} 个</span></div>
        <div class="cover"><b>{health_count.get('written', 42)} 份</b><span>健康 JSON（6 类 × 7 天）</span></div>
        <div class="cover"><b>{file_count} 个</b><span>本地文件：{fit_count} FIT / {json_count} JSON / {md_count} MD</span></div>
      </div>
      <div class="grid2" style="margin-top:14px">
        <div class="card">
          <div class="card-head"><div class="card-title">数据覆盖</div><div class="card-note">来自 manifest.json</div></div>
          <ul class="notes">
            <li>账号：{esc(ctx['account'].get('display_name') or '—')} · {esc(ctx['account'].get('region_label') or '—')}；报告不包含邮箱。</li>
            <li>导出时间：{esc(ctx['export_finished'])}；状态：{esc(ctx['manifest'].get('status', '—'))}；错误：{len(ctx['manifest'].get('errors') or [])} 条。</li>
            <li>活动：找到 {activities_count.get('found', '—')} 个，详情 {activities_count.get('details', '—')} 个，FIT {activities_count.get('fit', '—')} 个，失败 {activities_count.get('failed', '—')} 个。</li>
            <li>健康：写入 {health_count.get('written', '—')} 份，空数据 {health_count.get('empty', '—')} 份，失败 {health_count.get('failed', '—')} 份。</li>
            <li>不完整日期：{esc(partial_text)}。</li>
          </ul>
        </div>
        <div class="card">
          <div class="card-head"><div class="card-title">口径</div><div class="card-note">阅读图表前先看这里</div></div>
          <ul class="notes">
            <li>睡眠：夜间睡眠为 dailySleepDTO.sleepTimeSeconds（含清醒），总睡眠另加 napTimeSeconds；睡眠阶段为设备估算。</li>
            <li>心率区间：使用设备返回的 hrTimeInZone_1..5 秒数，未自行重算阈值；最大心率 196 bpm。</li>
            <li>训练负荷：Garmin activityTrainingLoad；TE 为有氧训练效果，0–5 分。</li>
            <li>身体电量：0–100，取当日第一个/最后一个有效值作为晨起/日终；最低值为当日最小采样。</li>
            <li>压力：0–100，取 5 分钟采样；区间按 ≤25 / 26–50 / 51–75 / ≥76 划分。</li>
            <li>配速：活动总用时 ÷ 距离；分段为完整 1 km 分段，最后不足 1 km 不计入分段图。</li>
          </ul>
        </div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="card-head"><div class="card-title">已知异常与限制</div><div class="card-note">这些地方不要过度解读</div></div>
        <ul class="notes">
          <li><b>10/22：</b>活动含明显停顿/间歇，分段受休息影响；第 6 km 平均 HR 85，属于心率带或佩戴伪差，不能当作真实心率。</li>
          <li><b>10/23：</b>后 4 km 配速 6:30–7:21、HR 90 左右，可能是走跑结合或光电心率低值；不作为有氧能力下降的证据。</li>
          <li><b>10/25：</b>后 5 km 心率从约 190 降到 154–165，而配速/步频未同步下降；存在心率带数据异常可能，报告未据此判断“后程轻松”。</li>
          <li><b>10/28：</b>健康数据仅到 12:10，身体电量、压力、步数为半日数据；日终电量、压力均值与步数不可与完整日直接比较。</li>
          <li><b>统计：</b>只有 7 天，相关矩阵为探索性；睡眠阶段、VO₂max、训练负荷均为设备估算，不同设备/固件可能不同。</li>
          <li><b>路线：</b>轨迹图为经纬度归一化后的示意图，无底图、未按比例尺；起点/终点仅用于区分方向。</li>
        </ul>
      </div>
      <div class="footer">
        <span>数据来源：{esc(str(root))}</span>
        <span>报告生成：{esc(ctx['generated_at'])} · 仅本地处理</span>
      </div>
    </section>
    """


def build_html(ctx: dict[str, Any]) -> str:
    sections = "".join(
        [
            render_overview(ctx),
            render_training(ctx),
            render_sessions(ctx),
            render_zones(ctx),
            render_sleep(ctx),
            render_recovery(ctx),
            render_steps(ctx),
            render_correlation(ctx),
            render_recommendations(ctx),
            render_data(ctx),
        ]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Garmin 一周训练与恢复分析 · 2026-10-22 – 10-28</title>
  <style>{CSS}</style>
</head>
<body>
  {render_header(ctx)}
  <main><div class="wrap">{sections}</div></main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="生成佳明数据 HTML 分析报告")
    parser.add_argument(
        "export_dir",
        nargs="?",
        default="/Users/xueyanjie/Downloads/Garmin导出/garmin_export_2026-10-22_2026-10-28",
        help="导出目录（包含 manifest.json / activities / health）",
    )
    parser.add_argument("-o", "--output", help="输出 HTML 路径")
    args = parser.parse_args()

    root = Path(args.export_dir).expanduser().resolve()
    if not (root / "manifest.json").is_file():
        raise SystemExit(f"找不到 manifest.json：{root}")

    ctx = build_context(root)
    output = Path(args.output).expanduser() if args.output else root / "Garmin数据分析报告.html"
    output.write_text(build_html(ctx), encoding="utf-8")
    print(f"已生成：{output}")
    print(f"大小：{output.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
