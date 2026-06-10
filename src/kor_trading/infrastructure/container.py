"""Composition Root — 모든 어댑터/유스케이스를 연결.

이 모듈만 모든 구체 어댑터를 안다. domain/application은 의존하지 않음.

시세 데이터:
- 종목 선정 스냅샷: KRX OPEN API (당일 전종목, 종목명·시총 포함)
- 지표용 OHLCV 시계열: FinanceDataReader (개별종목 1회 호출)
- 외국인/기관 수급: 현재 비활성 (KRX OPEN API에 미제공, 추후 별도 소스)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kor_trading.adapters.outbound.claude_code_classifier import (
    ClaudeCodeSentimentClassifier,
)
from kor_trading.adapters.outbound.dart_corp_code_resolver import DartCorpCodeResolver
from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider
from kor_trading.adapters.outbound.fdr_ohlcv import FdrOhlcvProvider
from kor_trading.adapters.outbound.filesystem_report_repository import (
    FileSystemReportRepository,
)
from kor_trading.adapters.outbound.kis_client import KisClient
from kor_trading.adapters.outbound.kis_investor_flow import KisInvestorFlowProvider
from kor_trading.adapters.outbound.krx_openapi_client import KrxOpenApiClient
from kor_trading.adapters.outbound.krx_openapi_market_snapshot import (
    KrxOpenApiMarketSnapshotProvider,
)
from kor_trading.adapters.outbound.telegram_notifier import TelegramNotifier
from kor_trading.application.use_cases.analyze_indicators import AnalyzeIndicatorsUseCase
from kor_trading.application.use_cases.analyze_issues import AnalyzeIssuesUseCase
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

    krx_client = KrxOpenApiClient(auth_key=secrets.krx_api_key or "")
    market_provider = KrxOpenApiMarketSnapshotProvider(client=krx_client)
    ohlcv_provider = FdrOhlcvProvider()
    # 외국인/기관 수급 — KIS 앱키가 있으면 활성, 없으면 None(비활성)
    kis_client = KisClient(
        app_key=secrets.kis_app_key,
        app_secret=secrets.kis_app_secret,
        virtual=secrets.kis_env == "virtual",
    )
    flow_provider = KisInvestorFlowProvider(client=kis_client) if kis_client.enabled else None
    corp_code_resolver = DartCorpCodeResolver(
        api_key=secrets.dart_api_key,
        cache_path=data_base_path / "cache" / "corp_code.json",
    )
    disclosure_provider = DartDisclosureProvider(
        api_key=secrets.dart_api_key,
        ticker_to_corp_code=corp_code_resolver.get_all_mapping(),
    )
    classifier = ClaudeCodeSentimentClassifier()
    repository = FileSystemReportRepository(base_path=data_base_path / "reports")
    notifier = TelegramNotifier(
        bot_token=secrets.telegram_bot_token, chat_id=secrets.telegram_chat_id
    )

    select_uc = SelectStocksUseCase(market_snapshots=market_provider)
    analyze_uc = AnalyzeIndicatorsUseCase(
        ohlcv_provider=ohlcv_provider, flow_provider=flow_provider
    )
    issues_uc = AnalyzeIssuesUseCase(disclosure_provider=disclosure_provider, classifier=classifier)
    report_uc = GenerateReportUseCase(repository=repository, notifier=notifier)

    pipeline = RunPipelineUseCase(
        select_stocks=select_uc,
        analyze_indicators=analyze_uc,
        generate_report=report_uc,
        analyze_issues=issues_uc,
    )
    return AppContainer(pipeline=pipeline)
