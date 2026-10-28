from __future__ import annotations

import json
import os
import tempfile
import unittest

from garmin_exporter.garmin_service import GarminService, find_latest_saved_session
from garmin_exporter.paths import REGION_CN, REGION_GLOBAL


class SessionTests(unittest.TestCase):
    def test_matching_session_requires_region_and_email(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GARMIN_EXPORTER_DATA_DIR"] = tmp
            try:
                service = GarminService("Me@Example.com", "", REGION_CN)
                service.session_directory.mkdir(parents=True)
                service.token_file.write_text("{}", encoding="utf-8")
                service.meta_file.write_text(
                    json.dumps({"email": "me@example.com", "region": REGION_CN}),
                    encoding="utf-8",
                )
                self.assertTrue(service.has_matching_session())
                self.assertFalse(
                    GarminService("other@example.com", "", REGION_CN).has_matching_session()
                )
                self.assertFalse(
                    GarminService("me@example.com", "", REGION_GLOBAL).has_matching_session()
                )
            finally:
                os.environ.pop("GARMIN_EXPORTER_DATA_DIR", None)

    def test_latest_session_uses_saved_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GARMIN_EXPORTER_DATA_DIR"] = tmp
            try:
                for region, email, saved_at in (
                    (REGION_CN, "cn@example.com", "2026-01-01T00:00:00+00:00"),
                    (REGION_GLOBAL, "global@example.com", "2026-02-01T00:00:00+00:00"),
                ):
                    service = GarminService("", "", region)
                    service.session_directory.mkdir(parents=True)
                    service.token_file.write_text("{}", encoding="utf-8")
                    service.meta_file.write_text(
                        json.dumps(
                            {"email": email, "region": region, "saved_at": saved_at}
                        ),
                        encoding="utf-8",
                    )
                self.assertEqual(
                    find_latest_saved_session(), (REGION_GLOBAL, "global@example.com")
                )
            finally:
                os.environ.pop("GARMIN_EXPORTER_DATA_DIR", None)


if __name__ == "__main__":
    unittest.main()
