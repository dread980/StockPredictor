# stockpred

`stockpred` forecasts the **next-day log return** for NSE-listed equities and, more
importantly, tries to tell you when it has no edge. It is a research toolkit, not a
signal service: the model forms a view at the close of day `t`, the backtest fills at
the open of day `t + 1`, every fill pays a realistic Indian cost model, and the report
is allowed to say "no trade" or "no edge" when that is the honest answer.

The defaults are conservative on purpose. Daily equity returns are close to noise, so
the goal is a small, well-measured edge with honest uncertainty, not a high R². A
backtest that returns nothing is a valid result here, not a bug.

## What is different here

Most stock-prediction projects show a high R² and a rising equity curve. The
differentiator here is credibility. The design choices below are the ones that make the
results hard to fake:

| Choice | What it means in the code |
| --- | --- |
| No look-ahead | Signal at the close of day `t`, fill at the next open. A feature row may use the close at `t` (the target is `t + 1`) but never `t + 1`. |
| Purged walk-forward CV | Expanding-window folds with a gap of at least the longest lookback **and** an embargo, so a training row's label window never reaches into the test block. |
| Out-of-fold stacking | The meta-model is trained only on base predictions that came from a model that never saw that row. |
| Conformal intervals | Split-conformal prediction gives a stated coverage with a finite-sample correction, instead of `prediction ± 1.96 · std`. |
| Abstain by design | No trade when the interval straddles zero or the expected move is inside the dead zone. The journal reports how often it abstained and how it did when it acted. |
| Real Indian cost model | Brokerage, STT (delivery vs intraday), exchange transaction charges, SEBI fees, stamp duty, GST, and the DP charge on delivery sells, plus slippage that grows with order size relative to average daily volume. |
| Overfitting controls | Deflated Sharpe ratio, probability of backtest overfitting, permutation test and a shuffled-label sanity check. |
| Regime tags | Each day is tagged calm / normal / stressed from a rolling volatility percentile (an HMM is used when `hmmlearn` is installed, not required). |
| Drift monitor | Rolling information coefficient, population stability index (PSI) per feature, and a calibration table. |
| Paper-trading journal | Forecasts are logged before the outcome exists and settled afterwards, so the out-of-sample record cannot be quietly edited. |
| Grounded analyst | "Why did the model turn bearish on TCS?" is answered from the stored forecast, attributions, headlines, journal and run ledger, with a `[S1]`-style citation on each claim. A language model is optional; its reply is discarded if it cites nothing. |
| Leakage canary | A test injects a feature containing tomorrow's return; the pipeline must detect it and fail loudly. This runs in CI. |

## Install

Requires Python 3.10 or newer. From the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[data,app,dev]"
```

`data` pulls in `yfinance` for price history; `app` adds Streamlit and Plotly; `dev` adds
the test and lint tooling. The heavy optional libraries (`xgboost`, `lightgbm`, `optuna`,
`shap`, `hmmlearn`, `transformers`, `weasyprint`, `pandera`) are declared as extras but are
**never required**. The code degrades gracefully and logs when one is missing:

- missing boosting libraries fall back to scikit-learn estimators,
- missing `shap` falls back to a model-agnostic importance view,
- missing `weasyprint` still writes the HTML tear sheet and skips only the PDF,
- missing `pandera` skips the optional frame-schema checks,
- missing `hmmlearn` uses the volatility-percentile regime tag.

## Quickstart

The whole pipeline is one command. On Windows, `run.cmd` at the repository root sets up
the virtual environment the first time and then runs everything, so this is the only
thing you ever type:

```powershell
.\run.cmd                 # fetch, train, backtest, forecast, rank, read
.\run.cmd --app           # the same, then open the dashboard
.\run.cmd --tune          # the same, with a hyperparameter search (slow)
.\run.cmd --report        # the same, plus an HTML tear sheet per symbol
.\run.cmd --help          # every other flag
```

With the environment active, the same thing is `stockpred run`. The individual steps,
if you want them separately:

```bash
# Download price history into the parquet cache
stockpred fetch

# Fit the ensemble for one symbol
stockpred train --symbols TCS.NS

# Walk-forward backtest with costs, stops and the reality check
stockpred backtest

# Forecast the next session
stockpred predict --symbols TCS.NS

# Rank a universe by expected risk-adjusted return
stockpred screen

# Write a tear sheet for one symbol (add --pdf to also try a PDF)
stockpred report TCS.NS --pdf

# Ask why the model leans the way it does, grounded in the stored records
stockpred ask "why did the model turn bearish?" --symbol TCS.NS

# Launch the Streamlit dashboard
stockpred app
```

Every command takes `--config` and `--costs` to point at different YAML files, and
`-v` / `--verbose` for debug logging. `stockpred run` defaults to `--no-tune` because a
hyperparameter search is the slow part; pass `--tune` when you want one.

## How to read the output

- **A zero-trade backtest is a legitimate result.** It means no session's expected move
  cleared the round-trip cost of trading that symbol. That is the tool doing its job.
- **A small positive information coefficient is normal.** IC is a rank correlation
  between forecast and outcome; on daily equity data a value of a few hundredths is
  ordinary, and near-zero is common. It is not a return.
- **Look at the reality check before the equity curve.** The permutation p-value, the
  deflated Sharpe ratio and the comparison against buy-and-hold say whether any of it
  beats chance. The report will state "no statistically significant edge" when that is
  the case.
- **Costs are shown next to every forecast.** The break-even move is the minimum move a
  signal needs just to pay for trading it; a forecast smaller than that is noise.

## Repository layout

```text
stock-predictor/
├── pyproject.toml
├── README.md
├── .env.example
├── Dockerfile
├── configs/
│   ├── default.yaml            # symbols, costs, risk limits, model grids
│   └── costs_india.yaml        # brokerage, STT, stamp duty, GST (with as-of date)
├── src/stockpred/
│   ├── config.py               # pydantic settings loader
│   ├── logging_setup.py
│   ├── schemas.py              # Forecast, Trade, BacktestResult, pandera schemas
│   ├── data/
│   │   ├── loaders.py          # yfinance + fallback sources
│   │   ├── cache.py            # parquet cache with freshness rules
│   │   ├── validation.py       # quality checks, split/dividend handling
│   │   ├── calendar.py         # NSE trading days and holidays
│   │   ├── market_context.py   # Nifty, VIX, USD/INR, sector indices
│   │   └── events.py           # results dates, corporate actions, flows
│   ├── features/
│   │   ├── indicators.py       # pure functions, no shifting inside
│   │   ├── builder.py          # assemble feature frame, shift once, X_live
│   │   ├── cross_section.py    # peer and sector ranks, relative strength
│   │   ├── selection.py        # pruning, correlation clusters
│   │   └── leakage_checks.py   # canary and future-row-change tests
│   ├── targets.py              # log return, direction, triple-barrier labels
│   ├── validation/
│   │   ├── splits.py           # purged walk-forward with embargo
│   │   ├── metrics.py          # RMSE, IC, directional accuracy, OOS R2
│   │   └── stats_tests.py      # permutation, shuffled-label, deflated Sharpe
│   ├── models/
│   │   ├── baselines.py        # naive, drift, SMA rule
│   │   ├── registry.py         # model factory from config
│   │   ├── tuning.py           # Optuna studies
│   │   ├── stacking.py         # out-of-fold stacking
│   │   ├── uncertainty.py      # conformal and quantile intervals
│   │   ├── regimes.py          # HMM or volatility regimes
│   │   └── persistence.py      # save/load full bundle with versions
│   ├── backtest/
│   │   ├── engine.py           # event loop, fills at next open, stops on High/Low
│   │   ├── costs.py            # Indian cost model + slippage
│   │   ├── sizing.py           # vol targeting, capped Kelly
│   │   ├── risk.py             # Sharpe, Sortino, drawdown, exposure
│   │   ├── portfolio.py        # multi-stock, sector caps
│   │   └── robustness.py       # Monte Carlo, sensitivity, stress tests
│   ├── explain/
│   │   ├── shap_utils.py
│   │   ├── narratives.py       # plain-language signal explanations
│   │   └── analyst.py          # grounded Q&A with citations to the records
│   ├── monitoring/
│   │   ├── drift.py            # rolling IC, PSI, calibration
│   │   └── journal.py          # paper-trading log
│   ├── sentiment/
│   │   └── news.py             # headline sentiment, timestamps
│   ├── pipelines/
│   │   ├── train.py
│   │   ├── predict.py
│   │   ├── backtest.py
│   │   └── screen.py           # universe ranking
│   ├── reporting/
│   │   ├── tearsheet.py        # HTML/PDF report
│   │   └── alerts.py           # Telegram / email
│   ├── viz/plots.py            # plotly figures, shared by UI and reports
│   └── cli.py                  # typer entry point
├── app/
│   ├── Home.py                 # Streamlit entry
│   └── pages/
│       ├── 1_Data.py
│       ├── 2_Models.py
│       ├── 3_Backtest.py
│       ├── 4_Signals.py
│       ├── 5_Screener.py
│       └── 6_Diagnostics.py    # Reality Check, drift, regimes
├── tests/
│   ├── test_indicators.py
│   ├── test_leakage.py
│   ├── test_costs.py
│   ├── test_backtest_accounting.py
│   └── test_splits.py
├── notebooks/                  # exploration only, never imported
└── artifacts/                  # cache, models, reports (git-ignored)
```

## Configuration and environment variables

Defaults live in `configs/default.yaml` (symbols, costs, risk limits, model grids) and
`configs/costs_india.yaml` (brokerage, STT, stamp duty, GST, with an as-of date). Both are
loaded into a single validated settings object, and environment variables override them.
The environment prefix is `STOCKPRED_` (for example `STOCKPRED_ARTIFACTS_DIR`).

Copy `.env.example` to `.env` to fill in optional keys. Nothing there is needed to run the
backtest; the keys only enable optional integrations:

```bash
cp .env.example .env
```

## Docker

Build the image and run the Streamlit app:

```bash
docker build -t stockpred .
docker run --rm -p 8501:8501 -v "$PWD/artifacts:/app/artifacts" stockpred
```

Or with Compose:

```bash
docker compose up
```

Mount `artifacts/` so the parquet cache, saved model bundles and generated reports persist
between runs; without the mount they are lost when the container exits.

## Testing and quality gates

```bash
pytest
ruff check .
black .
```

The test suite covers indicator values, the leakage canary, the cost model, backtest
accounting (cash plus positions equals equity), the split logic and the persistence round
trip.

## Disclaimer

This is research software. It is not investment advice, and it places no orders. It
separates research output from any broker integration on purpose: the model's only output
is a forecast, an interval and a note about costs, and any trading decision is yours. The
results of any backtest depend on the cost assumptions and data you feed it.
