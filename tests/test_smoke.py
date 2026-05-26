"""Smoke test — 패키지가 import 가능한지만 검증."""

import kor_trading


def test_package_imports() -> None:
    assert kor_trading.__version__ == "0.1.0"
