from __future__ import annotations

import io
import json
import tempfile
import threading
import types
import unittest
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectConnectionError

from garmin_exporter.config import HEALTH_KEYS
from garmin_exporter.exporter import (
    Exporter,
    ExportOptions,
    _is_no_data_error,
    iter_dates,
)


def make_fit_zip(activity_id: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{activity_id}.fit", b"\x0e\x10\x00\x00" + b".FIT" + b"0" * 16)
    return buffer.getvalue()


class FakeGarmin:
    ActivityDownloadFormat = types.SimpleNamespace(ORIGINAL="original")

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_health: str | None = None
        self.auth_failure: bool = False
        self.no_heart_rate: bool = False

    def get_activities_by_date(self, start: str, end: str, sortorder: str = "asc"):
        self.calls.append("activities")
        return [
            {
                "activityId": 111,
                "activityName": "Morning Run",
                "startTimeLocal": "2026-10-01 07:00:00",
                "activityType": {"typeKey": "running"},
            },
            {
                "activityId": 222,
                "activityName": "Lunch/Walk: 5km?",
                "startTimeLocal": "2026-10-02 12:00:00",
                "activityType": {"typeKey": "walking"},
            },
        ]

    def get_activity(self, activity_id: str):
        self.calls.append(f"summary:{activity_id}")
        return {"activityId": activity_id, "summary": True}

    def get_activity_details(self, activity_id: str):
        self.calls.append(f"details:{activity_id}")
        return {"activityId": activity_id, "details": [1, 2, 3]}

    def download_activity(self, activity_id: str, fmt: Any):
        self.calls.append(f"fit:{activity_id}")
        return make_fit_zip(activity_id)

    def get_sleep_data(self, day: str):
        self.calls.append(f"sleep:{day}")
        return {"sleep": day}

    def get_heart_rates(self, day: str):
        self.calls.append(f"hr:{day}")
        if self.no_heart_rate:
            raise GarminConnectConnectionError("No heart rate data received")
        return {"heartRate": 60}

    def get_steps_data(self, day: str):
        self.calls.append(f"steps:{day}")
        return [{"steps": 100}]

    def get_stress_data(self, day: str):
        self.calls.append(f"stress:{day}")
        return {"stress": 20}

    def get_body_battery(self, start: str, end: str):
        self.calls.append(f"bb:{start}")
        return [{"date": start, "values": [50]}]

    def get_hrv_data(self, day: str):
        self.calls.append(f"hrv:{day}")
        return None


class ExporterTests(unittest.TestCase):
    def test_iter_dates(self) -> None:
        self.assertEqual(
            list(iter_dates(date(2026, 10, 1), date(2026, 10, 3))),
            [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)],
        )

    def test_full_export_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            fake = FakeGarmin()
            progress: list[tuple[Any, Any, str]] = []
            exporter = Exporter(
                fake,
                ExportOptions(
                    start=date(2026, 10, 1),
                    end=date(2026, 10, 2),
                    activities=True,
                    health=HEALTH_KEYS,
                    request_delay=0,
                ),
                target,
                account={"email": "me@example.com", "region_label": "中国区"},
                progress=lambda current, total, message: progress.append(
                    (current, total, message)
                ),
            )
            result = exporter.run()

            self.assertEqual(result.status, "success")
            self.assertTrue((target / "activities" / "activities.json").is_file())
            activity_dir = target / "activities" / "2026-10-01_111_Morning_Run"
            self.assertTrue((activity_dir / "activity.json").is_file())
            self.assertTrue((activity_dir / "details.json").is_file())
            self.assertTrue((activity_dir / "activity_111.fit").is_file())
            self.assertTrue(
                (target / "activities" / "2026-10-02_222_Lunch_Walk_5km").is_dir()
            )

            for day in ("2026-10-01", "2026-10-02"):
                for key in HEALTH_KEYS:
                    path = target / "health" / f"{day}_{key}.json"
                    self.assertTrue(path.is_file(), path)
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["date"], day)
                    self.assertEqual(payload["type"], key)

            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["activities"]["found"], 2)
            self.assertEqual(manifest["counts"]["activities"]["fit"], 2)
            self.assertEqual(manifest["counts"]["health"]["written"], 12)
            self.assertEqual(manifest["status"], "success")
            self.assertTrue((target / "README.md").is_file())
            self.assertEqual(progress[-1][0], progress[-1][1])

    def test_no_data_errors_are_recognized(self) -> None:
        for message in (
            "No data received from server",
            "No heart rate data received",
            "No device solar input data received",
            "no data",
        ):
            self.assertTrue(
                _is_no_data_error(GarminConnectConnectionError(message)), message
            )
        self.assertFalse(
            _is_no_data_error(GarminConnectConnectionError("Connection reset"))
        )

    def test_no_heart_rate_data_still_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            fake = FakeGarmin()
            fake.no_heart_rate = True
            result = Exporter(
                fake,
                ExportOptions(
                    start=date(2026, 10, 1),
                    end=date(2026, 10, 1),
                    activities=False,
                    health=("heart_rate",),
                    request_delay=0,
                ),
                target,
            ).run()
            self.assertEqual(result.status, "success")
            path = target / "health" / "2026-10-01_heart_rate.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNone(payload["data"])
            self.assertEqual(result.manifest["counts"]["health"]["empty"], 1)

    def test_skip_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            fake = FakeGarmin()
            options = ExportOptions(
                start=date(2026, 10, 1),
                end=date(2026, 10, 1),
                activities=True,
                health=("sleep",),
                skip_existing=True,
                request_delay=0,
            )
            Exporter(fake, options, target).run()
            first_calls = len(fake.calls)
            result = Exporter(fake, options, target).run()
            self.assertEqual(result.status, "success")
            # Second run only fetches the activity list; everything else exists.
            self.assertEqual(len(fake.calls), first_calls + 1)
            self.assertGreater(result.manifest["counts"]["activities"]["skipped"], 0)
            self.assertEqual(result.manifest["counts"]["health"]["skipped"], 1)

    def test_cancel_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            cancel = threading.Event()
            cancel.set()
            result = Exporter(
                FakeGarmin(),
                ExportOptions(
                    start=date(2026, 10, 1),
                    end=date(2026, 10, 1),
                    activities=True,
                    health=("sleep",),
                    request_delay=0,
                ),
                target,
                cancel_event=cancel,
            ).run()
            self.assertEqual(result.status, "cancelled")
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "cancelled")

    def test_zip_without_fit_keeps_original(self) -> None:
        class NoFitGarmin(FakeGarmin):
            def get_activities_by_date(self, start, end, sortorder="asc"):
                return [
                    {
                        "activityId": 333,
                        "activityName": "Swim",
                        "startTimeLocal": "2026-10-01 08:00:00",
                    }
                ]

            def download_activity(self, activity_id, fmt):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr("readme.txt", b"no fit here")
                return buffer.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out"
            result = Exporter(
                NoFitGarmin(),
                ExportOptions(
                    start=date(2026, 10, 1),
                    end=date(2026, 10, 1),
                    activities=True,
                    health=(),
                    request_delay=0,
                ),
                target,
            ).run()
            self.assertEqual(result.status, "partial")
            folder = target / "activities" / "2026-10-01_333_Swim"
            self.assertTrue((folder / "activity_333_original.zip").is_file())
            self.assertEqual(result.manifest["counts"]["activities"]["fit"], 0)


if __name__ == "__main__":
    unittest.main()
