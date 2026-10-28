"""Application entry point."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import QApplication

from garmin_exporter.paths import APP_NAME, APP_TITLE, APP_VERSION, log_dir
from garmin_exporter.ui import MainWindow, make_app_icon


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    pattern = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        file_handler = RotatingFileHandler(
            log_dir() / "app.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(pattern)
        root.addHandler(file_handler)
    except OSError:
        pass
    # garminconnect can be chatty and its debug output contains request URLs.
    logging.getLogger("garminconnect").setLevel(logging.WARNING)


def main() -> int:
    setup_logging()
    logging.getLogger(__name__).info("Starting %s %s", APP_NAME, APP_VERSION)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_TITLE)
    QApplication.setOrganizationName("Ducc")

    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(make_app_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
