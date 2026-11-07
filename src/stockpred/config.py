"""Configuration.

One validated object drives the whole pipeline. Defaults live in the YAML
files under ``configs/``; anything secret or machine specific comes in
through environment variables, which pydantic-settings picks up for us.

The old script had risk limits as bare attributes that nothing ever read.
Here they are part of the same object the backtester is handed, so a limit
that is set is a limit that is enforced.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataConfig(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["TCS.NS"])
    benchmark: str = "^NSEI"
    period: str = "5y"
    interval: str = "1d"
    cache_dir: Path = Path("artifacts/cache")
    cache_ttl_hours: float = 12.0
    min_rows: int = 400
    drop_incomplete_session: bool = True


class FeatureConfig(BaseModel):
    lookback_days: int = 20
    include_cross_section: bool = False
    max_features: int = 60


class TargetConfig(BaseModel):
    kind: Literal["log_return", "direction", "triple_barrier"] = "log_return"
    horizon: int = 1
    dead_zone: float = 0.0
    barrier_profit: float = 0.02
    barrier_stop: float = 0.02
    barrier_days: int = 5


class RiskConfig(BaseModel):
    """Every limit the backtester has to respect."""

    max_position_pct: float = 0.30
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.02
    min_cash_reserve: float = 0.20
    risk_per_trade_pct: float = 0.01
    atr_window: int = 14
    kelly_fraction: float = 0.25
    max_sector_pct: float = 0.40
    max_correlated_positions: int = 3

    @field_validator("max_position_pct", "min_cash_reserve", "risk_per_trade_pct")
    @classmethod
    def _check_fraction(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("must be a fraction in (0, 1]")
        return value


class BacktestConfig(BaseModel):
    initial_capital: float = 100_000.0
    buy_threshold: float = 0.003
    sell_threshold: float = -0.003
    risk_free_rate: float = 0.065
    fill: Literal["next_open", "next_close"] = "next_open"
    retrain_every: int = 60
    retrain_window: Literal["expanding", "rolling"] = "expanding"


class ModelConfig(BaseModel):
    random_state: int = 42
    test_size: float = 0.2
    n_splits: int = 5
    gap: int = 20
    embargo: int = 5
    tuning_trials: int = 25
    ensemble: list[str] = Field(
        default_factory=lambda: [
            "Linear Regression",
            "Ridge",
            "Random Forest",
            "XGBoost",
            "LightGBM",
        ]
    )


class PathConfig(BaseModel):
    artifacts: Path = Path("artifacts")
    models: Path = Path("artifacts/models")
    reports: Path = Path("artifacts/reports")


class BrokerageConfig(BaseModel):
    delivery_pct: float = 0.0
    intraday_pct: float = 0.0003
    flat_per_order: float = 20.0


class TaxConfig(BaseModel):
    stt_delivery_pct: float = 0.001
    stt_intraday_pct: float = 0.00025
    exchange_txn_pct: float = 0.0000325
    sebi_pct: float = 0.000001
    stamp_duty_pct: float = 0.00015
    gst_pct: float = 0.18


class OtherCostConfig(BaseModel):
    dp_charge_per_sell: float = 13.5


class SlippageConfig(BaseModel):
    base_bps: float = 5.0
    impact_coefficient: float = 0.1
    small_cap_extra_bps: float = 10.0


class CostConfig(BaseModel):
    as_of: str = "2024-10-01"
    brokerage: BrokerageConfig = Field(default_factory=BrokerageConfig)
    taxes: TaxConfig = Field(default_factory=TaxConfig)
    other: OtherCostConfig = Field(default_factory=OtherCostConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)


class Settings(BaseSettings):
    """Top-level settings object.

    Nested config sections stay as plain pydantic models; only the secret
    fields are pulled from the environment. The env prefix keeps the names
    from colliding with anything else on the machine.
    """

    model_config = SettingsConfigDict(
        env_prefix="STOCKPRED_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data: DataConfig = Field(default_factory=DataConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    costs: CostConfig = Field(default_factory=CostConfig)

    # Optional secrets. None means the corresponding integration is off.
    alphavantage_api_key: str | None = None
    telegram_bot_token: str | None = None
    # The natural-language analyst works with no key at all: without one it
    # answers from the stored records deterministically. A key only lets a
    # language model compose the prose, and even then it must cite them.
    llm_provider: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout: float = 30.0
    telegram_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_email_to: str | None = None

    def ensure_dirs(self) -> None:
        """Create the artifact folders the pipeline writes into."""
        for path in (
            self.paths.artifacts,
            self.paths.models,
            self.paths.reports,
            self.data.cache_dir,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(
    config_path: str | Path | None = None,
    costs_path: str | Path | None = None,
) -> Settings:
    """Load settings from YAML, then let environment variables override.

    Passing no paths uses ``configs/default.yaml`` and ``configs/costs_india.yaml``
    relative to the repository root. Missing files are not fatal, because the
    defaults above are already usable.
    """
    root = Path(__file__).resolve().parents[2]
    config_path = Path(config_path) if config_path else root / "configs" / "default.yaml"
    costs_path = Path(costs_path) if costs_path else root / "configs" / "costs_india.yaml"

    payload = _read_yaml(config_path)
    costs = _read_yaml(costs_path)
    if costs:
        payload["costs"] = costs

    return Settings(**payload)


def save_settings(settings: Settings, path: str | Path) -> None:
    """Write the effective settings back out, so a run can be reproduced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(settings.model_dump(mode="json"), handle, sort_keys=False)
