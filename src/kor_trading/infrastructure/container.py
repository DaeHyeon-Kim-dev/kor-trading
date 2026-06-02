"""Composition Root — 모든 어댑터/유스케이스를 연결.

이 모듈만 모든 구체 어댑터를 안다. domain/application은 의존하지 않음.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kor_trading.adapters.outbound.dart_corp_code_resolver import DartCorpCodeResolver
from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider
from kor_trading.adapters.outbound.fdr_ticker_name_resolver import (
    FinanceDataReaderNameResolver,
)
from kor_trading.adapters.outbound.filesystem_report_repository import (
    FileSystemReportRepository,
)
from kor_trading.adapters.outbound.pykrx_investor_flow import PykrxInvestorFlowProvider
from kor_trading.adapters.outbound.pykrx_market_snapshot import (
    PykrxMarketSnapshotProvider,
)
from kor_trading.adapters.outbound.pykrx_ohlcv import PykrxOhlcvProvider
from kor_trading.adapters.outbound.telegram_notifier import TelegramNotifier
from kor_trading.application.use_cases.analyze_indicators import AnalyzeIndicatorsUseCase
from kor_trading.application.use_cases.generate_report import GenerateReportUseCase
from kor_trading.application.use_cases.run_pipeline import RunPipelineUseCase
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase

if TYPE_CHECKING:
    from pathlib import Path

    from kor_trading.infrastructure.config import AppConfig, Secrets


@dataclass(frozen=True, slots=True)
class AppContainer:
    pipeline: RunPipelineUseCase


def build_container(config: AppConfig, secrets: Secrets, data_base_path: Path) -> AppContainer:
    """Composition Root: 어댑터 ↔ 유스케이스 연결."""
    _ = config  # 추후 use case별 옵션 주입 시 사용

    name_resolver = FinanceDataReaderNameResolver()
    market_provider = PykrxMarketSnapshotProvider(name_resolver=name_resolver)
    ohlcv_provider = PykrxOhlcvProvider()
    flow_provider = PykrxInvestorFlowProvider()
    corp_code_resolver = DartCorpCodeResolver(
        api_key=secrets.dart_api_key,
        cache_path=data_base_path / "cache" / "corp_code.json",
    )
    disclosure_provider = DartDisclosureProvider(
        api_key=secrets.dart_api_key,
        ticker_to_corp_code=corp_code_resolver.get_all_mapping(),
    )
    _ = disclosure_provider  # AnalyzeIssuesUseCase 도입 후 wiring
    repository = FileSystemReportRepository(base_path=data_base_path / "reports")
    notifier = TelegramNotifier(
        bot_token=secrets.telegram_bot_token, chat_id=secrets.telegram_chat_id
    )

    select_uc = SelectStocksUseCase(market_snapshots=market_provider)
    analyze_uc = AnalyzeIndicatorsUseCase(
        ohlcv_provider=ohlcv_provider, flow_provider=flow_provider
    )
    report_uc = GenerateReportUseCase(repository=repository, notifier=notifier)

    pipeline = RunPipelineUseCase(
        select_stocks=select_uc,
        analyze_indicators=analyze_uc,
        generate_report=report_uc,
    )
    return AppContainer(pipeline=pipeline)
