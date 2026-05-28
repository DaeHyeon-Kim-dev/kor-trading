"""FileSystemReportRepository 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kor_trading.adapters.outbound.filesystem_report_repository import (
    FileSystemReportRepository,
)
from kor_trading.domain.ports.report_repository import ReportRepository

if TYPE_CHECKING:
    from pathlib import Path


class TestSaveReport:
    def test_creates_report_md_under_run_dir(self, tmp_path: Path) -> None:
        repo = FileSystemReportRepository(base_path=tmp_path)
        path = repo.save_report(run_id="2026-05-26/1430", report_md="# hello")
        assert path == tmp_path / "2026-05-26" / "1430" / "report.md"
        assert path.read_text(encoding="utf-8") == "# hello"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        repo = FileSystemReportRepository(base_path=tmp_path)
        repo.save_report("r1", "v1")
        repo.save_report("r1", "v2")
        assert (tmp_path / "r1" / "report.md").read_text(encoding="utf-8") == "v2"


class TestSaveEvidence:
    def test_under_evidence_subdir(self, tmp_path: Path) -> None:
        repo = FileSystemReportRepository(base_path=tmp_path)
        path = repo.save_evidence("r1", "005930", "## body")
        assert path == tmp_path / "r1" / "evidence" / "005930.md"
        assert path.read_text(encoding="utf-8") == "## body"


class TestSaveRaw:
    def test_under_raw_kind_subdir(self, tmp_path: Path) -> None:
        repo = FileSystemReportRepository(base_path=tmp_path)
        path = repo.save_raw("r1", "indicators", "005930.json", '{"x":1}')
        assert path == tmp_path / "r1" / "raw" / "indicators" / "005930.json"
        assert path.read_text(encoding="utf-8") == '{"x":1}'


class TestProtocolConformance:
    def test_conforms_to_report_repository(self, tmp_path: Path) -> None:
        repo = FileSystemReportRepository(base_path=tmp_path)
        assert isinstance(repo, ReportRepository)
