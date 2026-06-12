"""k-stock 스킬 공용 데이터조회 라이브러리.

기존 kor_trading 헥사고날 코어(use case·도메인 서비스·어댑터)를 재사용해
실시간 단건 질의를 마크다운으로 반환한다. 스킬 스크립트가 import 한다.

- 시세 스냅샷: KRX OPEN API (전종목, 종목명·시총 포함)
- OHLCV: FinanceDataReader
- 수급: KIS Open API (외국인/기관)
- 공시: DART OpenAPI + 로컬 Claude 분류

시크릿은 .env에서만 로드한다(절대 하드코딩 금지).
실행: 프로젝트 루트에서 `uv run python <스킬>/scripts/run.py` (kor_trading import 가능).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys

import structlog

# stdlib 로그(httpx 등) 억제 + structlog는 stderr로 보내 stdout 마크다운을 깨끗하게 유지
logging.disable(logging.CRITICAL)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

from kor_trading.adapters.outbound.claude_code_classifier import (  # noqa: E402
    ClaudeCodeSentimentClassifier,
)
from kor_trading.adapters.outbound.dart_corp_code_resolver import (  # noqa: E402
    DartCorpCodeResolver,
)
from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider  # noqa: E402
from kor_trading.adapters.outbound.fdr_ohlcv import FdrOhlcvProvider  # noqa: E402
from kor_trading.adapters.outbound.kis_client import KisClient  # noqa: E402
from kor_trading.adapters.outbound.kis_investor_flow import (  # noqa: E402
    KisInvestorFlowProvider,
)
from kor_trading.adapters.outbound.krx_openapi_client import KrxOpenApiClient  # noqa: E402
from kor_trading.adapters.outbound.krx_openapi_market_snapshot import (  # noqa: E402
    KrxOpenApiMarketSnapshotProvider,
)
from kor_trading.application.dto.selection import SelectionCriteria  # noqa: E402
from kor_trading.application.use_cases.analyze_indicators import (  # noqa: E402
    AnalyzeIndicatorsUseCase,
)
from kor_trading.application.use_cases.analyze_issues import AnalyzeIssuesUseCase  # noqa: E402
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase  # noqa: E402
from kor_trading.domain.entities.ticker import Ticker  # noqa: E402
from kor_trading.domain.services.horizon_recommendation import (  # noqa: E402
    derive_horizon_recommendations,
)
from kor_trading.domain.services.indicator_explainer import (  # noqa: E402
    explain_indicators,
    summarize_signal,
)
from kor_trading.domain.services.risk_levels import (  # noqa: E402
    STANDARD_MULTIPLIER,
    TIGHT_MULTIPLIER,
    atr_stop_loss,
)
from kor_trading.domain.services.setup_classifier import classify_setups  # noqa: E402
from kor_trading.domain.values.trade_plan import suggested_shares  # noqa: E402
from kor_trading.infrastructure.config import Secrets  # noqa: E402

_MARKETS = ("KOSPI", "KOSDAQ")
_JO = 1_000_000_000_000
_EOK = 100_000_000

_LEVEL_LABEL = {
    "strong_buy": "🟢🟢 적극매수",
    "buy": "🟢 매수",
    "hold": "🟡 관망",
    "sell": "🔴 매도",
    "strong_sell": "🔴🔴 적극매도",
}
_HORIZON_LABEL = {
    "ultra_short": "초단기",
    "short": "단기",
    "medium": "중기",
    "long": "장기",
}

_universe_cache: list | None = None  # type: ignore[type-arg]


# ──────────────────────── 공통 ────────────────────────
def _secrets() -> Secrets:
    return Secrets()  # type: ignore[call-arg]


def today() -> dt.date:
    return dt.date.today()


def _fmt_won(won: int) -> str:
    if abs(won) >= _JO:
        return f"{won / _JO:,.1f}조"
    return f"{won / _EOK:,.0f}억"


def _market_provider() -> KrxOpenApiMarketSnapshotProvider:
    s = _secrets()
    return KrxOpenApiMarketSnapshotProvider(client=KrxOpenApiClient(auth_key=s.krx_api_key or ""))


def universe(as_of: dt.date):  # type: ignore[no-untyped-def]
    """전종목 스냅샷(KOSPI+KOSDAQ). 프로세스 내 캐시."""
    global _universe_cache
    if _universe_cache is None:
        _universe_cache = _market_provider().get_market_snapshots(_MARKETS, as_of)
    return _universe_cache


def resolve(query: str, as_of: dt.date):  # type: ignore[no-untyped-def]
    """종목명 또는 6자리 코드 → StockSnapshot. 없으면 None."""
    q = query.strip()
    snaps = universe(as_of)
    if q.isdigit() and len(q) == 6:
        for s in snaps:
            if s.ticker.code == q:
                return s
        return None
    # 이름: 정확 일치 우선, 없으면 부분 일치
    exact = [s for s in snaps if s.ticker.name == q]
    if exact:
        return exact[0]
    partial = [s for s in snaps if q in s.ticker.name]
    partial.sort(key=lambda s: s.trading_value, reverse=True)
    return partial[0] if partial else None


# ──────────────────────── 시장 개요 ────────────────────────
def market_md(as_of: dt.date) -> str:
    sel = SelectStocksUseCase(market_snapshots=_market_provider()).execute(
        SelectionCriteria(), as_of
    )
    ov = sel.overview
    lines = [f"## 📊 시장 개요 — {as_of.isoformat()}", ""]
    if ov is None or not ov.breadths:
        lines.append("_시장 데이터를 가져오지 못했습니다._")
        return "\n".join(lines)
    for b in ov.breadths:
        lines.append(
            f"- **{b.market}**: {b.sentiment} | "
            f"상승 {b.advancers} · 하락 {b.decliners} · 보합 {b.unchanged} "
            f"(총 {b.total}) | 평균 {b.avg_change_pct:+.2f}% | "
            f"거래대금 {_fmt_won(b.total_trading_value)}"
        )
    return "\n".join(lines)


# ──────────────────────── 무버스(급등·급락·거래량) ────────────────────────
def movers_md(as_of: dt.date) -> str:
    sel = SelectStocksUseCase(market_snapshots=_market_provider()).execute(
        SelectionCriteria(top_volume_n=15, surge_top_n=15, plunge_top_n=15), as_of
    )
    by_code = {c.snapshot.ticker.code: c for c in sel.candidates}

    def rows(key, reverse: bool):  # type: ignore[no-untyped-def]
        picked = [c for c in by_code.values() if key(c) is not None]
        picked.sort(key=key, reverse=reverse)  # type: ignore[arg-type,return-value]
        return picked[:10]

    out = [f"## 🔥 오늘의 무버스 — {as_of.isoformat()}", ""]
    out.append("### 거래대금 상위")
    out += _mover_table(rows(lambda c: c.rank_by_volume, reverse=False))
    out.append("")
    out.append("### 급등 상위")
    out += _mover_table(rows(lambda c: c.rank_by_change_up, reverse=False))
    out.append("")
    out.append("### 급락 상위")
    out += _mover_table(rows(lambda c: c.rank_by_change_down, reverse=False))
    return "\n".join(out)


def _mover_table(cands) -> list[str]:  # type: ignore[no-untyped-def]
    if not cands:
        return ["_해당 없음_"]
    lines = ["| 종목 | 코드 | 등락률 | 거래대금 |", "|------|------|--------|----------|"]
    for c in cands:
        s = c.snapshot
        lines.append(
            f"| {s.ticker.name} | {s.ticker.code} | {s.change_pct:+.2f}% "
            f"| {_fmt_won(s.trading_value)} |"
        )
    return lines


# ──────────────────────── 셋업 & 매매플랜 ────────────────────────
def _account() -> tuple[int, float] | None:
    """계좌 규모/리스크%를 env에서 읽어 포지션 사이징에 사용(옵션)."""
    raw = os.environ.get("KOR_TRADING_ACCOUNT_KRW")
    if not raw:
        return None
    try:
        acct = int(raw)
    except ValueError:
        return None
    try:
        risk = float(os.environ.get("KOR_TRADING_RISK_PCT", "1.0"))
    except ValueError:
        risk = 1.0
    return acct, risk


def _setup_section(isnap, close: int) -> list[str]:  # type: ignore[no-untyped-def]
    plans = classify_setups(isnap, close)
    if not plans:
        return [
            "### 🎯 셋업",
            "- **매칭 셋업 없음** — 지금은 뚜렷한 진입 셋업이 아니다(관망 권장).",
        ]
    acct = _account()
    lines = ["### 🎯 셋업 & 매매플랜"]
    for p in plans[:2]:  # 상위 2개 셋업
        lines.append(f"- **{p.setup}** (강도 {p.quality:.0%}) — {p.rationale}")
        lines.append(
            f"  - 진입 {p.entry:,} / 손절 {p.stop:,} ({p.stop_pct:+.1f}%) "
            f"/ 1차 {p.target1:,} / 2차 {p.target2:,} | 손익비 {p.reward_risk:.1f}:1"
        )
        if acct is not None:
            shares = suggested_shares(acct[0], acct[1], p.risk_per_share)
            lines.append(
                f"  - 비중: 계좌 {acct[0]:,}원·리스크 {acct[1]:.1f}% → 약 {shares:,}주 "
                f"(1주 리스크 {p.risk_per_share:,}원)"
            )
        lines.append(f"  - 무효화: {p.invalidation}")
    return lines


# ──────────────────────── 단일 종목 분석 ────────────────────────
def analyze_md(query: str, as_of: dt.date) -> str:
    snap = resolve(query, as_of)
    if snap is None:
        return f"❌ '{query}' 종목을 찾지 못했습니다. 종목명 또는 6자리 코드를 확인하세요."

    s = _secrets()
    kis = KisClient(
        app_key=s.kis_app_key,
        app_secret=s.kis_app_secret,
        virtual=s.kis_env == "virtual",
        token_cache_path=_cache_path() / "kis_token.json",
    )
    flow_provider = KisInvestorFlowProvider(client=kis) if kis.enabled else None
    analyze_uc = AnalyzeIndicatorsUseCase(
        ohlcv_provider=FdrOhlcvProvider(), flow_provider=flow_provider
    )
    ticker = Ticker(code=snap.ticker.code, name=snap.ticker.name, market=snap.ticker.market)
    data_date = snap.as_of  # KRX가 보정한 실제 거래일(휴장/주말 자동 처리)
    res = analyze_uc.execute([ticker], data_date)
    if not res.items:
        reason = res.errors[0].reason if res.errors else "데이터 부족"
        return f"❌ {ticker.name}({ticker.code}) 분석 실패: {reason}"

    item = res.items[0]
    isnap, scores = item.snapshot, item.scores
    recs = derive_horizon_recommendations(scores)

    out = [
        f"## 🔎 {ticker.name} ({ticker.code}) — {ticker.market}",
        f"- 현재가 {snap.close:,}원 | 등락률 {snap.change_pct:+.2f}% "
        f"| 거래대금 {_fmt_won(snap.trading_value)} | 시총 {_fmt_won(snap.market_cap)}",
        f"- 기준일: {data_date.isoformat()}",
        "",
        f"**종합 시그널**: {summarize_signal(isnap)}",
        "",
    ]
    out += _setup_section(isnap, snap.close)
    out += [
        "",
        "### 매매관점 4종(참고)",
        "| 관점 | 추천 | 점수 | 근거 |",
        "|------|------|------|------|",
    ]
    for h in ("ultra_short", "short", "medium", "long"):
        rec = recs.get(h)
        if rec is None:
            out.append(f"| {_HORIZON_LABEL[h]} | — | — | — |")
        else:
            out.append(
                f"| {_HORIZON_LABEL[h]} | {_LEVEL_LABEL.get(rec.level.value, rec.level.value)} "
                f"| {rec.score.value:+.2f} | {rec.rationale} |"
            )
    out.append("")
    out.append("### 지표 해석")
    out += [f"- {line}" for line in explain_indicators(isnap)]

    if isnap.atr_14 is not None:
        tight = atr_stop_loss(snap.close, isnap.atr_14, TIGHT_MULTIPLIER)
        std = atr_stop_loss(snap.close, isnap.atr_14, STANDARD_MULTIPLIER)
        out.append("")
        out.append("### 손절 가이드 (ATR 14)")
        out.append(f"- 타이트(1.5x ATR): {tight.price:,}원 ({tight.pct:+.1f}%)")
        out.append(f"- 표준(2.0x ATR): {std.price:,}원 ({std.pct:+.1f}%)")
    return "\n".join(out)


# ──────────────────────── 수급 ────────────────────────
def flow_md(query: str, as_of: dt.date) -> str:
    snap = resolve(query, as_of)
    if snap is None:
        return f"❌ '{query}' 종목을 찾지 못했습니다."
    s = _secrets()
    kis = KisClient(
        app_key=s.kis_app_key,
        app_secret=s.kis_app_secret,
        virtual=s.kis_env == "virtual",
        token_cache_path=_cache_path() / "kis_token.json",
    )
    if not kis.enabled:
        return "❌ KIS 앱키가 설정되지 않아 수급을 조회할 수 없습니다(.env 확인)."
    flows = KisInvestorFlowProvider(client=kis).get_flows([snap.ticker.code], snap.as_of)
    f = flows.get(snap.ticker.code)
    if f is None:
        return f"❌ {snap.ticker.name}({snap.ticker.code}) 수급 데이터를 가져오지 못했습니다."

    def part(v: int | None) -> str:
        # 값은 백만원 단위(KIS *_ntby_tr_pbmn). 1억 = 100백만원 → ÷100.
        if v is None:
            return "—"
        mark = "순매수" if v > 0 else "순매도" if v < 0 else "중립"
        return f"{mark} {v / 100:+,.0f}억"

    def line(label: str, v5: int | None, v20: int | None) -> str:
        return f"- **{label}**: 5일 {part(v5)} | 20일 {part(v20)}"

    return "\n".join(
        [
            f"## 💰 {snap.ticker.name} ({snap.ticker.code}) 수급 — {snap.as_of.isoformat()}",
            line("외국인", f.foreign_net_5d, f.foreign_net_20d),
            line("기관", f.institution_net_5d, f.institution_net_20d),
        ]
    )


# ──────────────────────── 공시 ────────────────────────
def disclosures_md(query: str, as_of: dt.date, lookback_days: int = 14) -> str:
    snap = resolve(query, as_of)
    if snap is None:
        return f"❌ '{query}' 종목을 찾지 못했습니다."
    s = _secrets()
    resolver = DartCorpCodeResolver(
        api_key=s.dart_api_key, cache_path=_cache_path() / "corp_code.json"
    )
    provider = DartDisclosureProvider(
        api_key=s.dart_api_key, ticker_to_corp_code=resolver.get_all_mapping()
    )
    issues_uc = AnalyzeIssuesUseCase(
        disclosure_provider=provider, classifier=ClaudeCodeSentimentClassifier()
    )
    ticker = Ticker(code=snap.ticker.code, name=snap.ticker.name, market=snap.ticker.market)
    res = issues_uc.execute([ticker], snap.as_of, lookback_days=lookback_days)
    items = res.items
    head = f"## 📰 {ticker.name} ({ticker.code}) 공시 — 최근 {lookback_days}일"
    if not items or not items[0].issues:
        return f"{head}\n\n_분류 대상 공시가 없습니다(노이즈 공시 제외)._"

    mark = {"positive": "🟢 호재", "negative": "🔴 악재", "neutral": "⚪ 중립"}
    lines = [head, ""]
    for issue in items[0].issues:
        m = mark.get(issue.sentiment.value, issue.sentiment.value)
        lines.append(
            f"- [{issue.date:%m/%d}, {m}/{issue.impact.value}] {issue.title}"
        )
        lines.append(f"  - {issue.summary} (신뢰도 {issue.confidence:.2f})")
    return "\n".join(lines)


def _cache_path():  # type: ignore[no-untyped-def]
    import pathlib

    return pathlib.Path("data") / "cache"
