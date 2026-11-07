"""Labels.

The label has to match how a position actually leaves the book. Predicting
a price level and then treating the gap to the last close as a "signal" is
what made the old backtest self-fulfilling: it scored the model against the
very number it was asked to predict. The builders here produce labels that
a trade can honestly be judged against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TargetConfig


def log_return_target(close: pd.Series, horizon: int = 1) -> pd.Series:
    """Log return from the close of t to the close of t+horizon.

    The last ``horizon`` rows are NaN on purpose: their outcome has not
    happened yet. Keeping them is what lets the caller hold out a genuine
    live row instead of settling for the second-to-last day.
    """
    forward = np.log(close.shift(-horizon) / close)
    forward.name = "target"
    return forward


def direction_target(close: pd.Series, horizon: int = 1, dead_zone: float = 0.0) -> pd.Series:
    """Sign of the forward return, with an optional flat band.

    Returns are close to a coin flip, so a dead zone around zero gives the
    model the option of saying "nothing here" instead of forcing a side.
    """
    fwd = log_return_target(close, horizon)
    if dead_zone > 0:
        labels = pd.Series(0, index=close.index, dtype=float)
        labels[fwd > dead_zone] = 1.0
        labels[fwd < -dead_zone] = -1.0
        labels[fwd.isna()] = np.nan
    else:
        labels = np.sign(fwd).where(fwd.notna())
    labels.name = "target"
    return labels


def triple_barrier_labels(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    profit: float = 0.02,
    stop: float = 0.02,
    max_days: int = 5,
) -> pd.DataFrame:
    """Label a position by which barrier it hits first.

    Walks forward from each day and stops at the first touch. If the high
    and the low both breach on the same bar the outcome is unknowable from
    daily data, so the stop is assumed to have been hit - the pessimistic
    assumption, which is the only safe one to backtest on.

    Label 1 is the profit barrier, -1 the stop, 0 the time limit.
    """
    n = len(close)
    labels = np.zeros(n, dtype=float)
    hit_day = np.full(n, np.nan)
    close_vals = close.to_numpy(dtype=float)
    high_vals = high.to_numpy(dtype=float)
    low_vals = low.to_numpy(dtype=float)

    for i in range(n):
        entry = close_vals[i]
        if not np.isfinite(entry):
            labels[i] = np.nan
            continue

        upper = entry * (1 + profit)
        lower = entry * (1 - stop)
        end = min(i + 1 + max_days, n)

        outcome = 0.0
        for j in range(i + 1, end):
            hit_up = high_vals[j] >= upper
            hit_down = low_vals[j] <= lower
            if hit_up and hit_down:
                outcome = -1.0
                hit_day[i] = j
                break
            if hit_down:
                outcome = -1.0
                hit_day[i] = j
                break
            if hit_up:
                outcome = 1.0
                hit_day[i] = j
                break

        # A label whose window runs past the end of the data is not known yet.
        if i + max_days >= n:
            labels[i] = np.nan
        else:
            labels[i] = outcome

    return pd.DataFrame({"target": labels, "hit_day": hit_day}, index=close.index)


def build_target(prices: pd.DataFrame, cfg: TargetConfig) -> pd.Series:
    """Produce the label column asked for by the config."""
    close = prices["Close"]

    if cfg.kind == "log_return":
        return log_return_target(close, cfg.horizon)
    if cfg.kind == "direction":
        return direction_target(close, cfg.horizon, cfg.dead_zone)
    if cfg.kind == "triple_barrier":
        frame = triple_barrier_labels(
            close,
            prices["High"],
            prices["Low"],
            profit=cfg.barrier_profit,
            stop=cfg.barrier_stop,
            max_days=cfg.barrier_days,
        )
        return frame["target"]

    raise ValueError(f"unknown target kind: {cfg.kind}")


def forward_return_at(tradable_after: pd.Timestamp, close: pd.Series, horizon: int = 1) -> float:
    """The realised return a position opened at ``tradable_after`` would earn.

    Kept separate from the DataFrame so the backtest can ask a single
    question without slicing frames: if I buy here, what do I get?
    """
    position = close.index.get_indexer([tradable_after])[0]
    if position < 0 or position + horizon >= len(close):
        return float("nan")
    return float(np.log(close.iloc[position + horizon] / close.iloc[position]))
