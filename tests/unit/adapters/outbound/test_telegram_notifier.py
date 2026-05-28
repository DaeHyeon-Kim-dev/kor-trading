"""TelegramNotifier 단위 테스트 — respx로 HTTP mock."""

from __future__ import annotations

import httpx
import pytest
import respx

from kor_trading.adapters.outbound.telegram_notifier import TelegramNotifier
from kor_trading.domain.ports.notifier import Notifier

BOT_TOKEN = "test-token"
CHAT_ID = "123456"


def _make() -> TelegramNotifier:
    return TelegramNotifier(bot_token=BOT_TOKEN, chat_id=CHAT_ID, http_client=httpx.Client())


class TestConstruction:
    def test_rejects_empty_token(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            TelegramNotifier(bot_token="", chat_id=CHAT_ID)

    def test_rejects_empty_chat_id(self) -> None:
        with pytest.raises(ValueError, match="chat_id"):
            TelegramNotifier(bot_token=BOT_TOKEN, chat_id="")


class TestSendMessage:
    @respx.mock
    def test_posts_text_to_send_message(self) -> None:
        route = respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        _make().send_message("hello world")

        assert route.called
        body = dict(httpx.QueryParams(route.calls.last.request.content.decode()))
        assert body["chat_id"] == CHAT_ID
        assert body["text"] == "hello world"
        assert body["parse_mode"] == "Markdown"

    @respx.mock
    def test_empty_text_is_noop(self) -> None:
        route = respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(200)
        )
        _make().send_message("")
        assert not route.called

    @respx.mock
    def test_http_error_raises(self) -> None:
        respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(httpx.HTTPError):
            _make().send_message("x")


class TestMessageSplit:
    @respx.mock
    def test_splits_long_message_on_newline_boundary(self) -> None:
        route = respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(200)
        )
        long_text = "a" * 3000 + "\n" + "b" * 3000  # > 4096
        _make().send_message(long_text)
        assert route.call_count == 2

    @respx.mock
    def test_splits_long_message_without_newline_at_limit(self) -> None:
        # 줄바꿈 없는 거대 텍스트 → 강제로 limit 위치에서 잘림
        route = respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(200)
        )
        _make().send_message("x" * 5000)
        assert route.call_count == 2


class TestSendDocument:
    @respx.mock
    def test_posts_multipart_with_caption(self) -> None:
        route = respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        _make().send_document("report.md", b"# hello", caption="full report")

        assert route.called
        req = route.calls.last.request
        # multipart body should contain filename + caption
        body_str = req.content.decode("utf-8", errors="ignore")
        assert "report.md" in body_str
        assert "full report" in body_str

    @respx.mock
    def test_http_error_raises(self) -> None:
        respx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(httpx.HTTPError):
            _make().send_document("x.md", b"y")


class TestProtocolConformance:
    def test_conforms_to_notifier(self) -> None:
        assert isinstance(_make(), Notifier)
