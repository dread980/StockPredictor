"""Shared data containers.

These are the objects that cross module boundaries. Using small, explicit
structures instead of loose dictionaries means a typo shows up at import
time rather than three functions later.

The pandas schemas are optional: if ``pandera`` is installed the price and
feature frames get checked properly, and if it is not, the lightweight
checks in ``data.validation`` still run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

Signal = Literal["BUY", "SELL", "HOLD", "NO_TRADE"]
ExitReason = Literal["signal", "stop_loss", "take_profit", "time_limit", "end_of_test"]


@dataclass
class Forecast:
    """A single forecast for one symbol."""

    symbol: str
    as_of: pd.Timestamp
    horizon_days: int
    expected_return: float
    signal: Signal
    confidence: float | None = None
    lower: float | None = None
    upper: float | None = None
    rationale: str = ""

    @property
    def straddles_zero(self) -> bool:
        return self.lower is not None and self.upper is not None and self.lower <= 0.0 <= self.upper


@dataclass
class Trade:
    """One closed round trip.

    ``entry_price`` and ``exit_price`` are the fills actually used, fees
    included separately, so a trade ledger and the equity curve always
    reconcile.
    """

    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    shares: float
    entry_price: float
    exit_price: float
    side: Literal["long"] = "long"
    costs: float = 0.0
    exit_reason: ExitReason = "signal"

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.costs

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return self.exit_price / self.entry_price - 1.0

    @property
    def holding_days(self) -> int:
        return int((self.exit_date - self.entry_date).days)


@dataclass
class BacktestResult:
    """Everything a tearsheet, a test or the app needs to inspect."""

    symbol: str
    initial_capital: float
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    benchmark_equity: pd.Series | None = None
    metrics: dict = field(default_factory=dict)
    cost_as_of: str = ""
    # Day-by-day cash, position and action. Kept on the result rather than
    # thrown away so exposure can be measured and the books can be proved
    # to reconcile after the fact.
    trace: pd.DataFrame | None = None

    @property
    def final_value(self) -> float:
        return float(self.equity.iloc[-1]) if len(self.equity) else self.initial_capital
