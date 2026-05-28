"""build_container smoke 테스트 — 실 어댑터 인스턴스화 검증."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from kor_trading.application.use_cases.run_pipeline import RunPipelineUseCase
from kor_trading.infrastructure.config import AppConfig, Secrets
from kor_trading.infrastructure.container import AppContainer, build_container

if TYPE_CHECKING:
    from pathlib import Path


_YAML = """
schedule:
  interval_seconds: 3600
  active_hours_kst: {start: "08:30", end: "16:30"}
  active_weekdays: [1, 2, 3, 4, 5]

selection:
  top_volume_n: 50
  surge_top_n: 10
  plunge_top_n: 10
  market_cap_min_krw: 50_000_000_000
  max_candidates: 30
  markets: [KOSPI, KOSDAQ]
"""


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    p = tmp_path / "config.yaml"
    p.write_text(_YAML, encoding="utf-8")
    return AppConfig.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))


@pytest.fixture
def secrets(monkeypatch: pytest.MonkeyPatch) -> Secrets:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "cid")
    monkeypatch.setenv("DART_API_KEY", "key")
    return Secrets(_env_file=None)  # type: ignore[call-arg]


class TestBuildContainer:
    def test_returns_pipeline(self, cfg: AppConfig, secrets: Secrets, tmp_path: Path) -> None:
        container = build_container(cfg, secrets, data_base_path=tmp_path)
        assert isinstance(container, AppContainer)
        assert isinstance(container.pipeline, RunPipelineUseCase)
        assert container.pipeline.select_stocks is not None
        assert container.pipeline.analyze_indicators is not None
        assert container.pipeline.generate_report is not None
