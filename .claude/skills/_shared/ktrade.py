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
from kor_trading.domain.services.position_advisor import manage_position  # noqa: E402
from kor_trading.domain.services.setup_classifier import classify_setups  # noqa: E402
from kor_trading.domain.values.market_overview import overall_regime  # noqa: E402
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


# ──────────────────────── 추천 스크리너 ────────────────────────
# 실데이터 백테스트(2024~2025·18종목·88거래, 거래비용·갭 반영) 측정 기대값.
_SETUP_EXPECTANCY = {"돌파": 0.53, "추세 눌림목": 0.26, "과매도 반등": 0.17}


def screen_md(as_of: dt.date, top_n: int = 8) -> str:
    sel = SelectStocksUseCase(market_snapshots=_market_provider()).execute(
        SelectionCriteria(top_volume_n=60, surge_top_n=25, plunge_top_n=15), as_of
    )
    if not sel.candidates:
        return "❌ 후보 종목을 가져오지 못했습니다."
    regime = overall_regime(sel.overview) if sel.overview is not None else "혼조"
    data_date = sel.candidates[0].snapshot.as_of

    # 수급은 속도·KIS 호출량 고려해 미반영(가격 기반 셋업 위주). 개별은 /k-analyze.
    analyze_uc = AnalyzeIndicatorsUseCase(ohlcv_provider=FdrOhlcvProvider(), flow_provider=None)
    tickers = [
        Ticker(code=c.snapshot.ticker.code, name=c.snapshot.ticker.name, market=c.snapshot.ticker.market)
        for c in sel.candidates
    ]
    res = analyze_uc.execute(tickers, data_date)
    by_code = {it.snapshot.ticker.code: it.snapshot for it in res.items}

    rows = []
    for c in sel.candidates:
        isnap = by_code.get(c.snapshot.ticker.code)
        if isnap is None:
            continue
        plans = classify_setups(isnap, c.snapshot.close)
        if plans:
            rows.append((c, plans[0]))
    rows.sort(
        key=lambda r: (
            _SETUP_EXPECTANCY.get(r[1].setup) is not None,
            _SETUP_EXPECTANCY.get(r[1].setup, 0.0),
            r[1].quality,
        ),
        reverse=True,
    )

    warn = " ⚠️ 약세장 — 롱 신호는 비중 축소·엄격 손절" if regime == "약세" else ""
    out = [
        f"## 🛒 지금 매수할 만한 종목 — {data_date.isoformat()}",
        f"- 시장 레짐: **{regime}**{warn}",
        f"- 스캔 {len(sel.candidates)}종목 중 셋업 매칭 {len(rows)}종목",
        "",
    ]
    if not rows:
        out.append("**현재 매수 셋업이 잡힌 종목 없음 — 관망 권장.**")
        return "\n".join(out)
    out += [
        "| 종목 | 셋업 | 강도 | 과거기대값 | 진입 | 손절(%) | 1차목표 | 손익비 |",
        "|------|------|------|-----------|------|---------|---------|--------|",
    ]
    wide_any = False
    for c, p in rows[:top_n]:
        exp = _SETUP_EXPECTANCY.get(p.setup)
        exp_s = f"+{exp}R" if exp is not None else "미검증"
        wide = p.stop_pct < -12.0  # 고변동성 → 비중 축소 경고
        wide_any = wide_any or wide
        name = f"{'⚠️ ' if wide else ''}{c.snapshot.ticker.name}({c.snapshot.ticker.code})"
        out.append(
            f"| {name} | {p.setup} | {p.quality:.0%} "
            f"| {exp_s} | {p.entry:,} | {p.stop:,}({p.stop_pct:+.1f}%) | {p.target1:,} "
            f"| {p.reward_risk:.1f} |"
        )
    if len(rows) > top_n:
        out.append(f"\n_…외 {len(rows) - top_n}종목. 개별 상세는 /k-analyze <종목>._")
    if wide_any:
        out.append(
            "\n_⚠️ = 손절폭 >12%(고변동성). 손절을 좁히지 말고 **비중을 줄여** 대응 "
            "(계좌리스크 1% ÷ 넓은 손절폭 = 작은 수량)._"
        )
    out += [
        "",
        "_과거기대값 = 실데이터 2024~2025 백테스트(거래비용·갭 반영). 수급 미반영(개별은 /k-analyze)._",
    ]
    return "\n".join(out)


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


def _setup_section(plans) -> list[str]:  # type: ignore[no-untyped-def]
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
def _indicator_analysis(snap):  # type: ignore[no-untyped-def]
    """종목 스냅샷 → (IndicatorSnapshot, IndicatorScores) | None. 분석·관리 공용."""
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
    res = analyze_uc.execute([ticker], snap.as_of)  # snap.as_of = 실제 거래일
    if not res.items:
        return None
    return res.items[0].snapshot, res.items[0].scores


def analyze_md(query: str, as_of: dt.date) -> str:
    snap = resolve(query, as_of)
    if snap is None:
        return f"❌ '{query}' 종목을 찾지 못했습니다. 종목명 또는 6자리 코드를 확인하세요."

    analysis = _indicator_analysis(snap)
    if analysis is None:
        return f"❌ {snap.ticker.name}({snap.ticker.code}) 분석 실패: 데이터 부족"
    isnap, scores = analysis
    recs = derive_horizon_recommendations(scores)
    plans = classify_setups(isnap, snap.close)
    verdict = (
        f"🟢 매수 적정 — {plans[0].setup} 셋업"
        if plans
        else "⚪ 매수 부적정 — 매칭 셋업 없음(관망 권장)"
    )

    out = [
        f"## 🔎 {snap.ticker.name} ({snap.ticker.code}) — {snap.ticker.market}",
        f"- 현재가 {snap.close:,}원 | 등락률 {snap.change_pct:+.2f}% "
        f"| 거래대금 {_fmt_won(snap.trading_value)} | 시총 {_fmt_won(snap.market_cap)}",
        f"- 기준일: {snap.as_of.isoformat()}",
        "",
        f"**💡 현재가 매수 판정: {verdict}**",
        f"**종합 시그널**: {summarize_signal(isnap)}",
        "",
    ]
    out += _setup_section(plans)
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


# ──────────────────────── 페이퍼 트레이딩 로깅 ────────────────────────
def _paper_path():  # type: ignore[no-untyped-def]
    import pathlib  # noqa: PLC0415

    return pathlib.Path("data") / "paper" / "trades.jsonl"


def _read_paper():  # type: ignore[no-untyped-def]
    import json  # noqa: PLC0415

    path = _paper_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_paper(entry) -> None:  # type: ignore[no-untyped-def]
    import json  # noqa: PLC0415

    path = _paper_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def paper_log_md(codes: list[str], as_of: dt.date) -> str:
    if not codes:
        return "사용법: `k-paper log <종목명|코드> [...]` — 현재 셋업을 페이퍼로 기록"
    existing = _read_paper()
    open_keys = {(e["code"], e["data_date"], e["setup"]) for e in existing if e["status"] == "open"}
    lines = []
    for c in codes:
        snap = resolve(c, as_of)
        if snap is None:
            lines.append(f"❌ '{c}' 종목 못 찾음")
            continue
        analysis = _indicator_analysis(snap)
        if analysis is None:
            lines.append(f"❌ {snap.ticker.name} 분석 실패")
            continue
        isnap, _ = analysis
        plans = classify_setups(isnap, snap.close)
        if not plans:
            lines.append(f"⚪ {snap.ticker.name}({snap.ticker.code}) — 셋업 없음, 미기록")
            continue
        p = plans[0]
        if (snap.ticker.code, snap.as_of.isoformat(), p.setup) in open_keys:
            lines.append(f"🔁 {snap.ticker.name} — 이미 기록된 미청산 셋업")
            continue
        _append_paper(
            {
                "logged_at": today().isoformat(),
                "data_date": snap.as_of.isoformat(),
                "code": snap.ticker.code,
                "name": snap.ticker.name,
                "setup": p.setup,
                "quality": p.quality,
                "entry": p.entry,
                "stop": p.stop,
                "target1": p.target1,
                "target2": p.target2,
                "risk_per_share": p.risk_per_share,
                "reward_risk": p.reward_risk,
                "stop_pct": p.stop_pct,
                "status": "open",
            }
        )
        lines.append(
            f"📝 {snap.ticker.name}({snap.ticker.code}) {p.setup} 기록 — "
            f"진입 {p.entry:,}/손절 {p.stop:,}/목표 {p.target1:,}"
        )
    return "## 📝 페이퍼 기록\n" + "\n".join(f"- {x}" for x in lines)


def paper_status_md(as_of: dt.date) -> str:
    from datetime import date as _date  # noqa: PLC0415
    from datetime import timedelta  # noqa: PLC0415

    from kor_trading.domain.services.backtest import (  # noqa: PLC0415
        CostModel,
        score_open_position,
    )
    from kor_trading.domain.values.trade_plan import TradePlan  # noqa: PLC0415

    entries = _read_paper()
    if not entries:
        return "기록된 페이퍼 트레이드가 없습니다. `/k-paper log <종목>`으로 기록하세요."

    max_hold = 20
    ohlcv = FdrOhlcvProvider()
    closed, open_rows = [], []
    for e in entries:
        plan = TradePlan(
            setup=e["setup"], quality=e["quality"], entry=e["entry"], stop=e["stop"],
            target1=e["target1"], target2=e["target2"], risk_per_share=e["risk_per_share"],
            reward_risk=e["reward_risk"], stop_pct=e["stop_pct"], rationale="", invalidation="",
        )
        d = _date.fromisoformat(e["data_date"])
        # 신호일 '직후' 구간을 가져온다(최근 봉이 아니라). 보유기간 커버할 캘린더 버퍼.
        end = min(as_of, d + timedelta(days=max_hold * 2 + 14))
        bars = ohlcv.get_daily_bars(e["code"], end, max_hold * 2 + 20)
        future = [b for b in bars if b.date > d]
        out = score_open_position(plan, future, max_hold=max_hold, cost=CostModel())
        cur = future[-1].close if future else e["entry"]
        if out.status == "open":
            open_rows.append((e, cur))
        else:
            closed.append((e, out))

    md = [f"## 📒 페이퍼 트레이딩 현황 — {as_of.isoformat()}", f"미청산 {len(open_rows)} · 청산 {len(closed)}", ""]
    if closed:
        rs = [o.r_multiple for _, o in closed if o.r_multiple is not None]
        wins = sum(1 for r in rs if r > 0)
        md += ["### ✅ 청산 (forward 검증)", "| 종목 | 셋업 | 기록일 | 결과 | R |", "|---|---|---|---|---|"]
        mark = {"win": "🟢 목표", "loss": "🔴 손절", "timeout": "🟡 만기"}
        for e, o in closed:
            md.append(
                f"| {e['name']}({e['code']}) | {e['setup']} | {e['data_date']} "
                f"| {mark.get(o.status, o.status)} | {o.r_multiple:+.2f} |"
            )
        avg = sum(rs) / len(rs) if rs else 0.0
        md.append(f"\n**종합**: 승률 {wins / len(rs) * 100:.0f}% · 평균 {avg:+.2f}R ({len(rs)}건)")
        md.append("")
    if open_rows:
        md += ["### ⏳ 미청산", "| 종목 | 셋업 | 기록일 | 진입 | 현재 | 손절 | 목표 |", "|---|---|---|---|---|---|---|"]
        for e, cur in open_rows:
            pnl = (cur - e["entry"]) / e["entry"] * 100
            md.append(
                f"| {e['name']}({e['code']}) | {e['setup']} | {e['data_date']} "
                f"| {e['entry']:,} | {cur:,}({pnl:+.1f}%) | {e['stop']:,} | {e['target1']:,} |"
            )
    return "\n".join(md)


# ──────────────────────── 보유 포지션 관리 ────────────────────────
def manage_md(query: str, avg_cost: int, as_of: dt.date) -> str:
    if avg_cost <= 0:
        return "❌ 평단가는 0보다 큰 정수여야 합니다. 예) 005930 71000"
    snap = resolve(query, as_of)
    if snap is None:
        return f"❌ '{query}' 종목을 찾지 못했습니다."
    analysis = _indicator_analysis(snap)
    if analysis is None:
        return f"❌ {snap.ticker.name}({snap.ticker.code}) 분석 실패: 데이터 부족"
    isnap, _scores = analysis
    adv = manage_position(isnap, snap.close, avg_cost)

    pnl_mark = "🔵" if adv.pnl_pct >= 0 else "🔴"
    action_mark = {
        "추가매수 검토": "🟢",
        "보유": "🟡",
        "일부 익절": "🟠",
        "전량 익절": "🟠",
        "손절": "🔴",
    }.get(adv.action, "")
    return "\n".join(
        [
            f"## 📌 {snap.ticker.name} ({snap.ticker.code}) 보유 관리 — {snap.as_of.isoformat()}",
            f"- 평단 {avg_cost:,}원 → 현재가 {snap.close:,}원 "
            f"| 평가손익 {pnl_mark} {adv.pnl_pct:+.1f}%",
            "",
            f"**{action_mark} 판단: {adv.action}**",
            f"- 근거: {adv.reason}",
            f"- {adv.note}",
            "",
            f"_지표: {summarize_signal(isnap)}_",
        ]
    )


# ──────────────────────── 백테스트 ────────────────────────
def backtest_md(
    codes: list[str], as_of: dt.date, lookback_bars: int = 300, top_n: int = 20, max_hold: int = 20
) -> str:
    from kor_trading.domain.entities.ticker import Ticker  # noqa: PLC0415
    from kor_trading.domain.services.backtest import (  # noqa: PLC0415
        CostModel,
        aggregate,
        run_backtest,
    )
    from kor_trading.domain.services.indicator_calculator import (  # noqa: PLC0415
        calculate_indicators,
    )

    if codes:
        targets = [s for s in (resolve(c, as_of) for c in codes) if s is not None]
    else:
        targets = sorted(universe(as_of), key=lambda s: s.trading_value, reverse=True)[:top_n]
    if not targets:
        return "❌ 백테스트 대상 종목을 찾지 못했습니다."

    ohlcv = FdrOhlcvProvider()
    all_trades = []
    tested = 0
    for snap in targets:
        ticker = Ticker(code=snap.ticker.code, name=snap.ticker.name, market=snap.ticker.market)
        bars = ohlcv.get_daily_bars(ticker.code, snap.as_of, lookback_bars)
        if len(bars) < 130:  # 워밍업 부족
            continue
        tested += 1

        def sig(b, _t=ticker):  # type: ignore[no-untyped-def]
            w = list(b[-150:])
            return classify_setups(calculate_indicators(_t, w), w[-1].close)

        all_trades += run_backtest(bars, sig, warmup=120, max_hold=max_hold, cost=CostModel())

    stats = aggregate(all_trades)
    out = [
        f"## 🧪 셋업 백테스트 — {tested}종목 / 최근 {lookback_bars}거래일 / 보유 {max_hold}일",
        "_거래비용·갭 반영(왕복 ~0.21%). 수급 데이터 과거 미제공 → 수급주도 셋업 제외._",
        "",
        "| 셋업 | 거래 | 승률 | 기대값(R) | 손익비 | 평균익 | 평균손 | MDD(R) |",
        "|------|------|------|-----------|--------|--------|--------|--------|",
    ]
    if not stats:
        out.append("| _발생 거래 없음_ | | | | | | | |")
        return "\n".join(out)
    for s in stats:
        flag = "✅" if s.expectancy_r > 0 else "⚠️"
        out.append(
            f"| {flag} {s.setup} | {s.trades} | {s.win_rate:.0%} | {s.expectancy_r:+.2f} "
            f"| {s.payoff:.1f} | {s.avg_win_r:+.2f} | {s.avg_loss_r:+.2f} | {s.max_drawdown_r:.1f} |"
        )
    total = len(all_trades)
    avg_exp = sum(t.r_multiple for t in all_trades) / total if total else 0.0
    out.append("")
    out.append(f"**종합**: 총 {total}거래, 평균 기대값 {avg_exp:+.2f}R")
    out.append("기대값 > 0 = 양의 기대값(유효), < 0 = 손실 셋업(제거/수정 대상)")
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
