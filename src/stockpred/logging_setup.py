"""Logging setup.

The old script printed emoji-laden status lines straight from the library
functions, which made it impossible to reuse any of them. Here the library
only ever calls ``logging``; the CLI decides how loud it wants to be.

Each run gets a short id so that the console output, the log file and the
saved artifacts can be tied back to one another later.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

_CONFIGURED = False


def new_run_id() -> str:
    """A short, human-readable id for one end-to-end run."""
    return uuid.uuid4().hex[:8]


def setup_logging(
    level: int | str = logging.INFO,
    log_file: str | Path | None = None,
    run_id: str | None = None,
) -> logging.Logger:
    """Configure the root logger once and return the package logger.

    Calling this more than once is harmless: the handlers are replaced, not
    stacked, so an app that re-runs does not end up logging every line twice.
    """
    global _CONFIGURED

    logger = logging.getLogger("stockpred")
    logger.setLevel(level)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    if run_id:
        fmt = f"%(asctime)s [run {run_id}] %(levelname)-7s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Third-party libraries are noisy at INFO; keep them at WARNING.
    for noisy in ("yfinance", "urllib3", "matplotlib", "numexpr"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger.propagate = False
    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Child logger under the package namespace."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(f"stockpred.{name}")
