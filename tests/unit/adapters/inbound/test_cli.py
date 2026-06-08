"""CLI run 명령 테스트 (활성 시간 외 skip 동작만 검증).

실제 파이프라인 실행은 통합 테스트 영역 — 본 테스트는 CLI 인자 처리 + 시간 체크에 집중.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from kor_trading.adapters.inbound.cli import app

if TYPE_CHECKING:
    from pathlib import Path


_YAML_NO_ACTIVE = """
schedule:
  interval_seconds: 3600
  active_hours_kst: {start: "08:30", end: "16:30"}
  active_weekdays: []  # 빈 → 어떤 요일에도 비활성

selection:
  top_volume_n: 1
  surge_top_n: 0
  plunge_top_n: 0
  market_cap_min_krw: 0
  max_candidates: 1
  markets: [KOSPI]
"""


@pytest.fixture
def setup_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("DART_API_KEY", "k")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_YAML_NO_ACTIVE, encoding="utf-8")
    return cfg


class TestCli:
    def test_skip_when_outside_active_window(self, setup_env: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(setup_env),
                "--data",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "OUT_OF_HOURS" in result.stdout

    def test_unknown_option_returns_non_zero(self, setup_env: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--bogus-flag"])
        assert result.exit_code != 0
