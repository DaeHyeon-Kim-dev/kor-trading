"""리포트·근거 영구 저장 포트."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


@runtime_checkable
class ReportRepository(Protocol):
    """run_id 디렉토리 하위에 마크다운/raw JSON 저장.

    구조: {base_path}/{YYYY-MM-DD}/{HHmm}/{...}
    PRD: docs/PRD.md § 5.
    """

    def save_report(self, run_id: str, report_md: str) -> Path: ...

    def save_evidence(self, run_id: str, ticker_code: str, content_md: str) -> Path: ...

    def save_raw(self, run_id: str, kind: str, name: str, content: str) -> Path: ...
