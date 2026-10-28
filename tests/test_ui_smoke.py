from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from garmin_exporter.config import HEALTH_KEYS  # noqa: E402
from garmin_exporter.paths import REGION_CN  # noqa: E402
from garmin_exporter.garmin_service import GarminService  # noqa: E402
from garmin_exporter.ui import MainWindow  # noqa: E402


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_window_does_not_start_login_without_saved_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GARMIN_EXPORTER_DATA_DIR"] = str(Path(tmp) / "data")
            try:
                with patch("garmin_exporter.ui.find_latest_saved_session", return_value=None):
                    window = MainWindow()
                    self.app.processEvents()
                    self.assertFalse(window._logging_in)
                    self.assertIsNone(window.login_worker)
                    window.deleteLater()
                    self.app.processEvents()
            finally:
                os.environ.pop("GARMIN_EXPORTER_DATA_DIR", None)

    def test_window_starts_login_for_saved_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GARMIN_EXPORTER_DATA_DIR"] = str(Path(tmp) / "data")
            try:
                fake_worker = type("FakeWorker", (), {
                    "log": type("Signal", (), {"connect": lambda self, callback: None})(),
                    "mfa_required": type("Signal", (), {"connect": lambda self, callback: None})(),
                    "succeeded": type("Signal", (), {"connect": lambda self, callback: None})(),
                    "failed": type("Signal", (), {"connect": lambda self, callback: None})(),
                    "finished": type("Signal", (), {"connect": lambda self, callback: None})(),
                    "__init__": lambda self, *args, **kwargs: None,
                    "start": lambda self: None,
                })
                with patch("garmin_exporter.ui.find_latest_saved_session", return_value=(REGION_CN, "me@example.com")), patch.object(GarminService, "has_matching_session", return_value=True), patch("garmin_exporter.ui.LoginWorker", fake_worker):
                    window = MainWindow()
                    self.app.processEvents()
                    self.assertTrue(window._logging_in)
                    self.assertIsNotNone(window.login_worker)
                    window.deleteLater()
                    self.app.processEvents()
            finally:
                os.environ.pop("GARMIN_EXPORTER_DATA_DIR", None)

    def test_window_constructs_with_china_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GARMIN_EXPORTER_DATA_DIR"] = str(Path(tmp) / "data")
            try:
                window = MainWindow()
                self.assertEqual(window.region_combo.currentData(), REGION_CN)
                self.assertTrue(window.cb_activities.isChecked())
                for key in HEALTH_KEYS:
                    self.assertTrue(window.health_checks[key].isChecked())
                self.assertFalse(window.export_btn.isEnabled())
                self.assertIsNotNone(window.grab())
                window.deleteLater()
                self.app.processEvents()
            finally:
                os.environ.pop("GARMIN_EXPORTER_DATA_DIR", None)


if __name__ == "__main__":
    unittest.main()
