"""설정 로드: YAML + .env.

- Secrets: 환경변수/.env에서 API 키 등 로드 (pydantic-settings)
- AppConfig: config/default.yaml 파싱 (pydantic 모델)
- 변환 헬퍼: AppConfig → SelectionCriteria
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import TYPE_CHECKING, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kor_trading.application.dto.selection import SelectionCriteria
from kor_trading.domain.entities.ticker import Market  # noqa: TC001 (pydantic runtime)

if TYPE_CHECKING:
    from pathlib import Path


class Secrets(BaseSettings):
    """`.env` 또는 환경변수에서 시크릿 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    telegram_chat_id: str
    dart_api_key: str
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_account_no: str | None = None


class ScheduleConfig(BaseModel):
    interval_seconds: int = Field(ge=60)
    active_hours_kst: dict[str, str]
    active_weekdays: list[int]

    @property
    def start_time(self) -> time:
        return time.fromisoformat(self.active_hours_kst["start"])

    @property
    def end_time(self) -> time:
        return time.fromisoformat(self.active_hours_kst["end"])

    def is_active(self, now: datetime) -> bool:
        iso_weekday = now.isoweekday()
        if iso_weekday not in self.active_weekdays:
            return False
        return self.start_time <= now.time() <= self.end_time


class SelectionConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    top_volume_n: int = Field(ge=0)
    surge_top_n: int = Field(ge=0)
    plunge_top_n: int = Field(ge=0)
    market_cap_min_krw: int = Field(ge=0)
    max_candidates: int = Field(gt=0)
    markets: list[Market]


class IndicatorsConfig(BaseModel):
    """지표 계산 파라미터 (yaml의 다른 키는 무시)."""

    model_config = ConfigDict(extra="ignore")

    ohlcv_lookback_days: int = Field(default=120, gt=0)


class NewsConfig(BaseModel):
    """뉴스·공시 파라미터 (yaml의 다른 키는 무시)."""

    model_config = ConfigDict(extra="ignore")

    lookback_days: int = Field(default=7, gt=0)
    max_issues_per_ticker: int = Field(default=20, gt=0)


@dataclass(frozen=True, slots=True)
class PipelineOptions:
    """파이프라인 실행에 필요한 config 파생 값."""

    indicator_lookback_days: int
    issue_lookback_days: int
    max_issues_per_ticker: int


class AppConfig(BaseModel):
    schedule: ScheduleConfig
    selection: SelectionConfig
    indicators: IndicatorsConfig = Field(default_factory=IndicatorsConfig)
    news: NewsConfig = Field(default_factory=NewsConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def to_selection_criteria(self) -> SelectionCriteria:
        return SelectionCriteria(
            top_volume_n=self.selection.top_volume_n,
            surge_top_n=self.selection.surge_top_n,
            plunge_top_n=self.selection.plunge_top_n,
            market_cap_min_krw=self.selection.market_cap_min_krw,
            max_candidates=self.selection.max_candidates,
            markets=tuple(self.selection.markets),
        )

    def to_pipeline_options(self) -> PipelineOptions:
        return PipelineOptions(
            indicator_lookback_days=self.indicators.ohlcv_lookback_days,
            issue_lookback_days=self.news.lookback_days,
            max_issues_per_ticker=self.news.max_issues_per_ticker,
        )
