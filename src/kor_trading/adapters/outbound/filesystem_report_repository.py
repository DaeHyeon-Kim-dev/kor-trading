"""파일시스템 기반 ReportRepository.

PRD § 5 — data/reports/{YYYY-MM-DD}/{HHmm}/ 디렉토리 구조.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path


log = structlog.get_logger()


class FileSystemReportRepository:
    """data/reports/{run_id}/ 하위에 마크다운/JSON 저장.

    run_id 예: "2026-05-26/1430"
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def save_report(self, run_id: str, report_md: str) -> Path:
        path = self._run_dir(run_id) / "report.md"
        self._write_text(path, report_md)
        return path

    def save_evidence(self, run_id: str, ticker_code: str, content_md: str) -> Path:
        path = self._run_dir(run_id) / "evidence" / f"{ticker_code}.md"
        self._write_text(path, content_md)
        return path

    def save_raw(self, run_id: str, kind: str, name: str, content: str) -> Path:
        path = self._run_dir(run_id) / "raw" / kind / name
        self._write_text(path, content)
        return path

    def _run_dir(self, run_id: str) -> Path:
        return self._base / run_id

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log.debug("report.saved", path=str(path), bytes=len(content))
