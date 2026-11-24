# PAIC — AI Forex Swing Trading Platform

Semi-automated Forex swing-trading platform built on MetaTrader 5, Python/FastAPI, and (later) React and Claude.
The human stays the decision-maker. AI output is only advice, and risk and execution are governed by deterministic backend rules.

> **Current status: Phase 1 — read-only MT5 connectivity and market data.**
> No order placement, modification or closure code exists. A test (`tests/test_safety.py`) enforces this.

See [`CLAUDE.md`](CLAUDE.md) for the full specification and phased roadmap, [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design, and [`docs/WINDOWS_SMOKE_TEST.md`](docs/WINDOWS_SMOKE_TEST.md) for real-terminal verification.

## Repository layout

```
backend/
  app/
    core/            config, errors, auth/masking, UTC helpers, rate limiting
    mt5_connector/   adapter interface, real MT5 adapter, mock adapter, connection lifecycle
    symbol_manager/  symbol discovery, Forex filtering, broker-symbol mapping, contract specs
    market_data/     candles, ticks, UTC normalisation, validation, freshness
    api/v1/          read-only FastAPI routes
    main.py          app factory
  scripts/smoke_test.py   manual Windows/MT5 smoke test
  tests/                  pytest suite (mocked broker; Windows integration tests opt-in)
docs/
```

## Requirements

| Component | Where | Notes |
|---|---|---|
| Python ≥ 3.11 | any | The code is tested on 3.13 (Linux) with the mock adapter. |
| `MetaTrader5` package and MT5 terminal | **Windows only** | MetaQuotes ships Windows wheels only. Before choosing a Python version, check that a wheel exists for it (see below). Python 3.11 or 3.12 is the safest choice. |

The official package does **not** work in Linux containers. Run the API on the Windows PC/VPS that runs the terminal. Other services (dashboard, DB) can run elsewhere and connect over a private network.

## Setup — development (any OS, mock data)

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
cp .env.example .env                                  # then set MT5_ADAPTER=mock and API_AUTH_TOKEN
.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

The mock adapter serves **synthetic** data, and every response labels it `"data_source": "MOCK"`. To use it, set `MT5_ADAPTER=mock` explicitly. The default is `mt5`, so the app never shows fake data by accident.

## Setup — Windows with MT5

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\pip download MetaTrader5 --only-binary=:all: --no-deps -d $env:TEMP\mt5check   # confirm wheel exists
.venv\Scripts\pip install -r requirements-windows.txt
copy .env.example .env    # set API_AUTH_TOKEN, MT5_SERVER_TIMEZONE, optionally MT5_LOGIN/SERVER/PASSWORD (DEMO)
.venv\Scripts\python scripts\smoke_test.py
.venv\Scripts\uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest          # mocked; no MT5 or broker account needed
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Real-terminal integration tests are skipped by default. On Windows, run them with `set MT5_RUN_INTEGRATION=1` and then `pytest -m windows_mt5`.

## Configuration

All settings come from environment variables or `backend/.env`. See [`backend/.env.example`](backend/.env.example) for the full documented list. Never commit `.env` or put credentials in code or chat.

## API (Phase 1, read-only)

All routes are `GET`. Every route except `health` and `ready` requires `Authorization: Bearer <API_AUTH_TOKEN>`. If no token is configured, those routes return 503 (fail closed).

| Endpoint | Purpose |
|---|---|
| `/api/v1/health` | Liveness check. Never touches the broker. |
| `/api/v1/ready` | 200 when the broker connection is usable, otherwise 503. |
| `/api/v1/mt5/status` | Adapter, terminal, connection state and last error. |
| `/api/v1/account` | Masked account metadata: `login_masked`, type, currency, balance and equity. |
| `/api/v1/symbols?universe_only=&refresh=` | Discovered Forex symbols, contract specs and the universe mapping. |
| `/api/v1/market/{symbol}/candles?timeframe=H4&count=500&closed_only=false` | Candles for D1, H4 or H1, in UTC, plus a validation report. |
| `/api/v1/market/{symbol}/tick` | Latest quote with spread, age, staleness and a clock-skew flag. |

`{symbol}` accepts a canonical pair (`EURUSD`) or an exact broker name (`EURUSD.r`). Errors come back as `{"error": {"code", "message"}}`.
