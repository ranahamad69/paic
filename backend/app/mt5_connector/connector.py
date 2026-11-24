"""MT5 connection lifecycle: initialise, health-check, serialised use, throttled reconnect, shutdown.

All terminal calls go through :meth:`MT5Connector.run`, which holds a re-entrant
lock so the (not thread-safe) MT5 IPC channel is never used concurrently, and
which fails closed with ``BrokerUnavailableError`` when the terminal or broker
connection is not usable.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from app.core.errors import AppError, BrokerUnavailableError
from app.core.timeutil import utc_now
from app.mt5_connector.adapter import BrokerAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ConnectionState:
    initialized: bool = False
    package_available: bool = True
    broker_connected: bool = False
    last_error_code: int | None = None
    last_error_message: str | None = None
    last_check_utc: datetime | None = None
    last_connect_attempt_utc: datetime | None = None
    connect_attempts: int = 0
    terminal: dict[str, Any] = field(default_factory=dict)
    version: str | None = None


class MT5Connector:
    def __init__(
        self,
        adapter: BrokerAdapter,
        reconnect_interval_seconds: float = 15.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.adapter = adapter
        self._reconnect_interval = reconnect_interval_seconds
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._last_attempt: float | None = None
        self.state = ConnectionState()

    # --- lifecycle -----------------------------------------------------------
    def connect(self) -> bool:
        """Attempt to initialise the terminal. Never raises; returns success."""
        with self._lock:
            self._last_attempt = self._monotonic()
            self.state.last_connect_attempt_utc = utc_now()
            self.state.connect_attempts += 1
            try:
                ok = self.adapter.initialize()
            except BrokerUnavailableError as exc:
                self.state.package_available = False
                self._mark_down(-1, exc.message)
                logger.warning("MT5 unavailable: %s", exc.message)
                return False
            except Exception as exc:  # noqa: BLE001 - adapter/IPC failure; log and fail closed
                logger.exception("MT5 initialise raised unexpectedly")
                self._mark_down(-1, f"{type(exc).__name__}: {exc}")
                return False
            if not ok:
                code, message = self.adapter.last_error()
                self._mark_down(code, message)
                logger.warning("MT5 initialise failed: [%s] %s", code, message)
                return False
            self.state.initialized = True
            self.state.package_available = True
            logger.info("MT5 terminal initialised (adapter=%s)", self.adapter.name)
            self._refresh_health()
            return True

    def shutdown(self) -> None:
        with self._lock:
            try:
                self.adapter.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must not crash app teardown
                logger.exception("Error during MT5 shutdown")
            self.state.initialized = False
            self.state.broker_connected = False
            logger.info("MT5 connector shut down")

    def health_check(self) -> ConnectionState:
        """Refresh state (reconnecting if due) and return it. Never raises."""
        with self._lock:
            if not self.state.initialized:
                self._maybe_reconnect()
            else:
                self._refresh_health()
            return self.state

    # --- serialised use ------------------------------------------------------
    def run(self, fn: Callable[[BrokerAdapter], T]) -> T:
        """Run ``fn(adapter)`` under the terminal lock after verifying readiness.

        Raises ``BrokerUnavailableError`` if the terminal is not initialised (and
        a throttled reconnect fails) or the broker connection is down.
        """
        with self._lock:
            if not self.state.initialized and not self._maybe_reconnect():
                raise BrokerUnavailableError(self._unavailable_message())
            if not self._refresh_health():
                raise BrokerUnavailableError(self._unavailable_message())
            try:
                return fn(self.adapter)
            except AppError:
                raise
            except Exception as exc:
                logger.exception("Broker call failed")
                self._mark_down(-1, f"{type(exc).__name__}: {exc}")
                raise BrokerUnavailableError("Broker call failed; connection marked down") from exc

    def last_error(self) -> tuple[int, str]:
        with self._lock:
            try:
                return self.adapter.last_error()
            except Exception:  # noqa: BLE001
                logger.exception("last_error() failed")
                return (-1, "unknown")

    # --- internals -----------------------------------------------------------
    def _maybe_reconnect(self) -> bool:
        if self._last_attempt is not None and (self._monotonic() - self._last_attempt < self._reconnect_interval):
            return False
        logger.info("Attempting MT5 reconnect")
        return self.connect()

    def _refresh_health(self) -> bool:
        """Check terminal + broker connection. Returns True if usable."""
        self.state.last_check_utc = utc_now()
        try:
            info = self.adapter.terminal_info()
        except Exception as exc:  # noqa: BLE001
            logger.exception("terminal_info() raised")
            self._mark_down(-1, f"{type(exc).__name__}: {exc}")
            return False
        if info is None:
            code, message = self.adapter.last_error()
            self._mark_down(code, message or "Terminal info unavailable")
            return False
        self.state.terminal = {
            "name": info.get("name"),
            "company": info.get("company"),
            "build": info.get("build"),
            "trade_allowed": info.get("trade_allowed"),
            "ping_ms": round(info["ping_last"] / 1000, 1) if info.get("ping_last") else None,
        }
        if self.state.version is None:
            try:
                v = self.adapter.version()
                self.state.version = ".".join(str(p) for p in v[:2]) if v else None
            except Exception:  # noqa: BLE001
                logger.exception("version() raised")
        self.state.broker_connected = bool(info.get("connected"))
        if not self.state.broker_connected:
            self.state.last_error_message = "Terminal is not connected to the broker trade server"
            return False
        self.state.last_error_code = None
        self.state.last_error_message = None
        return True

    def _mark_down(self, code: int, message: str) -> None:
        """Terminal/IPC unusable: drop the initialised flag so a throttled reconnect is tried."""
        self.state.initialized = False
        self.state.broker_connected = False
        self.state.last_error_code = code
        self.state.last_error_message = message

    def _unavailable_message(self) -> str:
        detail = self.state.last_error_message or "not connected"
        return f"MT5 broker connection unavailable: {detail}"
