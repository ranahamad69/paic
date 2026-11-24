# Architecture — Phase 1

## Module boundaries

```
HTTP (FastAPI, api/v1) ──► services container (app/services.py, no globals)
                              │
          ┌───────────────────┼─────────────────────┐
          ▼                   ▼                     ▼
   market_data.service   symbol_manager.manager   mt5_connector.connector
   (candles, ticks,      (discovery, Forex        (lifecycle, lock,
    validation, UTC)      filter, mapping, specs)  health, reconnect)
          └─────────────► mt5_connector.connector ◄──┘
                              │ run(fn) — serialised, fail-closed
                              ▼
                     BrokerAdapter (ABC, read-only)
                     ├── MT5Adapter   (MetaTrader5 package, lazy import, Windows)
                     └── MockAdapter  (synthetic, labelled MOCK)
```

* **No component other than the adapters touches MT5.** The frontend (later) talks only to the API.
* `BrokerAdapter` has **no order methods**. Execution will be a separate `execution_engine` that requires explicit authorisation (Phase 7). AI modules (Phase 4) must never import it.
* Adapters return **raw, untrusted** dicts. Validation happens in `symbol_manager` and `market_data`.

## Connection lifecycle (`MT5Connector`)

1. `connect()` runs at app startup in a worker thread. It **never raises**: failures are recorded in `state` and the app keeps starting.
2. Every broker call goes through `run(fn)`, which:
   * holds an `RLock` (the MT5 IPC channel is not thread-safe, and FastAPI runs sync routes in a thread pool);
   * reconnects if not initialised, at most once every `MT5_RECONNECT_INTERVAL_SECONDS`;
   * checks `terminal_info()` and that the terminal is connected to the broker;
   * raises `BrokerUnavailableError` (HTTP 503) otherwise, so callers fail closed;
   * marks the connection down after an unexpected adapter exception.
3. `shutdown()` runs at app teardown and is idempotent.

## Time handling

MT5 bar and tick times are epoch seconds of the **broker server's wall clock**, not UTC. `MT5_SERVER_TIMEZONE` (an IANA zone, so DST is handled, or a fixed `UTC±H`) converts them to timezone-aware UTC (`core/timeutil.py`). A wrong setting shows up as:
* `FUTURE_BAR` errors in candle validation;
* `clock_skew_suspected: true` (and `is_stale: true`) on ticks.

Many brokers use GMT+2 in winter and GMT+3 in summer, switching on **US** DST dates. That doesn't match any single IANA zone exactly, so verify the setting against the broker and the smoke test. A dedicated "US-DST-aligned" option may be needed later.

## Symbols

* A symbol counts as Forex when its calc mode is FOREX or FOREX_NO_LEVERAGE **and** both base and profit currencies are fiat ISO codes. Metals, crypto and CFDs are excluded.
* Canonical name = `base + profit`. Mapping order: `SYMBOL_MAP_OVERRIDES` (validated), then an exact name, then a single unique candidate (for suffixes such as `.r` or `m`). Several candidates make the pair `AMBIGUOUS` (HTTP 409 until an override is set). Pairs without a symbol are `MISSING`.
* Contract specs (digits, point, tick size and value, contract size, volume min/max/step, stop and freeze levels, trade mode, currencies) are captured for Phase 5 risk calculations. A tick value of 0 is stored as `null` (unavailable), never as a guess.
* Discovery is cached for 5 minutes (`refresh=true` bypasses the cache). Symbols are added to Market Watch (`symbol_select`) on demand. This is not a trade action.

## Candle validation (`market_data/validation.py`)

Nothing is silently fixed. Each response carries a `ValidationReport`. `is_valid` is false if any ERROR is present.

| Code | Severity | Meaning |
|---|---|---|
| MALFORMED_RECORD | ERROR | Raw record unparseable (skipped) |
| INVALID_PRICE | ERROR | Price that is non-finite or ≤ 0 |
| INCONSISTENT_OHLC | ERROR | high < low, or open/close outside [low, high] |
| NEGATIVE_VOLUME | ERROR | |
| DUPLICATE | ERROR | Repeated open time |
| OUT_OF_ORDER | ERROR | Bar earlier than its predecessor |
| FUTURE_BAR | ERROR | Bar opens in the future, or an unclosed bar is not the newest (timezone problem) |
| EMPTY | ERROR | No bars |
| WEEKEND_GAP | WARNING | Gap ≤ 72h that touches a server-time Saturday |
| GAP | WARNING | Any other missing bars (holiday, history hole) |
| STALE | WARNING | Newest bar is older than one bar plus 72h |

Forming-bar rule: a bar is closed when `open_time + duration ≤ now` (UTC). Every candle carries `is_closed`. Use `closed_only=true` to get exactly `count` closed bars.

## Security

* Bearer token (`API_AUTH_TOKEN`, compared in constant time) on every endpoint except health and readiness. With no token set, protected endpoints are disabled (503).
* The account endpoint returns the login masked (`*****678`) and never the holder name. Logs mask the login, and the password is a `SecretStr` that is never logged.
* CORS is off unless `CORS_ALLOWED_ORIGINS` is set (GET only, no credentials).
* An in-process per-IP rate limit is applied. For multi-worker or public deployments, use a reverse proxy or Redis instead.

## Known limitations (Phase 1)

* No real MT5 connection has been verified yet. Only mocks were exercised in CI (see the Windows smoke test).
* The weekend/holiday classification is heuristic, and broker-specific sessions are not modelled yet.
* No persistence (PostgreSQL) yet. Data is fetched live per request.
