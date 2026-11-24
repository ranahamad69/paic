"""Domain errors. Each maps to a structured JSON API error in ``app.main``."""

from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BrokerUnavailableError(AppError):
    """MT5 package missing, terminal not running, or not connected/authorised."""

    status_code = 503
    code = "broker_unavailable"


class BrokerDataError(AppError):
    """Broker returned no data or malformed data for a request."""

    status_code = 502
    code = "broker_data_error"


class SymbolNotFoundError(AppError):
    status_code = 404
    code = "symbol_not_found"


class SymbolAmbiguousError(AppError):
    status_code = 409
    code = "symbol_ambiguous"


class AuthNotConfiguredError(AppError):
    status_code = 503
    code = "auth_not_configured"
