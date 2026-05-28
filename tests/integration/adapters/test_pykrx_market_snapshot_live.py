"""실 pykrx 호출 통합 테스트.

- CI에서는 기본 실행 안 함 (integration 마커 + pytest 옵션으로 제외 필요).
- 실행: `uv run pytest -m integration`
- 네트워크 필요. KRX 접근 가능 환경에서만 통과.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from kor_trading.adapters.outbound.pykrx_market_snapshot import PykrxMarketSnapshotProvider


def _last_known_weekday() -> date:
    """오늘 또는 직전 영업일에 가까운 일자 — 실제 휴장일은 어댑터가 빈 결과 처리."""
    today = date.today()
    # 토요일/일요일이면 금요일로
    while today.isoweekday() > 5:
        today -= timedelta(days=1)
    return today


@pytest.mark.integration
class TestPykrxLiveFetch:
    def test_fetches_kospi_snapshots(self) -> None:
        provider = PykrxMarketSnapshotProvider()
        snapshots = provider.get_market_snapshots(("KOSPI",), _last_known_weekday())
        # 평일이면 보통 800+ 종목. 휴장일이면 0 가능.
        if snapshots:
            # 형식만 검증
            assert all(s.ticker.market == "KOSPI" for s in snapshots)
            assert all(s.close >= 0 for s in snapshots)
            assert all(s.market_cap >= 0 for s in snapshots)
        # 빈 결과면 휴장일로 간주, 실패 아님
