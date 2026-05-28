"""structlog 설정 테스트."""

import json
import logging

import pytest
import structlog

from kor_trading.infrastructure.logging import configure_logging


class TestConfigureLogging:
    def test_emits_json_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO")
        log = structlog.get_logger("test")
        log.info("hello.event", market="KOSPI", count=42)
        captured = capsys.readouterr()
        line = captured.out.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["event"] == "hello.event"
        assert payload["market"] == "KOSPI"
        assert payload["count"] == 42
        assert payload["level"] == "info"
        assert "timestamp" in payload

    def test_filters_below_threshold(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="WARNING")
        log = structlog.get_logger("test")
        log.info("ignored.event")
        log.warning("important.event")
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if line]
        assert all("ignored.event" not in line for line in lines)
        assert any("important.event" in line for line in lines)

    def test_rejects_invalid_level(self) -> None:
        with pytest.raises((AttributeError, ValueError)):
            configure_logging(level="BOGUS")

    def test_is_idempotent(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO")
        configure_logging(level="INFO")
        log = structlog.get_logger("test")
        log.info("twice.event")
        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().splitlines() if "twice.event" in line]
        assert len(lines) == 1


class TestLoggingIntegrationWithStdlib:
    def test_stdlib_loggers_also_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="DEBUG")
        stdlib_log = logging.getLogger("test.stdlib")
        stdlib_log.info("stdlib.event")
        captured = capsys.readouterr()
        assert "stdlib.event" in captured.out or captured.err
