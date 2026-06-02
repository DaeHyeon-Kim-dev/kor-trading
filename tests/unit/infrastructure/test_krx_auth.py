"""configure_krx_login 테스트."""

from __future__ import annotations

import os

import pytest

from kor_trading.infrastructure.krx_auth import configure_krx_login


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)


class TestConfigureKrxLogin:
    def test_sets_env_when_both_provided(self) -> None:
        ok = configure_krx_login("my-id", "my-pw")
        assert ok is True
        assert os.environ["KRX_ID"] == "my-id"
        assert os.environ["KRX_PW"] == "my-pw"

    def test_returns_false_when_id_missing(self) -> None:
        assert configure_krx_login(None, "pw") is False
        assert "KRX_ID" not in os.environ

    def test_returns_false_when_pw_missing(self) -> None:
        assert configure_krx_login("id", None) is False

    def test_returns_false_when_both_none(self) -> None:
        assert configure_krx_login(None, None) is False

    def test_empty_string_treated_as_missing(self) -> None:
        assert configure_krx_login("", "") is False
