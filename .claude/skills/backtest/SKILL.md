---
name: backtest
description: Run a Phase 1 backtest for one or more symbols using the project's backtesting engine. Downloads recent historical klines from Bybit, runs the chosen strategy against the data, and prints win-rate / drawdown / P&L metrics. Pass the symbol(s) and an optional `--days N` (default 90). Use when validating a strategy change before deploying to paper trading.
disable-model-invocation: true
---

# Backtest a strategy

Goal: run the project's backtesting framework end-to-end for a given symbol set and report the metrics. Lives in `backtesting/` at repo root.

## Inputs

- **symbol(s)** (required): one or more of `SOLUSDT`, `BNBUSDT`, `ADAUSDT` (validated). Other symbols (`BTCUSDT`, `ETHUSDT`, `XRPUSDT`, `DOGEUSDT`) were excluded by paper-trading data and shouldn't be backtested into a deploy decision.
- **--days N** (optional, default 90): how many days of historical klines to test against.
- **--mode** (optional, default `phase1`): one of `phase1` (RSI+EMA + GATEKEEPER + VALIDATOR + ATR filters) or `comparison` (Phase 1 vs Phase 3 ML+sentiment).

## Playbook

1. **Sanity-check prereqs**:
   ```bash
   python3 -c "import pandas, numpy, scipy" 2>&1
   ```
   If any fail, install: `python3 -m pip install --user --break-system-packages pandas numpy scipy`. (Project venv is a placeholder; use --user installs.)

2. **Confirm market-data-service is up** (the backtest downloader pulls from it):
   ```bash
   curl -sf http://localhost:8002/health
   ```
   If down: tell the user to bring up the stack first (`docker compose -f docker-compose.unified.yml up -d`).

3. **Run the backtest** from repo root:
   ```bash
   cd /mnt/d/Bimo_max/crypto-trading-bot
   python3 backtesting/run_phase1_backtest.py --symbol <SYM> --days <N>
   ```
   For `--mode comparison`: use `backtesting/run_phase_comparison.py` instead.

4. **Read the output**. The script prints a side-by-side metrics table: win-rate, Sharpe, max drawdown, profit factor, and goal-achievement vs Phase 1 targets:
   - +10–15% win rate
   - −20–30% max drawdown
   - −40–50% false signals

5. **Summarize** for the user:
   - Whether the run hit the Phase 1 goals.
   - Notable per-symbol differences.
   - Any data-quality warnings in the log (gaps, testnet-tainted ranges — see the gotcha below).

## Gotcha — historical data taint

TimescaleDB was wiped of testnet pollution on 2026-04-25 and refilled with mainnet. Any backtest period including dates **before 2026-04-25** that relied on stored history will be using unrealistic testnet prices. Either:
- Restrict `--days` to dates after the flip, or
- Pull fresh klines from Bybit mainnet via `data_downloader.py` first.

## Output locations

- Equity curves and trade-by-trade CSVs land in `backtesting/charts/` and `backtesting/results/`.
- Comparison runs also produce a markdown report.

## Anti-cases (don't run /backtest)

- For excluded symbols (BTC/ETH/XRP/DOGE): the strategy is *known* to lose on these. Backtesting just re-confirms — skip unless you're testing whether a change inverts the verdict.
- For very short windows (`--days 7` or less): too few signals, results are noise.
- If you just changed config in `services/trading-engine/app/config.py`: the backtest scripts run their own strategy code, **not** the live service. Backtest will not reflect those changes unless you mirror the change in `backtesting/run_phase1_backtest.py`.
