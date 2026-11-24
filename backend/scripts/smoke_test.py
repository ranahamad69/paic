"""Manual read-only smoke test against a real MT5 terminal (run on the Windows host).

    cd backend
    python scripts/smoke_test.py

Reads configuration from backend/.env. Prints masked account metadata, symbol
mapping, a few candles per timeframe and the latest tick. Places no orders.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.security import mask_identifier  # noqa: E402
from app.market_data.timeframes import Timeframe  # noqa: E402
from app.services import build_services  # noqa: E402


def main() -> int:
    settings = get_settings()
    svc = build_services(settings)
    print(f"Adapter: {svc.connector.adapter.name}  (mock={svc.connector.adapter.is_mock})")
    if not svc.connector.connect():
        print(f"FAILED to connect: {svc.connector.state.last_error_message}")
        return 1
    try:
        state = svc.connector.state
        print(f"Terminal: {state.terminal}  version={state.version}  broker_connected={state.broker_connected}")
        acc = svc.connector.run(lambda a: a.account_info()) or {}
        mode = {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(acc.get("trade_mode"), "UNKNOWN")
        print(f"Account: login={mask_identifier(acc.get('login'))} type={mode} currency={acc.get('currency')}")
        if mode == "REAL":
            print("WARNING: connected to a REAL account. Phase 1 is read-only, but prefer a DEMO account.")

        mapping = svc.symbols.mapping()
        for pair, m in mapping.items():
            print(f"  {pair:7s} -> {m.broker_symbol or '-':14s} {m.status} ({m.source}) {m.candidates}")
        pair = next((p for p, m in mapping.items() if m.broker_symbol), None)
        if pair is None:
            print("No universe pair mapped; check SYMBOL_MAP_OVERRIDES")
            return 1

        for tf in Timeframe:
            series = svc.market.get_candles(pair, tf, 5)
            last = series.candles[-1]
            print(
                f"{pair} {tf}: {len(series.candles)} bars, valid={series.validation.is_valid}, "
                f"last open={last.open_time.isoformat()} closed={last.is_closed}"
            )
            for issue in series.validation.issues:
                print(f"    {issue.severity} {issue.code}: {issue.message}")
        tick = svc.market.get_tick(pair)
        print(
            f"Tick {pair}: bid={tick.bid} ask={tick.ask} spread_pts={tick.spread_points} "
            f"time={tick.time.isoformat()} age={tick.age_seconds}s stale={tick.is_stale} "
            f"clock_skew={tick.clock_skew_suspected}"
        )
        return 0
    finally:
        svc.connector.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
