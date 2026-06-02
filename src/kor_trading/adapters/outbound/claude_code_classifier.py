"""Claude Code(`claude -p`) subprocess 기반 SentimentClassifier.

Claude Max 구독으로 처리 → 추가 토큰 비용 0.
`claude -p --output-format json --model <haiku>`를 호출하고 result JSON을 파싱.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Protocol

import structlog

from kor_trading.domain.entities.issue import Impact, Sentiment
from kor_trading.domain.ports.sentiment_classifier import Classification


class SubprocessRunner(Protocol):
    def __call__(self, cmd: list[str], stdin: str, timeout_s: int) -> str: ...


log = structlog.get_logger()

_DEFAULT_MODEL = "claude-haiku-4-5"
_DEFAULT_TIMEOUT_S = 60

_PROMPT_TEMPLATE = """\
다음 한국 주식 공시/뉴스를 분석해 JSON으로만 답해. 다른 말 절대 금지.

제목: {title}
{context_line}

형식 (정확히 이 키):
{{"sentiment": "positive|negative|neutral", "impact": "high|medium|low", \
"confidence": 0.0~1.0, "summary": "한 문장 한국어 요약"}}

판정 기준:
- impact high: 실적, 대규모 공급계약, 횡령·배임, 상장폐지 사유
- impact medium: 유상증자, CB, 자사주, 임원 변경
- impact low: 단순 동향, 시황
"""


class ClaudeCodeSentimentClassifier:
    """`claude -p` subprocess 호출. DI 가능한 runner로 단위 테스트."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
        runner: SubprocessRunner | None = None,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._runner = runner if runner is not None else _default_runner

    def classify(self, title: str, *, context: str | None = None) -> Classification | None:
        if not title.strip():
            return None
        prompt = _PROMPT_TEMPLATE.format(
            title=title,
            context_line=f"본문: {context}" if context else "",
        )
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            self._model,
        ]
        try:
            stdout = self._runner(cmd, prompt, self._timeout_s)
        except (subprocess.SubprocessError, OSError) as e:
            log.error("claude_classifier.subprocess_failed", error=str(e))
            return None

        return _parse_result(stdout)


def _parse_result(stdout: str) -> Classification | None:
    try:
        envelope = json.loads(stdout)
        result_text = envelope.get("result", "")
        payload = _extract_json_object(result_text)
        if payload is None:
            log.warning("claude_classifier.no_json_in_result", result=result_text[:200])
            return None
        return Classification(
            sentiment=Sentiment(str(payload["sentiment"])),
            impact=Impact(str(payload["impact"])),
            confidence=float(payload["confidence"]),  # type: ignore[arg-type]
            summary=str(payload["summary"]),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("claude_classifier.parse_failed", error=str(e))
        return None


def _extract_json_object(text: str) -> dict[str, object] | None:
    """result 문자열에서 첫 번째 JSON 객체 추출 (코드블록/잡텍스트 허용)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):  # pragma: no cover (방어 — {..} 슬라이스는 항상 dict/에러)
        return None
    return parsed


def _default_runner(cmd: list[str], stdin: str, timeout_s: int) -> str:  # pragma: no cover
    if shutil.which(cmd[0]) is None:
        raise OSError(f"executable not found: {cmd[0]}")
    completed = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=True,
    )
    return completed.stdout
