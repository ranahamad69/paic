# CLAUDE.md — AI Forex Swing Trading Platform

> This file is the project-level instruction set for Claude Code. Read it before making changes.
> Project status: specification and Phase 1 only. Do not skip phases or enable live trading.

## 1. Project mission

Build a professional, semi-automated Forex swing-trading platform using:

- MetaTrader 5 (MT5) as the broker/trading-terminal integration.
- Python for the backend, market-data processing, strategy, risk controls and execution orchestration.
- FastAPI for the backend API.
- React + TypeScript for the web dashboard.
- Claude API for constrained market analysis and explanations.
- PostgreSQL for durable records and Redis for caching/background work where justified.

The application scans major and minor Forex pairs, analyses multiple timeframes, creates explainable trade proposals, and requires explicit human approval before any order can be submitted.

**The user remains the decision-maker.** AI analysis is advisory. Deterministic backend rules govern risk and execution.

## 2. Non-negotiable safety rules

1. Start in read-only mode. Phase 1 must not place, modify, or close orders.
2. Never implement or call `mt5.order_send()` until a later phase is explicitly authorized in the project plan. Even then, implement it first for a demo account only, behind an explicit execution-mode setting and human approval.
3. Live trading must remain disabled by default. Never enable it automatically.
4. No autonomous order execution. Every order requires an authenticated human approval tied to a specific, unexpired proposal and exact order parameters.
5. Claude must never calculate authoritative position size, override risk limits, approve a trade, or call broker execution functions.
6. Risk limits must be enforced in deterministic backend code and rechecked immediately before execution.
7. Never hardcode credentials, API keys, account passwords, tokens, or private endpoints. Use environment variables or a secrets manager. Do not log secrets.
8. Do not expose broker passwords, full account identifiers, or sensitive configuration through API responses or the browser.
9. Treat broker data, AI output, external news and user-provided text as untrusted input. Validate and constrain all data.
10. Fail closed: if MT5 disconnects, data is stale, account details are unavailable, risk cannot be calculated, proposal has expired, or broker checks fail, do not trade.
11. Do not claim a trade was placed unless the broker confirms the result and the application reconciles the resulting order/position.
12. Do not claim a strategy is profitable based only on a backtest. Account for spread, commission, swaps, slippage, execution delays and look-ahead bias.

## 3. Product decisions

### Trading market
- Forex major and minor pairs.
- Initial target universe (broker availability must be checked):
  - EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD
  - EURGBP, EURJPY, EURCHF, EURAUD, EURCAD
  - GBPJPY, GBPCHF, GBPAUD, GBPCAD
  - AUDJPY, AUDNZD, AUDCAD, CADJPY
- Brokers often use symbol suffixes/prefixes. Never assume a symbol is named exactly `EURUSD`. Discover symbols from MT5 and maintain a configurable mapping.

### Trading style and timeframes
- Swing trading.
- D1: primary trend and market structure.
- H4: setup identification and confirmation.
- H1: entry refinement.
- Use completed candles for signal generation by default. Clearly distinguish the current forming candle from closed candles.
- Avoid hardcoding market session assumptions. Make session filters configurable.

### Initial technical indicators
- EMA 20, EMA 50 and EMA 200.
- RSI 14.
- MACD (document the chosen parameters).
- ADX 14.
- ATR 14.
- Support/resistance and market-structure logic must be explicit, testable and documented.

### Experimental signal scoring
Initial configurable weights:
- D1 trend: 25 points.
- H4 technical confirmation: 30 points.
- Momentum: 15 points.
- Market structure: 15 points.
- AI assessment: 15 points.
- Total: 100 points.

Initial candidate thresholds:
- 80–100: strong candidate for review.
- 65–79: watchlist.
- Below 65: no proposal.

These are experimental ranking scores, not probabilities or guarantees. Do not call a score an 80% chance of winning. Make weights and thresholds configurable and validate them through out-of-sample testing.

## 4. Initial technology choices

- Python: target Python 3.12 only if the selected MetaTrader5 package version supports it in the actual Windows environment; otherwise use a supported Python version and document why.
- MT5: official `MetaTrader5` Python package and desktop terminal.
- Backend: FastAPI, Pydantic.
- Data: Pandas and NumPy; use TA-Lib or another maintained indicator library only after verifying installation compatibility. If a library is unavailable, implement and test the required indicators transparently.
- Database: PostgreSQL.
- Cache/background work: Redis only when needed; avoid premature complexity.
- Frontend: React, TypeScript, Tailwind CSS.
- Charts: TradingView Lightweight Charts.
- Tests: Pytest, API integration tests and mocked broker adapters.
- Deployment: MT5 terminal and Python bridge on a compatible Windows PC/Windows VPS. Do not assume the official MT5 Python package works inside a Linux container. Other services may run separately and communicate over a secured private network.

## 5. Architecture boundaries

Keep these concerns separate:

1. `mt5_connector`: terminal initialization, status, account metadata, terminal metadata and shutdown.
2. `symbol_manager`: symbol discovery, Forex filtering, broker symbol mapping and contract specifications.
3. `market_data`: candles, ticks, timestamps, freshness and data validation.
4. `indicators`: deterministic indicator calculations.
5. `market_structure`: trend, swing highs/lows, support/resistance and breakout/pullback definitions.
6. `strategy_engine`: deterministic candidate signal generation.
7. `ai_engine`: Claude request/response schemas, analysis and explanation only.
8. `risk_engine`: position sizing, exposure, limits and independent validation.
9. `signal_manager`: candidate and proposal lifecycle, deduplication and expiry.
10. `approval_engine`: authenticated human decision and immutable approval record.
11. `execution_engine`: broker order operations, only in a later explicitly authorized phase.
12. `portfolio_manager`: open positions, pending orders and currency exposure.
13. `analytics_engine`: trade metrics and reporting.
14. `audit`: append-only records of important decisions and state changes.

Do not let the frontend call MT5 directly. Do not let the AI module import or access the execution adapter. Avoid circular imports and hidden global state.

## 6. MT5 integration requirements

- Run the MT5 terminal and its Python integration in a compatible Windows environment.
- Provide a clear connection lifecycle: initialize, health check, use, reconnect where safe, and shutdown.
- Avoid concurrent unsafe calls to the terminal. Serialize MT5 operations through a dedicated adapter/service or lock.
- Handle terminal-not-running, authorization failure, disconnected broker, missing symbol, market closed, missing history and API errors.
- Discover available symbols using MT5, filter for Forex instruments, and explicitly select/enable symbols when required.
- Retrieve D1, H4 and H1 historical candles and latest ticks.
- Normalize timestamps to UTC internally. Store timezone-aware timestamps.
- Detect missing, duplicated, malformed and out-of-order candles.
- Check whether the newest bar is still forming. Do not silently treat it as closed.
- Capture symbol specifications needed later for risk calculations: digits, point, tick size, tick value where available, contract size, volume minimum/maximum/step, stop level, trade mode and currency metadata.
- Never assume pip value, contract size, leverage or volume rules are identical across brokers.
- Mask account identifiers in logs and API responses.

## 7. Strategy and AI contract

### Deterministic strategy first
The strategy engine must be reproducible from the same input data and configuration. It generates candidate setups from documented rules. Do not use Claude to invent indicator values or silently alter rules.

### Claude's allowed role
Claude may:
- Classify a market regime based on supplied validated features.
- Summarize trend and momentum context.
- Explain supporting and conflicting factors.
- Identify missing or stale information.
- Provide a structured advisory assessment.

Claude may not:
- Submit, modify or close orders.
- Set or override account risk limits.
- Decide authoritative lot size.
- Bypass spread, exposure, margin or stop-distance checks.
- Treat its own confidence score as a calibrated win probability.

Use strict Pydantic schemas for model inputs and outputs. Reject malformed, incomplete or out-of-range responses. Store model name, prompt/schema version, input snapshot reference, output, timestamp and validation result. Do not send credentials or unnecessary personal/account data to the model.

Example advisory response shape:

```json
{
  "symbol": "EURUSD",
  "direction": "BUY",
  "market_regime": "TRENDING",
  "setup_quality": 82,
  "supporting_factors": ["Daily bullish structure", "H4 EMA alignment"],
  "conflicting_factors": [],
  "invalidation_conditions": ["H4 bullish structure breaks"],
  "recommendation": "REVIEW"
}
```

The backend must independently verify that the AI's symbol and direction match the candidate being assessed.

## 8. Risk management requirements for later phases

Initial values are development/demo defaults only and must be configurable:
- Risk per trade: 0.25% of equity.
- Maximum open positions: 4.
- Maximum daily loss: 1% (define whether based on start-of-day equity and include realized plus floating P&L).
- Minimum reward/risk: 1:2.
- Maximum correlated exposure: 1R, with documented currency-exposure methodology.
- ATR-based stop distance.
- Default target: 2R.

Before any order:
- Calculate loss in account currency using broker instrument specifications and an appropriate MT5 calculation method (for example `order_calc_profit` when applicable).
- Validate volume min/max/step and normalize volume without increasing risk beyond the cap.
- Check margin availability using broker calculations.
- Check stop/freeze levels and order constraints.
- Check current spread, quote freshness and market status.
- Check aggregate open and pending risk, correlated currency exposure and daily loss lockout.
- Run broker-side preflight/check where supported.
- Revalidate all conditions immediately before submission.
- If a calculation or check is unavailable, reject the proposal.

Provide a kill switch that blocks new orders independently of Claude. Define and test what happens to existing positions; never silently close them as a side effect of activating the switch.

## 9. Human approval and execution requirements for later phases

A proposal must contain:
- Unique proposal ID.
- Symbol and direction.
- Strategy/version and timeframe.
- Entry type and entry price/range.
- Stop-loss and take-profit.
- Volume/lot size.
- Estimated cash risk and percentage risk.
- Reward/risk ratio.
- Spread and quote timestamp.
- AI assessment and supporting/conflicting factors.
- Expiry time and invalidation conditions.

Approval must be authenticated and tied to the exact proposal version and order parameters. Any material parameter change invalidates the approval and requires a new approval. Reject expired proposals. Prevent duplicate submissions with idempotency keys and broker reconciliation.

Execution should initially be implemented only against an MT5 demo account after explicit authorization. Live trading requires a separate deliberate project decision and must never be enabled by configuration accident.

## 10. Data model for later phases

Use migrations and explicit constraints. Expected entities:
- accounts (store minimal, masked metadata)
- symbols
- market_candles
- indicator_snapshots
- trading_signals
- ai_analyses
- trade_proposals
- trade_approvals
- orders
- positions
- risk_events
- audit_logs

Store enough identifiers to trace a broker order back to its signal, AI analysis, risk checks, proposal and human approval. Use UTC timestamps. Avoid storing secrets in the database.

## 11. API direction

Version endpoints under `/api/v1`. Initial read-only endpoints:
- `GET /api/v1/health`
- `GET /api/v1/mt5/status`
- `GET /api/v1/account` (masked, authenticated)
- `GET /api/v1/symbols`
- `GET /api/v1/market/{symbol}/candles?timeframe=H4&count=500`
- `GET /api/v1/market/{symbol}/tick`

Later endpoints may include signals, proposals, approvals, positions, history, analytics and kill switch. Do not create a trade-submission endpoint in Phase 1.

Protect sensitive endpoints with authentication. Configure CORS narrowly. Add request validation, sensible rate limits, structured errors and health/readiness distinction.

## 12. Dashboard requirements for later phases

Screens:
1. Overview: balance, equity, floating P&L, daily P&L and connection status.
2. Market scanner: pair, D1 trend, H4 confirmation, RSI, ADX, volatility and signal score.
3. AI analysis: regime, rationale, conflicts and invalidation conditions.
4. Trade approval: exact order parameters, estimated risk and approve/reject controls.
5. Portfolio: positions, pending orders and currency exposure.
6. Analytics: win rate, profit factor, average R, drawdown and performance by pair/strategy.

Use clear connection/staleness indicators. Do not display fabricated or sample values as live account data. Label mock/demo data prominently.

## 13. Testing and quality standards

- Write tests alongside implementation, not at the end.
- Unit-test indicators against known reference values and edge cases.
- Test strategy logic with deterministic fixtures.
- Mock MT5 for normal CI tests; tests must not require a broker account.
- Add integration tests for the Windows MT5 environment separately.
- Test disconnects, stale ticks, missing candles, malformed broker responses and symbol suffixes.
- Test risk calculations for JPY and non-JPY pairs, account-currency conversion, volume steps and boundary conditions before execution exists.
- Use type hints, docstrings for public interfaces, linting/formatting and clear module boundaries.
- Never silently swallow exceptions. Log actionable errors without secrets.
- Do not fabricate test results. State exactly which tests ran and which require Windows/MT5.

## 14. Development workflow for Claude Code

At the start of each task:
1. Read this file and the current README/architecture documents.
2. Inspect the existing repository before changing files.
3. Identify the current phase and its acceptance criteria.
4. Propose a concise implementation plan.
5. Implement only the requested phase/task.
6. Run relevant tests and report exact results.
7. Update documentation and `.env.example` when configuration changes.
8. Summarize changed files, design decisions, limitations and next task.

Do not rewrite working modules unnecessarily. Do not add dependencies without explaining why. Prefer small, reviewable changes. Ask before making destructive changes, introducing paid services, or changing project scope.

## 15. Phased roadmap and gates

### Phase 1 — MT5 connectivity and market data (CURRENT)
Deliver:
- Repository and environment setup.
- FastAPI app.
- MT5 connector lifecycle.
- Connection/terminal/account status (masked).
- Symbol discovery and Forex filtering.
- D1/H4/H1 candles and latest tick.
- UTC normalization and candle validation.
- Mocked unit tests.
- Read-only endpoints.
- `.env.example`, `.gitignore`, README and architecture documentation.

Acceptance:
- Application starts without crashing when MT5 is unavailable.
- Mock-based tests pass without MT5 installed.
- On compatible Windows/MT5 setup, a manual smoke test can retrieve account metadata, symbols and candles.
- No order placement/modification/closure code is present.
- No credentials are committed or logged.

### Phase 2 — Indicators and market structure
Implement and test EMA, RSI, MACD, ADX, ATR, swing highs/lows, trend and support/resistance.

### Phase 3 — Deterministic strategy engine
Implement configurable multi-timeframe swing setups, signal scoring, deduplication and expiry.

### Phase 4 — Claude analysis
Add constrained AI assessments, strict schemas, prompt versioning and audit records.

### Phase 5 — Risk engine
Implement independent sizing, exposure, spread, margin and loss-limit checks. No order submission yet.

### Phase 6 — Web dashboard
Implement the React interface and authenticated read-only views, then proposal review UI.

### Phase 7 — Human approval and demo execution
Only after explicit authorization, add approval-bound MT5 demo order execution, idempotency, broker reconciliation and position monitoring. Live mode remains disabled.

### Phase 8 — Backtesting and forward validation
Use realistic spreads, commissions, swaps, slippage and execution assumptions. Use chronological train/validation/test splits, walk-forward analysis and out-of-sample evaluation. Avoid look-ahead and survivorship bias.

### Phase 9 — Operational hardening
Monitoring, backups, security review, recovery testing, deployment documentation and demo forward testing.

Do not advance to the next phase until the current phase's acceptance criteria are met and the user has reviewed the result.

## 16. First task to execute now

Implement **Phase 1 only: MT5 connectivity and read-only market data foundation**.

Before coding:
- Inspect the machine/runtime OS and Python version.
- Verify the current MetaTrader5 Python package's supported environment.
- If not on compatible Windows with MT5 installed, build the adapter interface and mock implementation first; document the Windows smoke-test steps.
- Do not attempt to install or run incompatible MT5 components.

Then implement the Phase 1 deliverables and tests. At completion, report:
- Files created/changed.
- Setup and run commands.
- Environment variables required (names only; never request secrets in chat or commit them).
- Endpoints implemented.
- Tests executed and exact pass/fail counts.
- Whether a real MT5 connection was actually verified or only mocked.
- Remaining blockers and the next recommended task.

**Stop after Phase 1. Do not start strategy, AI, risk-based order sizing or execution until instructed.**
