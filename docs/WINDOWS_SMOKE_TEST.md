# Windows MT5 smoke test (manual)

Phase 1 acceptance requires a manual check on a compatible Windows host. Use a **demo** account.

## Prerequisites

1. Windows 10/11 or Windows Server (64-bit) with the MT5 desktop terminal installed, logged in to a **demo** account, and connected (green bars bottom-right).
2. In the terminal, set Tools → Options → Expert Advisors → *Allow algorithmic trading*. Phase 1 places no trades, but some builds restrict API access without this setting.
3. 64-bit Python that has a `MetaTrader5` wheel available:
   ```powershell
   py -3.12 -m pip download MetaTrader5 --only-binary=:all: --no-deps -d $env:TEMP\mt5check
   ```
   If this fails, try another Python version (3.11 or 3.10) and record which one worked in the README.

## Steps

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-windows.txt -r requirements-dev.txt
copy .env.example .env
notepad .env
```

In `.env` set at minimum:
* `MT5_ADAPTER=mt5`
* `API_AUTH_TOKEN=<random token>`
* `MT5_SERVER_TIMEZONE=<broker server tz>` (check the broker's documentation; e.g. `UTC+2` in winter for many brokers)
* Optionally `MT5_TERMINAL_PATH`, `MT5_LOGIN`, `MT5_PASSWORD` and `MT5_SERVER`. Leave them empty to attach to the terminal's logged-in account.

Then run:

```powershell
.venv\Scripts\python scripts\smoke_test.py
set MT5_RUN_INTEGRATION=1
.venv\Scripts\python -m pytest -m windows_mt5 -v
.venv\Scripts\uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

In a second shell:

```powershell
$h = @{ Authorization = "Bearer <token>" }
irm http://127.0.0.1:8000/api/v1/ready
irm http://127.0.0.1:8000/api/v1/mt5/status -Headers $h
irm http://127.0.0.1:8000/api/v1/account -Headers $h
irm "http://127.0.0.1:8000/api/v1/symbols?universe_only=true" -Headers $h
irm "http://127.0.0.1:8000/api/v1/market/EURUSD/candles?timeframe=H4&count=10" -Headers $h
irm http://127.0.0.1:8000/api/v1/market/EURUSD/tick -Headers $h
```

## Pass criteria

- [ ] `smoke_test.py` reports `broker_connected=True` and `type=DEMO`.
- [ ] Account login is masked everywhere (console and API).
- [ ] The universe mapping shows each available pair `MAPPED`. Fix any `AMBIGUOUS` pairs with `SYMBOL_MAP_OVERRIDES`.
- [ ] D1, H4 and H1 candles return `validation.is_valid = true`, and the newest bar is `is_closed=false` while the market is open.
- [ ] During market hours the tick shows `clock_skew_suspected=false`, `is_stale=false` and an `age_seconds` of a few seconds.
  * A large negative age or `FUTURE_BAR` means `MT5_SERVER_TIMEZONE` is too small (it should be further east).
  * A consistent age of about N hours means it is off by N hours.
- [ ] Closing the terminal makes `/ready` return 503 and data endpoints return 503. Restarting the terminal makes it recover within `MT5_RECONNECT_INTERVAL_SECONDS`.
- [ ] The integration tests pass.

Record the date, broker, Python version, `MetaTrader5` version, terminal build and results in the PR or issue.
