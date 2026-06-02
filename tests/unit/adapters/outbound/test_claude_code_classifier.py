"""ClaudeCodeSentimentClassifier 단위 테스트 (DI runner — 실 subprocess 없음)."""

from __future__ import annotations

import json
import subprocess

from kor_trading.adapters.outbound.claude_code_classifier import (
    ClaudeCodeSentimentClassifier,
)
from kor_trading.domain.entities.issue import Impact, Sentiment
from kor_trading.domain.ports.sentiment_classifier import SentimentClassifier


def _envelope(result_text: str) -> str:
    return json.dumps({"type": "result", "result": result_text})


def _make(
    runner_output: str | None = None, raise_exc: Exception | None = None
) -> tuple[ClaudeCodeSentimentClassifier, list[tuple[list[str], str]]]:
    calls: list[tuple[list[str], str]] = []

    def runner(cmd: list[str], stdin: str, timeout_s: int) -> str:
        _ = timeout_s
        calls.append((cmd, stdin))
        if raise_exc is not None:
            raise raise_exc
        return runner_output or ""

    classifier = ClaudeCodeSentimentClassifier(runner=runner)
    return classifier, calls


class TestClassify:
    def test_parses_clean_json_result(self) -> None:
        result = json.dumps(
            {
                "sentiment": "positive",
                "impact": "high",
                "confidence": 0.95,
                "summary": "어닝 서프라이즈",
            },
            ensure_ascii=False,
        )
        clf, _ = _make(runner_output=_envelope(result))
        out = clf.classify("1분기 영업이익 사상 최대")
        assert out is not None
        assert out.sentiment == Sentiment.POSITIVE
        assert out.impact == Impact.HIGH
        assert out.confidence == 0.95
        assert out.summary == "어닝 서프라이즈"

    def test_extracts_json_from_codeblock_or_noise(self) -> None:
        inner = json.dumps(
            {"sentiment": "negative", "impact": "medium", "confidence": 0.7, "summary": "유상증자"},
            ensure_ascii=False,
        )
        result = f"설명입니다\n```json\n{inner}\n```"
        clf, _ = _make(runner_output=_envelope(result))
        out = clf.classify("유상증자 결정")
        assert out is not None
        assert out.sentiment == Sentiment.NEGATIVE
        assert out.impact == Impact.MEDIUM

    def test_passes_model_and_format_flags(self) -> None:
        result = '{"sentiment":"neutral","impact":"low","confidence":0.5,"summary":"동향"}'
        clf, calls = _make(runner_output=_envelope(result))
        clf.classify("단순 시황")
        cmd = calls[0][0]
        assert "claude" in cmd[0]
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd

    def test_includes_context_in_prompt(self) -> None:
        result = '{"sentiment":"neutral","impact":"low","confidence":0.5,"summary":"x"}'
        clf, calls = _make(runner_output=_envelope(result))
        clf.classify("제목", context="추가 본문 내용")
        stdin = calls[0][1]
        assert "추가 본문 내용" in stdin


class TestEdgeCases:
    def test_empty_title_returns_none_without_call(self) -> None:
        clf, calls = _make(runner_output=_envelope("{}"))
        assert clf.classify("   ") is None
        assert calls == []

    def test_subprocess_error_returns_none(self) -> None:
        clf, _ = _make(raise_exc=subprocess.TimeoutExpired(cmd="claude", timeout=60))
        assert clf.classify("제목") is None

    def test_os_error_returns_none(self) -> None:
        clf, _ = _make(raise_exc=OSError("not found"))
        assert clf.classify("제목") is None

    def test_invalid_envelope_json_returns_none(self) -> None:
        clf, _ = _make(runner_output="not json at all")
        assert clf.classify("제목") is None

    def test_result_without_json_object_returns_none(self) -> None:
        clf, _ = _make(runner_output=_envelope("판단 불가"))
        assert clf.classify("제목") is None

    def test_result_json_array_not_object_returns_none(self) -> None:
        # result에 객체가 아닌 배열이 온 경우
        clf, _ = _make(runner_output=_envelope('["positive", "high"]'))
        assert clf.classify("제목") is None

    def test_invalid_sentiment_value_returns_none(self) -> None:
        result = '{"sentiment":"happy","impact":"high","confidence":0.9,"summary":"x"}'
        clf, _ = _make(runner_output=_envelope(result))
        assert clf.classify("제목") is None

    def test_missing_key_returns_none(self) -> None:
        result = '{"sentiment":"positive","impact":"high"}'  # confidence/summary 누락
        clf, _ = _make(runner_output=_envelope(result))
        assert clf.classify("제목") is None


class TestProtocolConformance:
    def test_conforms_to_sentiment_classifier(self) -> None:
        clf, _ = _make(runner_output=_envelope("{}"))
        assert isinstance(clf, SentimentClassifier)
