"""Qt worker threads for login and export."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from PySide6.QtCore import QThread, Signal

from .exporter import ExportOptions, Exporter, ExportResult
from .garmin_service import (
    MFA_REQUIRED,
    GarminService,
    friendly_error,
)

MFA_TIMEOUT_SECONDS = 300
MFA_MAX_ATTEMPTS = 3


class LoginWorker(QThread):
    """Login without blocking the UI; waits asynchronously for an MFA code."""

    log = Signal(str)
    mfa_required = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self, email: str, password: str, region: str, parent: Any = None
    ) -> None:
        super().__init__(parent)
        self.email = email
        self.password = password
        self.region = region
        self._mfa_queue: queue.Queue[str | None] = queue.Queue()
        self._cancel = threading.Event()

    def provide_mfa(self, code: str) -> None:
        self._mfa_queue.put(code.strip())

    def cancel(self) -> None:
        self._cancel.set()
        self._mfa_queue.put(None)

    def _wait_for_mfa(self) -> str | None:
        deadline = time.monotonic() + MFA_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                return None
            try:
                code = self._mfa_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if code is None:
                return None
            if code:
                return code
        return None

    def _login_service(
        self, service: GarminService
    ) -> tuple[GarminService, str, Any]:
        use_session = service.has_matching_session()
        if use_session:
            self.log.emit("发现匹配的已保存会话，正在验证…")
        try:
            status, state = service.login(use_saved_session=use_session)
            return service, status, state
        except GarminConnectTooManyRequestsError:
            raise
        except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
            if not use_session:
                raise
            if not self.password:
                raise GarminConnectAuthenticationError(
                    "保存的会话已失效，请输入密码重新登录"
                ) from exc
            self.log.emit("已保存的会话不可用，改用账号密码重新登录…")
            fresh = GarminService(self.email, self.password, self.region)
            status, state = fresh.login(use_saved_session=False)
            return fresh, status, state

    def run(self) -> None:
        if not self.email:
            self.failed.emit("请输入 Garmin 账号邮箱。")
            return

        service = GarminService(self.email, self.password, self.region)
        self.log.emit(f"正在连接 {service.region_label} Garmin 服务器…")
        try:
            service, status, state = self._login_service(service)
            self.password = ""
        except GarminConnectTooManyRequestsError as exc:
            self.failed.emit(friendly_error(exc))
            return
        except GarminConnectAuthenticationError as exc:
            self.failed.emit(friendly_error(exc))
            return
        except GarminConnectConnectionError as exc:
            self.failed.emit(friendly_error(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(friendly_error(exc))
            return

        if status == MFA_REQUIRED:
            if self._cancel.is_set():
                self.failed.emit("已取消登录。")
                return
            self.log.emit("Garmin 要求两步验证，请查看邮箱或手机短信。")
            for attempt in range(1, MFA_MAX_ATTEMPTS + 1):
                if attempt == 1:
                    hint = "请输入 Garmin 发送的验证码。"
                else:
                    hint = f"验证码不正确，请重新输入（第 {attempt}/{MFA_MAX_ATTEMPTS} 次）。"
                self.mfa_required.emit(attempt, hint)
                code = self._wait_for_mfa()
                if code is None:
                    self.failed.emit("两步验证已取消或超时，请重新登录。")
                    return
                self.log.emit("正在验证两步验证码…")
                try:
                    service.resume_login(state, code)
                except GarminConnectTooManyRequestsError as exc:
                    self.failed.emit(friendly_error(exc))
                    return
                except GarminConnectAuthenticationError as exc:
                    if attempt < MFA_MAX_ATTEMPTS:
                        self.log.emit(f"验证码未通过：{exc}")
                        continue
                    self.failed.emit(friendly_error(exc))
                    return
                except GarminConnectConnectionError as exc:
                    self.failed.emit(friendly_error(exc))
                    return
                except Exception as exc:  # noqa: BLE001
                    self.failed.emit(friendly_error(exc))
                    return
                break

        self.log.emit(
            f"登录成功：{service.display_name}（{service.region_label}）"
        )
        self.succeeded.emit(service)


class ExportWorker(QThread):
    """Run the exporter on a background thread."""

    progress = Signal(object, object, str)
    log = Signal(str)
    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: GarminService,
        options: ExportOptions,
        target: Path,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.options = options
        self.target = target
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        exporter = Exporter(
            self.service.garmin_client,
            self.options,
            self.target,
            account={
                "email": self.service.email,
                "region": self.service.region,
                "region_label": self.service.region_label,
                "display_name": self.service.display_name,
            },
            progress=lambda current, total, message: self.progress.emit(
                current, total, message
            ),
            log=self.log.emit,
            cancel_event=self.cancel_event,
        )
        try:
            result: ExportResult = exporter.run()
        except GarminConnectAuthenticationError as exc:
            self.failed.emit(friendly_error(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(friendly_error(exc))
            return
        finally:
            self.service.persist_session()
        self.finished_result.emit(result)
