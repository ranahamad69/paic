"""Phase 1 guard-rails: no order placement/modification/closure code and no write endpoints."""

import re
from pathlib import Path

from app.main import create_app
from tests.conftest import make_settings

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# MT5 functions/constants that place, check, modify or close orders.
FORBIDDEN = re.compile(r"\b(order_send|order_check|TRADE_ACTION_\w+|ORDER_TYPE_\w+|positions_close|Close)\s*\(?")


def test_no_order_functions_in_application_code():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(APP_DIR)}:{lineno}: {line.strip()}")
    assert offenders == [], "Order functionality is not allowed in Phase 1:\n" + "\n".join(offenders)


def test_api_exposes_only_get_routes():
    app = create_app(make_settings())
    methods = set()
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/"):
            methods |= set(route.methods)
    assert methods <= {"GET", "HEAD"}


def test_no_trade_like_paths():
    app = create_app(make_settings())
    paths = " ".join(getattr(r, "path", "") for r in app.routes).lower()
    for word in ("order", "trade", "execute", "approve", "position"):
        assert word not in paths


def test_no_secrets_committed():
    root = APP_DIR.parent.parent
    for name in (".env", "backend/.env"):
        assert not (root / name).exists() or name in (root / ".gitignore").read_text()
