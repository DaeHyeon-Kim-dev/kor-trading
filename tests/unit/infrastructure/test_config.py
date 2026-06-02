"""AppConfig 로더 테스트 (YAML + .env)."""

from datetime import datetime
from pathlib import Path

import pytest

from kor_trading.infrastructure.config import AppConfig, Secrets


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


_MINIMAL_YAML = """
schedule:
  interval_seconds: 3600
  active_hours_kst:
    start: "08:30"
    end: "16:30"
  active_weekdays: [1, 2, 3, 4, 5]

selection:
  top_volume_n: 50
  surge_top_n: 10
  plunge_top_n: 10
  market_cap_min_krw: 50_000_000_000
  max_candidates: 30
  markets: ["KOSPI", "KOSDAQ"]
"""


_FULL_YAML = (
    _MINIMAL_YAML
    + """
indicators:
  ohlcv_lookback_days: 200
  sma_periods: [5, 20, 60, 120]

news:
  lookback_days: 14
  max_issues_per_ticker: 10
"""
)


class TestPipelineOptions:
    def test_defaults_when_sections_absent(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        opts = cfg.to_pipeline_options()
        assert opts.indicator_lookback_days == 120
        assert opts.issue_lookback_days == 7
        assert opts.max_issues_per_ticker == 20

    def test_reads_from_yaml_when_present(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _FULL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        opts = cfg.to_pipeline_options()
        assert opts.indicator_lookback_days == 200
        assert opts.issue_lookback_days == 14
        assert opts.max_issues_per_ticker == 10

    def test_ignores_unknown_indicator_keys(self, tmp_path: Path) -> None:
        # sma_periods, macd 등 추가 키가 있어도 무시 (검증 통과)
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _FULL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        assert cfg.indicators.ohlcv_lookback_days == 200


class TestSecrets:
    def test_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        monkeypatch.setenv("DART_API_KEY", "dart-key")
        s = Secrets(_env_file=None)  # type: ignore[call-arg]
        assert s.telegram_bot_token == "tok-123"
        assert s.telegram_chat_id == "456"
        assert s.dart_api_key == "dart-key"

    def test_missing_required_field_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.delenv("DART_API_KEY", raising=False)
        with pytest.raises(ValueError):
            Secrets(_env_file=None)  # type: ignore[call-arg]


class TestAppConfigLoading:
    def test_loads_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        assert cfg.schedule.interval_seconds == 3600
        assert cfg.schedule.active_weekdays == [1, 2, 3, 4, 5]
        assert cfg.selection.top_volume_n == 50

    def test_yaml_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            AppConfig.from_yaml(tmp_path / "missing.yaml")


class TestAppConfigConversion:
    def test_to_selection_criteria_matches_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        criteria = cfg.to_selection_criteria()
        assert criteria.top_volume_n == 50
        assert criteria.surge_top_n == 10
        assert criteria.plunge_top_n == 10
        assert criteria.market_cap_min_krw == 50_000_000_000
        assert criteria.max_candidates == 30
        assert criteria.markets == ("KOSPI", "KOSDAQ")


class TestScheduleActivation:
    def test_is_active_inside_window(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        # 화요일 09:00 KST
        dt = datetime(2026, 5, 26, 9, 0)
        assert cfg.schedule.is_active(dt) is True

    def test_is_inactive_outside_hours(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        # 화요일 06:00 (08:30 이전)
        dt = datetime(2026, 5, 26, 6, 0)
        assert cfg.schedule.is_active(dt) is False

    def test_is_inactive_on_weekend(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        _write_yaml(yaml_file, _MINIMAL_YAML)
        cfg = AppConfig.from_yaml(yaml_file)
        # 일요일 09:00
        dt = datetime(2026, 5, 24, 9, 0)
        assert cfg.schedule.is_active(dt) is False
