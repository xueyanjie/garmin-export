"""Thin, GUI-friendly wrapper around :mod:`garminconnect`."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .paths import REGION_CN, REGION_GLOBAL, REGIONS, session_dir, write_json

LOGGER = logging.getLogger(__name__)

REGION_LABELS = {
    REGION_CN: "中国区",
    REGION_GLOBAL: "国际区",
}

MFA_REQUIRED = "needs_mfa"
LOGIN_OK = "ok"


def find_latest_saved_session() -> tuple[str, str] | None:
    """Return the region and email for the newest complete saved session."""
    candidates: list[tuple[datetime, str, str]] = []
    for region in REGIONS:
        probe = GarminService("", "", region)
        meta = probe.read_session_meta()
        if not probe.token_file.is_file() or not meta:
            continue
        if meta.get("region") != region:
            continue
        email = meta.get("email")
        if not isinstance(email, str) or not email.strip():
            continue

        saved_at = meta.get("saved_at")
        timestamp: datetime
        try:
            timestamp = datetime.fromisoformat(str(saved_at))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            try:
                timestamp = datetime.fromtimestamp(
                    probe.meta_file.stat().st_mtime, tz=timezone.utc
                )
            except OSError:
                continue
        candidates.append((timestamp, region, email.strip()))

    if not candidates:
        return None
    _, region, email = max(candidates, key=lambda item: item[0])
    return region, email


class GarminService:
    """Owns one authenticated Garmin client and its local session."""

    def __init__(self, email: str, password: str, region: str) -> None:
        if region not in REGIONS:
            raise ValueError(f"Unknown region: {region}")
        self.email = email.strip()
        self.password = password
        self.region = region
        self.is_cn = region == REGION_CN
        self.garmin: Garmin | None = None

    # ------------------------------------------------------------------ session
    @property
    def session_directory(self) -> Path:
        return session_dir(self.region)

    @property
    def token_file(self) -> Path:
        return self.session_directory / "garmin_tokens.json"

    @property
    def meta_file(self) -> Path:
        return self.session_directory / "session.json"

    @property
    def region_label(self) -> str:
        return REGION_LABELS[self.region]

    def read_session_meta(self) -> dict[str, Any] | None:
        try:
            meta = json.loads(self.meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return meta if isinstance(meta, dict) else None

    def has_matching_session(self) -> bool:
        """True when a saved session belongs to this email and region."""
        if not self.token_file.is_file():
            return False
        meta = self.read_session_meta()
        if not meta or meta.get("region") != self.region:
            return False
        saved_email = meta.get("email")
        if not isinstance(saved_email, str):
            return False
        return saved_email.strip().casefold() == self.email.casefold()

    def clear_saved_session(self) -> None:
        for path in (self.token_file, self.meta_file):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove session file %s", path)
        try:
            self.session_directory.rmdir()
        except OSError:
            pass

    def _persist_session(self) -> None:
        if self.garmin is None:
            return
        directory = self.session_directory
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
        # Garmin.login() does this in the non-MFA path; setting it explicitly
        # also covers a login completed through resume_login().
        self.garmin.client._tokenstore_path = str(directory)  # noqa: SLF001
        self.garmin.client.dump(str(directory))  # noqa: SLF001
        write_json(
            self.meta_file,
            {
                "email": self.email,
                "region": self.region,
                "display_name": self.display_name,
                "full_name": self.full_name,
                "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            private=True,
        )

    # -------------------------------------------------------------------- login
    def login(self, *, use_saved_session: bool) -> tuple[str, Any]:
        """Start a login.

        Returns ``("ok", None)`` or ``("needs_mfa", client_state)``.  The
        caller must feed the state and the code to :meth:`resume_login`.
        """
        tokenstore = (
            str(self.session_directory)
            if use_saved_session and self.has_matching_session()
            else None
        )
        self.garmin = Garmin(
            email=self.email,
            password=self.password,
            is_cn=self.is_cn,
            return_on_mfa=True,
            verify_login=True,
        )
        status, state = self.garmin.login(tokenstore)
        if status == MFA_REQUIRED:
            self.password = ""
            self.garmin.password = None
            return MFA_REQUIRED, state
        # With return_on_mfa=True the library returns immediately after the
        # credential check: it has not loaded the profile and has not cleared
        # the plaintext password yet. Finish both here.
        self.garmin.password = None
        self.password = ""
        if not self.garmin.display_name and not self.garmin.full_name:
            try:
                self.garmin._load_profile_and_settings()  # noqa: SLF001
            except Exception:  # noqa: BLE001 - display metadata only
                LOGGER.debug("Could not load Garmin profile after login", exc_info=True)
        self._persist_session()
        return LOGIN_OK, None

    def resume_login(self, client_state: Any, mfa_code: str) -> None:
        if self.garmin is None:
            raise GarminConnectAuthenticationError("登录会话已丢失，请重新登录")
        self.garmin.resume_login(client_state, mfa_code)
        # Garmin.login() only clears the password in its non-MFA path.
        self.password = ""
        if self.garmin is not None:
            self.garmin.password = None
        self._persist_session()

    def persist_session(self) -> None:
        """Save refreshed tokens after a long export, if still authenticated."""
        if self.garmin is not None and self.garmin.client.is_authenticated:
            try:
                self._persist_session()
            except Exception:  # noqa: BLE001 - never fail an export over this
                LOGGER.debug("Could not refresh saved session tokens", exc_info=True)

    # ----------------------------------------------------------------- details
    @property
    def display_name(self) -> str:
        if self.garmin and self.garmin.full_name:
            return str(self.garmin.full_name)
        if self.garmin and self.garmin.display_name:
            return str(self.garmin.display_name)
        return self.email

    @property
    def full_name(self) -> str:
        return str(self.garmin.full_name) if self.garmin and self.garmin.full_name else ""

    @property
    def garmin_client(self) -> Garmin:
        if self.garmin is None:
            raise RuntimeError("尚未登录 Garmin")
        return self.garmin


def friendly_error(exc: BaseException) -> str:
    """Turn library/network errors into actionable Chinese messages."""
    text = str(exc).strip()
    lowered = text.lower()

    if isinstance(exc, GarminConnectTooManyRequestsError) or "429" in lowered:
        return "请求过于频繁（HTTP 429）。请等待几分钟后重试，或在导出设置中缩小日期范围。"
    if "curl_cffi" in lowered:
        return (
            "登录所需的 curl_cffi 组件不可用。请删除项目中的 .venv 目录后重新启动，"
            "程序会自动重新安装依赖。"
        )
    if "cloudflare" in lowered or "403 forbidden" in lowered or "access denied" in lowered:
        return (
            "Garmin 的登录防护暂时拦截了请求（Cloudflare/403）。请稍后重试；"
            "如果仍失败，尝试切换网络（如手机热点）后再登录。"
        )
    if "username and password are required" in lowered:
        return "没有可用的已保存会话，请输入账号密码后登录。"
    if "保存的会话已失效" in text:
        return "保存的会话已失效，请输入密码重新登录。"
    if "mfa" in lowered or "verification code" in lowered:
        return "两步验证码不正确或已过期，请重新输入。"
    if isinstance(exc, GarminConnectAuthenticationError):
        if "invalid" in lowered or "credentials" in lowered:
            return "账号或密码不正确。中国区账号请确认选择的是“中国区”，并使用 connect.garmin.cn 的账号。"
        return f"Garmin 认证失败：{text or '请检查账号、密码与区服设置'}"
    if isinstance(exc, GarminConnectConnectionError):
        return (
            "无法连接 Garmin 服务器。请检查网络连接；中国区账号请确认未开启需要额外认证的代理。\n"
            f"详细信息：{text}"
        )
    if "timed out" in lowered or "timeout" in lowered:
        return "连接 Garmin 服务器超时，请检查网络后重试。"
    if len(text) > 700:
        text = text[:700] + "…"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
