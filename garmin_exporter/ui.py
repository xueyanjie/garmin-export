"""PySide6 user interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QSettings, QTimer, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .config import HEALTH_KEYS, HEALTH_LABELS, load_config, save_config
from .exporter import ExportOptions, ExportResult
from .garmin_service import (
    GarminService,
    REGION_LABELS,
    find_latest_saved_session,
)
from .paths import (
    APP_TITLE,
    APP_VERSION,
    REGION_CN,
    REGION_GLOBAL,
    default_export_dir,
    timestamp_slug,
)
from .workers import ExportWorker, LoginWorker

LOGGER = logging.getLogger(__name__)

BG = "#F3F6FA"
CARD = "#FFFFFF"
TEXT = "#172B4D"
MUTED = "#6B7C93"
LINE = "#E3E9F1"
PRIMARY = "#0A6CFF"
PRIMARY_HOVER = "#0059D6"
SUCCESS = "#0B8457"

STYLE_SHEET = f"""
QWidget#Root {{
    background: {BG};
    color: {TEXT};
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QFrame#Card {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
QLabel#Title {{
    font-size: 26px;
    font-weight: 700;
    color: #10233F;
}}
QLabel#Subtitle {{
    font-size: 12px;
    color: {MUTED};
}}
QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: 700;
    color: #10233F;
}}
QLabel#FieldLabel {{
    font-size: 12px;
    color: {MUTED};
}}
QLabel#Hint {{
    font-size: 11px;
    color: {MUTED};
}}
QLabel#ErrorHint {{
    font-size: 11px;
    color: #C0392B;
}}
QLabel#StatusText {{
    font-size: 12px;
    color: {MUTED};
}}
QLineEdit, QComboBox, QDateEdit {{
    background: #FBFCFE;
    border: 1px solid #D7DFEA;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 20px;
    selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
    background: #FFFFFF;
    border: 1px solid {PRIMARY};
}}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
    background: #F5F7FA;
    color: #9AA8BA;
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    border: none;
    width: 24px;
}}
QPushButton {{
    border-radius: 8px;
    padding: 8px 14px;
    border: 1px solid #D7DFEA;
    background: #FFFFFF;
    color: #263B59;
}}
QPushButton:hover {{
    background: #F5F8FC;
    border-color: #C4D0E0;
}}
QPushButton:pressed {{
    background: #EDF2F8;
}}
QPushButton:disabled {{
    color: #A9B4C4;
    background: #F3F5F8;
    border-color: #E5EAF1;
}}
QPushButton#Primary {{
    background: {PRIMARY};
    border: 1px solid {PRIMARY};
    color: #FFFFFF;
    font-weight: 600;
    padding: 9px 16px;
}}
QPushButton#Primary:hover {{
    background: {PRIMARY_HOVER};
    border-color: {PRIMARY_HOVER};
}}
QPushButton#Primary:disabled {{
    background: #B9D2FA;
    border-color: #B9D2FA;
    color: #FFFFFF;
}}
QPushButton#Danger {{
    background: #FFFFFF;
    border: 1px solid #E9B5AF;
    color: #B03A2E;
}}
QPushButton#Danger:hover {{
    background: #FDF1EF;
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 4px 2px;
    text-align: left;
}}
QPushButton#Link:hover {{
    color: {PRIMARY};
}}
QPushButton#Mini {{
    padding: 6px 9px;
    font-size: 11px;
}}
QFrame#MfaCard {{
    background: #EFF6FF;
    border: 1px solid #C7DDFB;
    border-radius: 9px;
}}
QCheckBox {{
    spacing: 8px;
    color: #2A3F5C;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #B9C6D8;
    background: #FFFFFF;
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QProgressBar {{
    border: none;
    background: #E7EDF6;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: 4px;
}}
QPlainTextEdit#Log {{
    background: #0E1724;
    color: #C7D6E8;
    border: none;
    border-radius: 8px;
    padding: 8px;
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 11px;
    selection-background-color: #21456F;
}}
QFrame#Divider {{
    background: {LINE};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #C5D1E1;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def make_app_icon() -> QIcon:
    pix = QPixmap(128, 128)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, 128, 128)
    gradient.setColorAt(0, QColor("#1B84FF"))
    gradient.setColorAt(1, QColor("#0056C7"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 120, 120, 28, 28)

    pen = QPen(QColor("white"))
    pen.setWidth(11)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(64, 31, 64, 84)
    painter.drawLine(42, 64, 64, 86)
    painter.drawLine(86, 64, 64, 86)
    painter.drawLine(36, 100, 92, 100)
    painter.end()
    return QIcon(pix)


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.HLine)
    return line


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.service: GarminService | None = None
        self.login_worker: LoginWorker | None = None
        self.export_worker: ExportWorker | None = None
        self._logging_in = False
        self._exporting = False
        self._startup_login = False
        self._mfa_visible = False
        self._closing = False
        self.last_export_dir: Path | None = None
        self.settings = QSettings("Ducc", "GarminDataExporter")

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(make_app_icon())
        self.resize(1060, 860)
        self.setMinimumSize(900, 680)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1060, max(900, available.width() - 48)),
                min(860, max(680, available.height() - 48)),
            )
        self.setStyleSheet(STYLE_SHEET)

        self._build_ui()
        self._apply_config()
        self._wire_signals()
        self._restore_geometry()
        self._refresh_controls()
        self._update_session_hint()
        QTimer.singleShot(0, self._start_saved_session_login)
        self._append_log(
            f"{APP_TITLE} v{APP_VERSION} 已启动。数据仅保存在本机。"
        )

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 18, 24, 16)
        outer.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel(APP_TITLE)
        title.setObjectName("Title")
        subtitle = QLabel(
            "Garmin Connect · 按日期批量导出活动与每日健康数据，支持中国区 / 国际区"
        )
        subtitle.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.status_chip = QLabel("未登录")
        self.status_chip.setAlignment(Qt.AlignCenter)
        self._set_status_chip("未登录", "idle")
        header.addWidget(self.status_chip)
        outer.addLayout(header)

        # Main cards, scrollable on small screens
        body_widget = QWidget()
        body_widget.setObjectName("Body")
        body = QHBoxLayout(body_widget)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        body.addWidget(self._build_account_card(), 0)
        body.addWidget(self._build_export_card(), 1)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body_widget)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll, 1)

        # Log card
        outer.addWidget(self._build_log_card(), 0)

    def _build_account_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(350)
        card.setMaximumWidth(410)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("1. 连接账号")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        layout.addWidget(_field_label("服务器"))
        self.region_combo = QComboBox()
        self.region_combo.addItem("中国区  ·  connect.garmin.cn", REGION_CN)
        self.region_combo.addItem("国际区  ·  connect.garmin.com", REGION_GLOBAL)
        layout.addWidget(self.region_combo)

        layout.addWidget(_field_label("Garmin 账号邮箱"))
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("name@example.com")
        self.email_edit.setClearButtonEnabled(True)
        layout.addWidget(self.email_edit)

        layout.addWidget(_field_label("密码"))
        password_row = QHBoxLayout()
        password_row.setSpacing(6)
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("登录密码（不会保存）")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.show_password_btn = QPushButton("显示")
        self.show_password_btn.setObjectName("Mini")
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.setFixedWidth(52)
        password_row.addWidget(self.password_edit, 1)
        password_row.addWidget(self.show_password_btn)
        layout.addLayout(password_row)

        self.login_btn = QPushButton("登录 Garmin")
        self.login_btn.setObjectName("Primary")
        self.login_btn.setMinimumHeight(38)
        layout.addWidget(self.login_btn)

        self.mfa_frame = QFrame()
        self.mfa_frame.setObjectName("MfaCard")
        mfa_layout = QVBoxLayout(self.mfa_frame)
        mfa_layout.setContentsMargins(12, 10, 12, 10)
        mfa_layout.setSpacing(7)
        self.mfa_hint = QLabel("请输入两步验证码")
        self.mfa_hint.setWordWrap(True)
        self.mfa_hint.setObjectName("Hint")
        mfa_layout.addWidget(self.mfa_hint)
        mfa_row = QHBoxLayout()
        mfa_row.setSpacing(6)
        self.mfa_edit = QLineEdit()
        self.mfa_edit.setPlaceholderText("验证码")
        self.mfa_edit.setMaxLength(12)
        self.mfa_btn = QPushButton("验证")
        self.mfa_btn.setObjectName("Mini")
        self.mfa_cancel_btn = QPushButton("取消")
        self.mfa_cancel_btn.setObjectName("Mini")
        mfa_row.addWidget(self.mfa_edit, 1)
        mfa_row.addWidget(self.mfa_btn)
        mfa_row.addWidget(self.mfa_cancel_btn)
        mfa_layout.addLayout(mfa_row)
        self.mfa_frame.hide()
        layout.addWidget(self.mfa_frame)

        self.session_hint = QLabel("")
        self.session_hint.setObjectName("Hint")
        self.session_hint.setWordWrap(True)
        layout.addWidget(self.session_hint)

        self.clear_session_btn = QPushButton("清除本机保存的会话")
        self.clear_session_btn.setObjectName("Link")
        layout.addWidget(self.clear_session_btn)
        layout.addStretch(1)

        note = QLabel(
            "账号密码仅用于本次登录，不会写入磁盘；登录成功后保存的会话令牌"
            "位于本机用户目录，并限制了文件权限。"
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return card

    def _build_export_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("2. 选择导出范围")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        dates = QHBoxLayout()
        dates.setSpacing(10)
        start_box = QVBoxLayout()
        start_box.setSpacing(4)
        start_box.addWidget(_field_label("开始日期"))
        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_edit.setMinimumDate(QDate(2000, 1, 1))
        self.start_edit.setMaximumDate(QDate.currentDate())
        start_box.addWidget(self.start_edit)
        end_box = QVBoxLayout()
        end_box.setSpacing(4)
        end_box.addWidget(_field_label("结束日期"))
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_edit.setMinimumDate(QDate(2000, 1, 1))
        self.end_edit.setMaximumDate(QDate.currentDate())
        end_box.addWidget(self.end_edit)
        dates.addLayout(start_box, 1)
        dates.addLayout(end_box, 1)
        layout.addLayout(dates)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        self.quick_buttons: list[QPushButton] = []
        for text, days in (("最近 7 天", 7), ("最近 30 天", 30), ("最近 90 天", 90)):
            btn = QPushButton(text)
            btn.setObjectName("Mini")
            btn.clicked.connect(lambda _checked=False, d=days: self._set_quick_range(d))
            quick.addWidget(btn)
            self.quick_buttons.append(btn)
        this_year = QPushButton("今年")
        this_year.setObjectName("Mini")
        this_year.clicked.connect(self._set_this_year)
        quick.addWidget(this_year)
        self.quick_buttons.append(this_year)
        quick.addStretch(1)
        layout.addLayout(quick)

        layout.addWidget(_field_label("保存到"))
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        self.export_dir_edit = QLineEdit()
        self.export_dir_edit.setReadOnly(True)
        self.browse_btn = QPushButton("选择…")
        self.browse_btn.setObjectName("Mini")
        out_row.addWidget(self.export_dir_edit, 1)
        out_row.addWidget(self.browse_btn)
        layout.addLayout(out_row)

        layout.addWidget(_divider())
        content_title = QLabel("3. 导出内容")
        content_title.setObjectName("SectionTitle")
        layout.addWidget(content_title)

        self.cb_activities = QCheckBox("活动数据（列表 + 详情 + FIT 原始文件）")
        layout.addWidget(self.cb_activities)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)
        self.health_checks: dict[str, QCheckBox] = {}
        for index, key in enumerate(HEALTH_KEYS):
            checkbox = QCheckBox(HEALTH_LABELS[key])
            self.health_checks[key] = checkbox
            grid.addWidget(checkbox, index // 3, index % 3)
        layout.addLayout(grid)

        options_row = QHBoxLayout()
        self.cb_skip = QCheckBox("跳过已存在文件（断点续传）")
        self.cb_skip.setChecked(True)
        options_row.addWidget(self.cb_skip)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        hint = QLabel(
            "每日健康数据按天保存为 JSON；活动会保存概要、详情与 FIT。"
            "日期较长时请求次数较多，请耐心等待。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.export_btn = QPushButton("开始导出")
        self.export_btn.setObjectName("Primary")
        self.export_btn.setMinimumHeight(42)
        self.cancel_btn = QPushButton("取消导出")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.setMinimumHeight(42)
        self.cancel_btn.hide()
        self.open_folder_btn = QPushButton("打开导出目录")
        self.open_folder_btn.setMinimumHeight(42)
        self.open_folder_btn.setEnabled(False)
        buttons.addWidget(self.export_btn, 2)
        buttons.addWidget(self.cancel_btn, 1)
        buttons.addWidget(self.open_folder_btn, 1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return card

    def _build_log_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setFixedHeight(168)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.progress_label = QLabel("就绪")
        self.progress_label.setObjectName("StatusText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        row.addWidget(self.progress_label, 1)
        row.addWidget(self.progress_bar, 2)
        layout.addLayout(row)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("Log")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(3000)
        self.log_edit.setMinimumHeight(70)
        self.log_edit.setPlaceholderText("日志会显示在这里…")
        layout.addWidget(self.log_edit, 1)
        return card

    def _wire_signals(self) -> None:
        self.region_combo.currentIndexChanged.connect(self._on_region_changed)
        self.email_edit.textChanged.connect(self._on_email_changed)
        self.show_password_btn.toggled.connect(self._toggle_password)
        self.login_btn.clicked.connect(self._on_login_clicked)
        self.clear_session_btn.clicked.connect(self._clear_session)
        self.mfa_btn.clicked.connect(self._submit_mfa)
        self.mfa_cancel_btn.clicked.connect(self._cancel_mfa)
        self.mfa_edit.returnPressed.connect(self._submit_mfa)
        self.browse_btn.clicked.connect(self._choose_export_dir)
        self.export_btn.clicked.connect(self._start_export)
        self.cancel_btn.clicked.connect(self._cancel_export)
        self.open_folder_btn.clicked.connect(self._open_export_dir)
        self.cb_activities.toggled.connect(self._refresh_controls)
        self.cb_skip.toggled.connect(self._save_config)
        for checkbox in self.health_checks.values():
            checkbox.toggled.connect(self._refresh_controls)
        self.start_edit.dateChanged.connect(self._save_config)
        self.end_edit.dateChanged.connect(self._save_config)

    # ------------------------------------------------------------- config/UI
    def _apply_config(self) -> None:
        region = self.config.get("region", REGION_CN)
        index = self.region_combo.findData(region)
        self.region_combo.setCurrentIndex(max(0, index))
        self.email_edit.setText(str(self.config.get("email", "")))

        today = QDate.currentDate()
        end = today
        start = today.addDays(-6)
        self.start_edit.setDate(start)
        self.end_edit.setDate(end)

        export_dir = self.config.get("export_dir") or str(default_export_dir())
        self.export_dir_edit.setText(export_dir)

        self.cb_activities.setChecked(bool(self.config.get("export_activities", True)))
        self.cb_skip.setChecked(bool(self.config.get("skip_existing", True)))
        health = self.config.get("health", {})
        for key, checkbox in self.health_checks.items():
            checkbox.setChecked(bool(health.get(key, True)))

    def _config_from_ui(self) -> dict[str, Any]:
        return {
            "region": self.region_combo.currentData() or REGION_CN,
            "email": self.email_edit.text().strip(),
            "export_dir": self.export_dir_edit.text().strip(),
            "skip_existing": self.cb_skip.isChecked(),
            "export_activities": self.cb_activities.isChecked(),
            "health": {
                key: checkbox.isChecked()
                for key, checkbox in self.health_checks.items()
            },
        }

    def _save_config(self) -> None:
        self.config = self._config_from_ui()
        save_config(self.config)

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _set_quick_range(self, days: int) -> None:
        today = QDate.currentDate()
        self.end_edit.setDate(today)
        self.start_edit.setDate(today.addDays(-(days - 1)))
        self._save_config()

    def _set_this_year(self) -> None:
        today = QDate.currentDate()
        self.end_edit.setDate(today)
        self.start_edit.setDate(QDate(today.year(), 1, 1))
        self._save_config()

    def _choose_export_dir(self) -> None:
        initial = self.export_dir_edit.text().strip() or str(default_export_dir())
        chosen = QFileDialog.getExistingDirectory(
            self, "选择导出保存目录", initial, QFileDialog.ShowDirsOnly
        )
        if chosen:
            self.export_dir_edit.setText(chosen)
            self._save_config()

    def _toggle_password(self, checked: bool) -> None:
        self.password_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.show_password_btn.setText("隐藏" if checked else "显示")

    # --------------------------------------------------------------- identity
    def _current_region(self) -> str:
        return str(self.region_combo.currentData() or REGION_CN)

    def _current_email(self) -> str:
        return self.email_edit.text().strip()

    def _set_status_chip(self, text: str, state: str) -> None:
        colors = {
            "idle": ("#EEF2F7", "#5A6B82"),
            "ok": ("#E7F6EF", SUCCESS),
            "busy": ("#EAF2FF", PRIMARY),
            "warn": ("#FFF4E5", "#A35D00"),
            "error": ("#FDEDEC", "#B03A2E"),
        }
        bg, fg = colors.get(state, colors["idle"])
        self.status_chip.setText(text)
        self.status_chip.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 11px;"
            "padding: 5px 12px; font-size: 12px; font-weight: 600;"
        )

    def _update_session_hint(self) -> None:
        email = self._current_email()
        region = self._current_region()
        if self.service and self.service.region == region:
            if self.service.email.casefold() == email.casefold():
                self.session_hint.setText(
                    f"已登录：{self.service.display_name}。会话会自动保存在本机。"
                )
                return
        if not email:
            self.session_hint.setText("请输入账号邮箱。登录成功后会保存会话，下次通常可免密登录。")
            return
        probe = GarminService(email, "", region)
        if probe.has_matching_session():
            self.session_hint.setText(
                f"检测到 {REGION_LABELS[region]} 已保存会话，可留空密码直接登录。"
            )
        elif probe.token_file.exists():
            self.session_hint.setText(
                "该区服保存了其他账号的会话；当前邮箱将重新进行登录验证。"
            )
        else:
            self.session_hint.setText(
                "登录成功后会话会保存在本机，下次通常无需再次输入密码或验证码。"
            )

    def _on_region_changed(self) -> None:
        if self.service and self.service.region != self._current_region():
            self._invalidate_login("服务器已更改，请重新登录。")
        self._update_session_hint()
        self._save_config()

    def _on_email_changed(self) -> None:
        if self.service and self.service.email.casefold() != self._current_email().casefold():
            self._invalidate_login("账号已更改，请重新登录。")
        self._update_session_hint()
        self._save_config()

    def _invalidate_login(self, message: str) -> None:
        self.service = None
        self._mfa_visible = False
        self.mfa_frame.hide()
        self.progress_label.setText(message)
        self._set_status_chip("未登录", "idle")
        self._append_log(message)
        self._refresh_controls()

    # ------------------------------------------------------------- controls
    def _selected_health(self) -> tuple[str, ...]:
        return tuple(
            key for key in HEALTH_KEYS if self.health_checks[key].isChecked()
        )

    def _refresh_controls(self) -> None:
        idle = (
            not self._logging_in
            and not self._exporting
            and not self._closing
            and self.login_worker is None
        )
        for widget in (
            self.region_combo,
            self.email_edit,
            self.password_edit,
            self.show_password_btn,
            self.login_btn,
            self.clear_session_btn,
            self.start_edit,
            self.end_edit,
            self.browse_btn,
            self.cb_activities,
            self.cb_skip,
            *self.quick_buttons,
            *self.health_checks.values(),
        ):
            widget.setEnabled(idle)

        has_content = self.cb_activities.isChecked() or bool(self._selected_health())
        self.export_btn.setEnabled(
            idle and self.service is not None and has_content
        )
        self.export_btn.setText("正在导出…" if self._exporting else "开始导出")
        self.cancel_btn.setVisible(self._exporting)
        self.cancel_btn.setEnabled(self._exporting and not self._closing)
        self.open_folder_btn.setEnabled(
            idle and self.last_export_dir is not None and self.last_export_dir.exists()
        )
        if self._logging_in:
            self.login_btn.setText("正在登录…")
        elif self.service is not None:
            self.login_btn.setText("重新登录")
        else:
            self.login_btn.setText("登录 Garmin")
        self.mfa_frame.setVisible(self._mfa_visible)
        self._update_login_button_style()

    def _update_login_button_style(self) -> None:
        self.login_btn.setObjectName("Primary")
        self.login_btn.style().unpolish(self.login_btn)
        self.login_btn.style().polish(self.login_btn)

    # ---------------------------------------------------------------- login
    def _start_saved_session_login(self) -> None:
        if self._closing or self._logging_in or self._exporting:
            return
        saved = find_latest_saved_session()
        if saved is None:
            return
        region, email = saved
        self.region_combo.setCurrentIndex(max(0, self.region_combo.findData(region)))
        self.email_edit.setText(email)
        probe = GarminService(email, "", region)
        if not probe.has_matching_session():
            return
        self._begin_login(auto=True)

    def _begin_login(self, *, auto: bool = False) -> None:
        if self._logging_in or self._exporting or self.login_worker is not None:
            return
        email = self._current_email()
        region = self._current_region()
        password = "" if auto else self.password_edit.text()
        if not email:
            if auto:
                return
            QMessageBox.warning(self, "需要账号", "请输入 Garmin 账号邮箱。")
            self.email_edit.setFocus()
            return

        probe = GarminService(email, "", region)
        has_session = probe.has_matching_session()
        if not password and not has_session:
            if auto:
                return
            QMessageBox.warning(
                self,
                "需要密码",
                "没有找到该账号的已保存会话，请输入密码后再登录。",
            )
            self.password_edit.setFocus()
            return

        self._save_config()
        self._startup_login = auto
        self._mfa_visible = False
        self.mfa_frame.hide()
        self._logging_in = True
        self._set_status_chip("正在恢复会话" if auto else "正在登录", "busy")
        self.progress_label.setText("正在验证已保存会话…" if auto else "正在连接 Garmin…")
        self._refresh_controls()
        self._append_log(
            f"使用 {REGION_LABELS[region]} 登录 {email}"
            + ("（自动恢复已保存会话）" if auto else "（使用已保存会话）" if has_session else "")
        )

        worker = LoginWorker(email, password, region, self)
        worker.log.connect(self._append_log)
        worker.mfa_required.connect(self._on_mfa_required)
        worker.succeeded.connect(self._on_login_succeeded)
        worker.failed.connect(self._on_login_failed)
        worker.finished.connect(self._on_login_worker_finished)
        self.login_worker = worker
        worker.start()

    def _on_login_clicked(self) -> None:
        self._begin_login(auto=False)

    def _on_mfa_required(self, attempt: int, hint: str) -> None:
        if self._closing:
            return
        self._mfa_visible = True
        self.mfa_hint.setText(hint)
        self.mfa_edit.clear()
        self.mfa_btn.setEnabled(True)
        self.progress_label.setText("等待两步验证码…")
        self._set_status_chip("需要验证", "warn")
        self._refresh_controls()
        self.mfa_edit.setFocus()

    def _submit_mfa(self) -> None:
        if not self.login_worker or not self._mfa_visible:
            return
        code = self.mfa_edit.text().strip()
        if not code:
            self.mfa_edit.setFocus()
            return
        self.login_worker.provide_mfa(code)
        self._mfa_visible = False
        self.mfa_frame.hide()
        self.mfa_btn.setEnabled(False)
        self.progress_label.setText("正在验证验证码…")
        self._refresh_controls()

    def _cancel_mfa(self) -> None:
        if self.login_worker:
            self.login_worker.cancel()
        self._mfa_visible = False
        self.mfa_frame.hide()
        self.progress_label.setText("正在取消登录…")
        self._refresh_controls()

    def _on_login_succeeded(self, service: GarminService) -> None:
        if self._closing:
            return
        self.service = service
        self._logging_in = False
        self._startup_login = False
        self._mfa_visible = False
        self.password_edit.clear()
        self.show_password_btn.setChecked(False)
        self._set_status_chip(f"已登录 · {service.region_label}", "ok")
        self.progress_label.setText(f"已登录：{service.display_name}")
        self._append_log(f"会话已保存到 {service.session_directory}")
        self._update_session_hint()
        self._refresh_controls()

    def _on_login_failed(self, message: str) -> None:
        if self._closing:
            return
        was_startup_login = self._startup_login
        self._logging_in = False
        self._startup_login = False
        self._mfa_visible = False
        self.mfa_frame.hide()
        self.service = None
        self._set_status_chip("会话恢复失败" if was_startup_login else "登录失败", "warn" if was_startup_login else "error")
        self.progress_label.setText(
            "自动恢复失败，请输入密码后点击“登录 Garmin”。"
            if was_startup_login
            else message
        )
        self._append_log(
            f"自动恢复失败：{message}。请输入密码后手动登录。"
            if was_startup_login
            else f"登录失败：{message}"
        )
        self._update_session_hint()
        self._refresh_controls()
        if was_startup_login:
            return
        if "取消" in message:
            QMessageBox.information(self, "登录已取消", message)
        else:
            QMessageBox.warning(self, "登录失败", message)

    def _on_login_worker_finished(self) -> None:
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        if worker is self.login_worker:
            self.login_worker = None
            self._refresh_controls()

    def _clear_session(self) -> None:
        if self._logging_in or self._exporting:
            return
        region = self._current_region()
        email = self._current_email()
        answer = QMessageBox.question(
            self,
            "清除保存的会话",
            f"确定要清除 {REGION_LABELS[region]} 账号"
            f"{('（' + email + '）') if email else ''}保存在本机的登录会话吗？\n"
            "清除后下次需要重新输入密码和验证码。",
        )
        if answer != QMessageBox.Yes:
            return
        probe = GarminService(email, "", region)
        probe.clear_saved_session()
        self.service = None
        self._set_status_chip("未登录", "idle")
        self.progress_label.setText("已清除本机会话")
        self._append_log("已清除本机保存的 Garmin 会话。")
        self._update_session_hint()
        self._refresh_controls()

    # ---------------------------------------------------------------- export
    def _start_export(self) -> None:
        if self._exporting or self._logging_in:
            return
        if self.service is None:
            QMessageBox.warning(self, "尚未登录", "请先登录 Garmin 账号。")
            return
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        if start > end:
            QMessageBox.warning(self, "日期范围有误", "开始日期不能晚于结束日期。")
            return
        health = self._selected_health()
        activities = self.cb_activities.isChecked()
        if not health and not activities:
            QMessageBox.warning(self, "未选择内容", "请至少选择一项导出内容。")
            return

        base = Path(self.export_dir_edit.text().strip() or str(default_export_dir()))
        base = base.expanduser()
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "目录不可用", f"无法创建导出目录：\n{exc}")
            return
        if not base.is_dir():
            QMessageBox.critical(self, "目录不可用", f"导出路径不是文件夹：\n{base}")
            return

        days = (end - start).days + 1
        if days > 90:
            health_requests = days * len(health)
            answer = QMessageBox.question(
                self,
                "确认导出范围",
                f"将导出 {days} 天数据（{start} 至 {end}）。\n"
                f"仅健康数据就至少约 {health_requests} 次网络请求，"
                "活动还会额外请求列表、详情和 FIT。\n"
                "这可能需要较长时间并可能触发 Garmin 频率限制，是否继续？",
            )
            if answer != QMessageBox.Yes:
                return

        if self.cb_skip.isChecked():
            # Stable folder name so a later run of the same range can resume.
            target = base / f"garmin_export_{start}_{end}"
        else:
            stamp = timestamp_slug()
            target = base / f"garmin_export_{start}_{end}_{stamp}"
            suffix = 2
            while target.exists():
                target = base / f"garmin_export_{start}_{end}_{stamp}_{suffix}"
                suffix += 1

        options = ExportOptions(
            start=start,
            end=end,
            activities=activities,
            health=health,
            skip_existing=self.cb_skip.isChecked(),
            request_delay=0.35,
        )
        self._save_config()
        self._exporting = True
        self._set_status_chip("正在导出", "busy")
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText("准备导出…")
        self._append_log("")
        self._append_log(
            f"开始导出 {start} 至 {end}（{days} 天），保存到 {target}"
        )
        self._refresh_controls()

        worker = ExportWorker(self.service, options, target, self)
        worker.progress.connect(self._on_export_progress)
        worker.log.connect(self._append_log)
        worker.finished_result.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(self._on_export_worker_finished)
        self.export_worker = worker
        worker.start()

    def _on_export_progress(
        self, current: object, total: object, message: str
    ) -> None:
        if isinstance(total, int) and total > 0:
            self.progress_bar.setRange(0, total)
            if isinstance(current, int):
                self.progress_bar.setValue(min(max(current, 0), total))
                self.progress_label.setText(f"{message}  ({current}/{total})")
            else:
                self.progress_label.setText(message)
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(message)

    def _cancel_export(self) -> None:
        if not self.export_worker or not self._exporting:
            return
        self.export_worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.progress_label.setText("正在取消，请稍候…")
        self._append_log("正在取消导出…")

    def _on_export_finished(self, result: ExportResult) -> None:
        self._exporting = False
        self.last_export_dir = result.directory
        counts = result.manifest.get("counts", {})
        activities = counts.get("activities", {})
        health = counts.get("health", {})
        errors = result.manifest.get("errors", [])

        if result.status == "cancelled":
            self.progress_label.setText("导出已取消（已完成的文件保留）")
            self._set_status_chip("已取消", "warn")
            self._append_log(f"导出已取消：{result.directory}")
            self._refresh_controls()
            QMessageBox.information(
                self,
                "已取消",
                f"导出已取消，已完成的文件保留在：\n{result.directory}",
            )
            return

        summary = (
            f"活动：{activities.get('found', 0)} 个，FIT：{activities.get('fit', 0)} 个\n"
            f"健康数据：写入 {health.get('written', 0)} 个文件"
            f"（其中无数据 {health.get('empty', 0)} 个）\n"
            f"错误：{len(errors)} 条"
        )
        self.progress_bar.setRange(0, self.progress_bar.maximum() or 1)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self._append_log(
            f"导出结束：{result.status}；活动 {activities.get('found', 0)} 个，"
            f"FIT {activities.get('fit', 0)} 个，健康文件 {health.get('written', 0)} 个，"
            f"错误 {len(errors)} 条。"
        )
        if result.status == "success":
            self._set_status_chip("导出完成", "ok")
            self.progress_label.setText("导出完成")
            self._refresh_controls()
            QMessageBox.information(
                self,
                "导出完成",
                f"数据已导出到：\n{result.directory}\n\n{summary}",
            )
        elif result.status == "failed":
            self._set_status_chip("导出失败", "error")
            self.progress_label.setText("导出失败，请查看日志")
            self._refresh_controls()
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出过程中出现错误：\n{result.directory}\n\n{summary}\n"
                "详情请查看 manifest.json 和日志。",
            )
        else:
            self._set_status_chip("部分完成", "warn")
            self.progress_label.setText("导出完成，但存在错误")
            self._refresh_controls()
            QMessageBox.warning(
                self,
                "导出完成（有错误）",
                f"数据已导出到：\n{result.directory}\n\n{summary}\n"
                "详情请查看 manifest.json 和日志。",
            )

    def _on_export_failed(self, message: str) -> None:
        self._exporting = False
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label.setText(message)
        self._append_log(f"导出失败：{message}")
        if "会话已失效" in message or "重新登录" in message:
            self._invalidate_login("登录会话已失效，请重新登录。")
        self._set_status_chip("导出失败", "error")
        self._refresh_controls()
        QMessageBox.critical(self, "导出失败", message)

    def _on_export_worker_finished(self) -> None:
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        if worker is self.export_worker:
            self.export_worker = None

    def _open_export_dir(self) -> None:
        if self.last_export_dir and self.last_export_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export_dir)))

    # ------------------------------------------------------------------ misc
    def _append_log(self, message: str) -> None:
        from datetime import datetime

        cleaned = str(message).rstrip()
        if not cleaned:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{stamp}] {cleaned}")
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        LOGGER.info("%s", cleaned)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        busy = self._logging_in or self._exporting or self.login_worker is not None
        if busy:
            answer = QMessageBox.question(
                self,
                "任务仍在进行",
                "登录或导出尚未结束，确定要退出吗？\n未完成的导出会保留已写入的文件。",
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return

        self._closing = True
        self._save_config()
        self.settings.setValue("window/geometry", self.saveGeometry())

        if self.login_worker is not None:
            self.login_worker.cancel()
        if self.export_worker is not None:
            self.export_worker.cancel()
        for worker in (self.login_worker, self.export_worker):
            if worker is not None and worker.isRunning():
                if not worker.wait(8000):
                    LOGGER.warning(
                        "Worker still running on exit; terminating %s", type(worker).__name__
                    )
                    worker.terminate()
                    if not worker.wait(3000):
                        LOGGER.error(
                            "Worker %s did not stop after terminate()",
                            type(worker).__name__,
                        )
                # All export files are written atomically, so even an abrupt
                # stop cannot leave a truncated file that skip-existing trusts.
        event.accept()
