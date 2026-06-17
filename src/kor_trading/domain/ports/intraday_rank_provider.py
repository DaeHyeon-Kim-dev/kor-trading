"""장중 실시간 순위 조회 포트.

KRX 일별매매정보(EOD)와 달리, 장중 실시간 거래대금/거래량 상위 종목을 제공한다.
어댑터(예: KIS 거래량순위 API)가 구현하며, 도메인은 추상에만 의존한다.
"""

from datetime import date
from typing import Protocol, runtime_checkable

from kor_trading.domain.entities.stock_snapshot import StockSnapshot
from kor_trading.domain.entities.ticker import Market


@runtime_checkable
class IntradayRankProvider(Protocol):
    """장중 실시간 순위 제공 포트.

    EOD 스냅샷이 아니라 '지금 이 순간'의 순위를 반환한다(휴장/마감 후엔 직전 값).
    반환 스냅샷은 trading_value 내림차순 정렬, 여러 시장을 합쳐 상위 limit개.
    조회 실패·미제공 시장은 결과에서 생략한다(빈 리스트 가능).
    """

    def top_by_trading_value(
        self, markets: tuple[Market, ...], as_of: date, limit: int = 20
    ) -> list[StockSnapshot]: ...
