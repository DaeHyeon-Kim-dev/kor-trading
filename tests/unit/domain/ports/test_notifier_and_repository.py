"""Notifier / ReportRepository Protocol 부합 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.domain.ports.notifier import Notifier
from kor_trading.domain.ports.report_repository import ReportRepository

if TYPE_CHECKING:
    from pathlib import Path


class _StubNotifier:
    def send_message(self, text: str) -> None:
        _ = text

    def send_document(self, filename: str, content: bytes, caption: str | None = None) -> None:
        _ = (filename, content, caption)


class _StubRepo:
    def __init__(self, base: Path) -> None:
        self._base = base

    def save_report(self, run_id: str, report_md: str) -> Path:
        _ = (run_id, report_md)
        return self._base / "report.md"

    def save_evidence(self, run_id: str, ticker_code: str, content_md: str) -> Path:
        _ = (run_id, ticker_code, content_md)
        return self._base / "evidence.md"

    def save_raw(self, run_id: str, kind: str, name: str, content: str) -> Path:
        _ = (run_id, kind, name, content)
        return self._base / "raw.json"


class TestProtocols:
    def test_stub_notifier_conforms(self) -> None:
        assert isinstance(_StubNotifier(), Notifier)

    def test_stub_repo_conforms(self, tmp_path: Path) -> None:
        assert isinstance(_StubRepo(tmp_path), ReportRepository)
