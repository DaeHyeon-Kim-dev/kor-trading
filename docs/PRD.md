# PRD — 한국 주식 트레이딩 에이전트 (Kor Trading Agent)

> 상태: **Draft v0.3.1** — 뉴스 시점(recency) 분석 도입
> 최종 갱신: 2026-05-26

---

## 1. 개요

### 1.1 목적
한국 주식(KOSPI/KOSDAQ) 단기·스윙 매매 의사결정을 보조하는 **멀티 에이전트 시스템**을 구축한다.
사용자는 매일/매 세션 단위로 시스템을 실행하여 다음을 얻는다:
- 오늘 주목할 만한 후보 종목 리스트
- 각 종목의 기술적 지표 분석
- 각 종목 관련 최신 뉴스/공시 분석
- 통합 리포트 (매매 판단 보조)

### 1.2 범위 (MVP)
- 종목 후보 선정 (거래량 상위, 급등, 급락 기준)
- 기술적 지표 분석 (추세/모멘텀/변동성/거래량/한국 특화)
- 뉴스·공시 수집 및 LLM 기반 호재/악재 분류
- 통합 리포트 생성 (마크다운)

### 1.3 비범위 (Out of Scope, v1 이후)
- **커뮤니티 감성 분석** (네이버 종목토론실, 디시, X 등) — Phase 2
- **자동 주문 실행** — 별도 결정 필요 (KIS Open API 연동)
- **백테스팅 시스템** — Phase 2
- **실시간 스트리밍 분석** — Phase 3
- **포트폴리오 최적화 / 리스크 매니지먼트 에이전트** — Phase 2

### 1.4 운영 시나리오 (확정 — MVP)

**실행 주기는 가변** — `config/default.yaml`의 `schedule.interval_seconds`로 제어 (✅ 확정)
- 기본값: 3600초 (1시간) — 평일 08:30 ~ 16:30 KST
- 변경 예: 5분=300, 10분=600, 30분=1800
- launchd plist의 `StartInterval`을 동일 값으로 동기화 필요 (`docs/CONFIG.md` 참조)

**실행 흐름**
1. macOS launchd가 설정된 주기로 트리거
2. `claude -p` 헤드리스 모드로 Orchestrator 서브에이전트 호출
3. 활성 시간대(`active_hours_kst`) + 활성 요일(`active_weekdays`) 외에는 즉시 스킵
4. 분석 완료 → **텔레그램 봇으로 리포트 푸시**
5. 모든 리포트와 근거는 `data/reports/{YYYY-MM-DD}/{HHmm}/`에 영구 보존 (✅ 확정)

향후 확장 (Phase 2+):
- 장중 급등/급락 실시간 알람 (5분 주기 모드)
- 장 마감 후 종가 종합 리포트 (별도 cron)

---

## 2. 아키텍처

### 2.1 멀티 에이전트 구성

```
                    ┌──────────────────────┐
                    │   Orchestrator       │
                    │   (워크플로우 조정)   │
                    └──────────┬───────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Stock Selector  │  │ Indicator       │  │ Issue Analyst   │
│ (종목 선정)      │─▶│ Analyst (지표)  │  │ (뉴스/공시)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │   Reporter           │
                    │   (통합 리포트)       │
                    └──────────────────────┘

[Phase 2] Community Sentiment Agent (커뮤니티 크롤링) — 추후 추가
```

### 2.2 데이터 플로우 (한 사이클)

1. **Orchestrator**가 사용자 입력(시장 구분, 필터 조건) 수신
2. **Stock Selector**에게 위임 → 후보 종목 N개 반환
3. 후보 종목별로 **Indicator Analyst**, **Issue Analyst** 병렬 호출
4. 모든 결과를 **Reporter**에 전달 → 최종 리포트 생성
5. 리포트를 `data/reports/YYYY-MM-DD/` 에 저장 및 사용자에게 출력

### 2.3 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 언어 | **Python 3.11+** | 데이터/금융 라이브러리 풍부 |
| 멀티 에이전트 런타임 | **Claude Code 서브에이전트** (`.claude/agents/*.md`) + Python 도구 호출 | ✅ 확정 — Max 구독 활용 |
| LLM | **Claude (Max 구독 안에서 호출)** | ✅ 확정 — 추가 토큰 비용 0 |
| 실행 진입점 | `claude -p` 헤드리스 모드 | 서브에이전트 자동 호출 |
| 스케줄러 | **macOS launchd** (MVP) | ✅ 확정 — 안정성 이슈 시 Oracle Cloud Free Tier 이전 검토 |
| 알림 채널 | **텔레그램 봇 API** | ✅ 확정 |
| 시세 데이터 | **pykrx**, **FinanceDataReader** | 무료, KRX 공식 |
| 실시간/주문 | **KIS Developers Open API** | 무료, 모의투자 지원 (Phase 2+) |
| 공시 | **DART OpenAPI** | 무료, API 키 발급 필요 |
| 뉴스 | RSS (한경/매경/이데일리), 네이버 금융 (크롤링 — 약관 검토 필요) | |
| 저장소 | 로컬 파일 (JSON/Parquet) → 추후 SQLite | MVP는 파일, 히스토리 영구 보존 |
| 시크릿 관리 | **`.env` + `.gitignore`** (DART 키, 텔레그램 토큰) | ✅ 확정 |
| 설정 파일 | **`config/default.yaml`** (실행 주기, 선정 기준, 지표 파라미터) | ✅ 확정 — `docs/CONFIG.md` 참조 |

---

## 3. 에이전트별 상세 명세

### 3.1 Orchestrator Agent

**책임**
- 사용자 입력 파싱 및 워크플로우 실행
- 서브 에이전트 호출 순서 및 병렬화 관리
- 에러 처리 및 부분 실패 시 폴백
- 최종 결과 통합 → Reporter에 전달

**입력**
```yaml
market: ["KOSPI", "KOSDAQ"]   # 대상 시장
date: 2026-05-22              # 분석 기준일
selection_criteria:
  top_volume_n: 30            # 거래대금 상위 N
  surge_threshold_pct: 5.0    # 급등 기준
  plunge_threshold_pct: -5.0  # 급락 기준
exclude_tickers: []           # 제외 종목
max_candidates: 10            # 최종 분석 대상 수
```

**출력**: `Report` 객체 (Reporter가 생성)

**핵심 로직** (의사 코드)
```python
candidates = stock_selector.select(market, criteria)
candidates = candidates[:max_candidates]

# 병렬 실행
indicator_results = parallel_map(indicator_analyst.analyze, candidates)
issue_results = parallel_map(issue_analyst.analyze, candidates)

report = reporter.compose(candidates, indicator_results, issue_results)
return report
```

---

### 3.2 Stock Selector Agent (종목 선정)

**책임**: 분석 대상 종목 후보군 좁히기

**선정 기준 (✅ 확정 — `config/default.yaml`로 변경 가능)**
1. **거래대금 상위 50종목** (`selection.top_volume_n: 50`)
2. **급등 상위 10종목** (`selection.surge_top_n: 10`) — 등락률 양수 상위
3. **급락 상위 10종목** (`selection.plunge_top_n: 10`) — 등락률 음수 상위
4. 위 세 그룹을 합집합 후 중복 제거 → 후보 풀
5. `max_candidates`로 최종 cap (기본 30)

**필터** (모든 후보에 적용)
- 시가총액 하한 — `market_cap_min_krw` (기본 500억)
- 제외: 우선주, 스팩, ETF, ETN, 관리종목 (각각 토글)

**데이터 소스**
- `pykrx.stock.get_market_ohlcv_by_ticker()` — 일별 시세
- `pykrx.stock.get_market_cap_by_ticker()` — 시가총액
- (실시간 필요 시) KIS API

**계산 원칙 (✅ 확정)**
- 모든 정렬/필터링은 **Python 코드로 처리** (LLM은 결과 해석만)
- 휴장일이면 가장 최근 영업일로 자동 조정

**출력 스키마 (엄격 — ✅ 확정)**
```json
{
  "as_of": "2026-05-26",
  "market": ["KOSPI", "KOSDAQ"],
  "total_screened": 2350,
  "candidates": [
    {
      "ticker": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "close": 78500,
      "change_pct": 5.2,
      "volume": 25300000,
      "trading_value": 1980000000000,
      "market_cap": 469000000000000,
      "selection_reason": ["top_volume", "surge"],
      "rank_by_volume": 3,
      "rank_by_change_up": 7,
      "rank_by_change_down": null
    }
  ]
}
```

**저장 경로**: `data/reports/{YYYY-MM-DD}/{HHmm}/raw/selection.json` + 가독성용 `selection.md`

---

### 3.3 Indicator Analyst Agent (지표 분석)

**책임**: 종목별 기술적 지표 계산 및 신호 분류

**계산 지표 (MVP)**

| 카테고리 | 지표 | 파라미터 | 신호 |
|---|---|---|---|
| 추세 | SMA | 5, 20, 60, 120일 | 정배열/역배열 |
| 추세 | MACD | (12, 26, 9) | 골든/데드 크로스 |
| 모멘텀 | RSI | 14 | 과매수(>70)/과매도(<30) |
| 모멘텀 | Stochastic | (14, 3, 3) | %K-%D 크로스 |
| 변동성 | Bollinger Band | (20, 2) | 밴드 이탈, 스퀴즈 |
| 변동성 | ATR | 14 | 손절폭 산정 |
| 거래량 | OBV | - | 추세 일치/다이버전스 |
| 거래량 | VWAP | 일중 | 가격 vs VWAP |
| 한국 특화 | 외국인 순매수 | 5일/20일 | 누적 매수세 |
| 한국 특화 | 기관 순매수 | 5일/20일 | 누적 매수세 |
| 한국 특화 | 공매도 잔고 비율 | - | 추세 |

**입력**
```yaml
ticker: "005930"
period: 120  # 일 (지표 계산용 과거 데이터 기간)
end_date: 2026-05-22
```

**출력 스키마**
```json
{
  "ticker": "005930",
  "as_of": "2026-05-22",
  "indicators": {
    "sma": {"5": 77800, "20": 75200, "60": 72100, "120": 70500, "alignment": "bullish"},
    "macd": {"macd": 1.2, "signal": 0.8, "hist": 0.4, "cross": "golden_recent"},
    "rsi_14": 62.3,
    "bollinger": {"upper": 80100, "mid": 75200, "lower": 70300, "position": "upper_half"},
    "atr_14": 1850,
    "foreign_net_buy_5d": 12_500_000_000,
    "institution_net_buy_5d": -3_200_000_000,
    "short_balance_ratio": 1.8
  },
  "signals": {
    "trend": "bullish",
    "momentum": "neutral_overbought_risk",
    "volatility": "expanding",
    "volume": "strong",
    "summary": "단기 추세 강세이나 RSI 60대 진입, 외국인 순매수 지속"
  },
  "score": 0.72
}
```

**구현 방식 (✅ 확정 — A)**
- **모든 지표 계산은 Python 코드** (`pandas` + `pandas-ta`)
- **LLM은 신호 해석/요약만** — raw OHLCV를 LLM에 던지지 않음
- 해석 룰은 `docs/INDICATORS.md` 참조 (각 지표 상태별 상승·하락 확률 정리)
- 종합 점수 = 카테고리별 점수 × 가중치 (가중치는 `config/default.yaml`의 `score_weights`)

**저장 경로**: `data/reports/{YYYY-MM-DD}/{HHmm}/raw/indicators/{ticker}.json` + 가독성용 `evidence/{ticker}.md`

---

### 3.4 Issue Analyst Agent (이슈 분석)

**책임**: 종목 관련 뉴스/공시 수집 + LLM 분석

**수집 소스 (✅ 확정 — MVP는 DART만)**
1. **DART 공시** — **1순위 (✅ 확정)**
   - `https://opendart.fss.or.kr/api/list.json`
   - 주목할 보고서 유형은 `config/default.yaml`의 `news.sources.dart.target_reports`에서 관리
   - 주요 공시: 실적, 단일판매·공급계약, 유상증자, 자사주, 임원 변경, 횡령·배임
2. **네이버 금융 뉴스** — Phase 2 (약관 검토 후 활성화)
3. **RSS (한경/매경/이데일리)** — Phase 2

**수집 범위**
- 분석일 기준 **최근 7일** (`news.lookback_days`)
- 종목당 최대 20건 (`news.max_issues_per_ticker`)

**LLM 분석 항목**
- 핵심 이슈 3~5건 요약 (1줄씩)
- 각 이슈의 **방향성** (호재/악재/중립) + **영향도** (강/중/약)
- 공시·뉴스의 **신뢰도** 표시 (공시 > 주요 매체 > 기타)
- 전체 종합 코멘트 (2~3문장)

**시점(recency) 분석 ✅ 확정**
모든 이슈는 **반드시 날짜를 포함**하고, 시점 기반 가중치(decay)와 가격 반영도를 평가한다.

| recency_days | decay_weight |
|---|---|
| 0 (당일) | 1.00 |
| 1~2 | 0.85 |
| 3~7 | 0.60 |
| 8~14 | 0.30 |
| 15+ | 0.10 |

- `effective_impact = impact_score × decay_weight`
- 각 이슈마다 `price_action_since` (공시 후 가격 변화율)을 함께 산출 → "재료 소진/미반영" 판단
- 종합 점수는 decay 적용된 가중 평균
- Reporter는 4관점별로 다른 recency 윈도우를 사용:
  - 초단기: 0~3일 이슈 위주
  - 단기: 0~7일
  - 중기: 0~14일 + 분기 실적
  - 장기: 산업 흐름 (개별 뉴스 영향 ↓)
- **decay 가중치는 `config/default.yaml`의 `news.recency_decay`에서 변경 가능**

**출력 스키마 (엄격 — ✅ 확정)**
```json
{
  "ticker": "005930",
  "as_of": "2026-05-26",
  "period_from": "2026-05-19",
  "period_to": "2026-05-26",
  "sources_count": {"dart": 3, "naver": 0, "rss": 0},
  "key_issues": [
    {
      "date": "2026-05-21",
      "title": "1분기 영업이익 사상 최대",
      "source": "DART",
      "source_url": "https://...",
      "report_type": "주요사항보고",
      "recency_days": 5,         // ✅ 확정 — 분석일 - 공시일
      "decay_weight": 0.60,      // ✅ 확정 — 시점 가중치
      "sentiment": "positive",   // positive | negative | neutral
      "impact": "high",          // high | medium | low
      "effective_impact": 0.60,  // impact_score × decay_weight
      "confidence": 0.95,        // 0~1 (공시>매체>기타)
      "price_action_since": 4.8, // ✅ 확정 — 공시일 종가 대비 변화율 (%)
      "summary": "AI 반도체 수요 증가로 어닝 서프라이즈"
    }
  ],
  "overall_sentiment": "positive",  // positive | negative | mixed | neutral
  "overall_score": 0.6,              // -1.0 ~ +1.0 (decay 적용 가중 평균)
  "overall_comment": "5/21 1Q 어닝 공시 이후 +4.8%로 일부 반영. 5/24(당일) 자사주 매입은 미반영 신규 호재."
}
```

**저장 경로**: `data/reports/{YYYY-MM-DD}/{HHmm}/raw/issues/{ticker}.json` + `evidence/{ticker}.md`에 통합

---

### 3.5 Reporter Agent (리포트 + 텔레그램 푸시)

**책임**: 모든 분석 결과를 사용자 친화적 형태로 통합 + **텔레그램 봇으로 전송**

**리포트 구성 (✅ 확정)**
1. **헤더** — 분석 일시(YYYY-MM-DD HH:mm), 시장, 후보 수, 실행 주기
2. **시장 개요** — KOSPI/KOSDAQ 종가·변동률, 외국인/기관 일별 순매수
3. **요약 테이블** — 후보 전체 한눈에 (4관점 추천을 컬럼으로)
4. **종목별 상세 카드** (각 후보 종목)
   - 종목명·코드·등락률·거래대금
   - 선정 사유
   - **4관점 매수/매도 추천 표** (초단기/단기/중기/장기, 각각 추천 + 근거)
   - **지표 요약** (점수 + 핵심 신호)
   - **이슈 요약** (Top 3 핵심 공시·뉴스)
   - 종합 코멘트 (2~3문장)
5. **부록** — 사용 지표 정의 링크 (`docs/INDICATORS.md`)

### 4관점 매수/매도 추천 (✅ 확정)

각 종목마다 다음 4개 시간 관점에서 추천을 산출:

| 관점 | 기간 | 우선 지표 |
|---|---|---|
| **초단기** | 당일~3일 | VWAP, 분봉 RSI, 외국인 당일 매매, 거래량 급증 |
| **단기** | 1주~1개월 | 5/20일선, RSI(14), MACD, 외국인 5일 누적 |
| **중기** | 1~3개월 | 20/60일선, MACD 추세, 외국인 20일 누적, 분기 실적 |
| **장기** | 3개월+ | 60/120일선, 산업 사이클, 재무 |

**추천 단계** (`config/default.yaml`의 `recommendation_levels` 참조)
- 🟢🟢 **Strong Buy** (점수 ≥ +0.5)
- 🟢 **Buy** (+0.2 ~ +0.5)
- 🟡 **Hold / Watch** (-0.2 ~ +0.2)
- 🔴 **Sell** (-0.5 ~ -0.2)
- 🔴🔴 **Strong Sell** (≤ -0.5)

각 관점별 점수는 **해당 시간대 우선 지표만** 가중치를 높여 재계산.
지표 → 추천 변환 룰은 `docs/INDICATORS.md` § 7, § 9 참조.

### 종목 카드 예시 마크다운
```markdown
### 1. 삼성전자 (005930)
- **등락률**: +5.2% | **거래대금**: 1.98조 | **시총**: 469조
- **선정 사유**: 거래대금 1위, 급등 7위

| 관점 | 추천 | 근거 |
|---|---|---|
| 초단기 (~3일) | 🟢 Buy | VWAP 위, 외국인 당일 +1200억, 거래량 평균 2.3배 |
| 단기 (~1개월) | 🟢🟢 Strong Buy | 5/20 골든크로스, MACD 0선 위, RSI 62 |
| 중기 (~3개월) | 🟢 Buy | 정배열 진입, 1Q 어닝 서프라이즈 |
| 장기 (3개월+) | 🟡 Hold | 120일선 위지만 산업 사이클 정점 우려 |

**지표 요약 (점수 0.72)**: 정배열 + MACD 골든크로스 + 외국인 5일 누적 +5000억
**이슈 요약**: [DART] 1Q 영업이익 사상 최대 / [DART] 자사주 매입 결정
**코멘트**: 단기 추세·재료 모두 우호적. RSI 60대 진입으로 단기 과열 주의.
```

**출력 형식**
- 기본: 마크다운 (`.md`) 파일 저장 + **텔레그램 봇 전송** ✅ 확정
- 추후: HTML, Slack 옵션

**저장 경로 (✅ 확정 — 히스토리 영구 보존)**
- `data/reports/{YYYY-MM-DD}/{HHmm}/report.md` — 최종 리포트
- `data/reports/{YYYY-MM-DD}/{HHmm}/selection.md` — 선정 결과 (가독성)
- `data/reports/{YYYY-MM-DD}/{HHmm}/evidence/{ticker}.md` — 종목별 근거 통합 (지표 + 이슈)
- `data/reports/{YYYY-MM-DD}/{HHmm}/raw/` — 모든 raw JSON
- `data/reports/{YYYY-MM-DD}/{HHmm}/meta.json` — 실행 메타 (소요시간, 에러)

**텔레그램 푸시 명세**
- 환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (`.env`에서 로드)
- 전송 전략:
  - 헤더 + 시장 개요 → 1개 메시지
  - 종목별 카드 → 종목당 1개 메시지 (텔레그램 4096자 제한 회피, 푸시 알림이 종목별로 와서 가독성 ↑)
  - 마크다운 본문 전체는 `sendDocument`로 `.md` 파일 첨부 (백업/검색용)
- 멱등성: 전송 실패 시 로컬 마크다운은 보존, 재실행 시 동일 결과 재전송 가능
- 재시도: HTTP 5xx/네트워크 오류에 한해 1회 재시도, 그 외(403, chat_id 오류 등)는 즉시 실패
- Rate limit: 텔레그램은 봇당 초당 ~30 메시지 제한, 종목 분할 전송 시 100ms sleep 권장

**종합 시그널 룰** (관점별 — 자세한 룰은 `docs/INDICATORS.md` § 6, § 9)
- Strong Buy: 정배열 + MACD 0선 위 골든크로스 + RSI 50~70 + 외국인·기관 동반 순매수
- Buy: 위 신호 중 3개 이상
- Hold/Watch: 혼조 또는 1~2개만 충족
- Sell: 역배열 + MACD 0선 아래 데드크로스 또는 RSI > 80에서 반락
- Strong Sell: 위 + 외국인·기관 동반 순매도 + 악재

**작성 원칙**
- 매매 권유가 아닌 **정보 보조** 톤
- 시그널은 항상 **근거(지표 또는 이슈)** 와 함께 제시
- 확신 표현 금지 (가능성/주의 표현 사용)

---

## 4. Phase 2 — Community Sentiment Agent (참고)

**향후 추가 예정**, 현재는 명세만 메모.

- 데이터 소스 후보: 네이버 종목토론실, 디시 주식갤러리, X 종목 해시태그
- 시그널: **언급량 급증** + 감성 분포 + 작전성 의심도
- 법적/약관 검토 선행 필수
- 별도 PRD 작성 예정

---

## 5. 데이터 모델 (히스토리 영구 보존 ✅ 확정)

```
data/
├── cache/                                  # 재사용 가능한 원본 (날짜별 1회 수집)
│   ├── ohlcv/{ticker}/{date}.parquet       # 일봉 (지표 계산용)
│   ├── flow/{ticker}/{date}.json           # 외국인·기관 매매동향
│   ├── dart/{ticker}/{date}.json           # 공시 raw
│   └── market/{date}.json                  # 지수, 시장 요약
│
└── reports/{YYYY-MM-DD}/{HHmm}/            # 실행 1회 = 1 디렉토리 (히스토리)
    ├── report.md                           # 최종 리포트 (텔레그램 푸시 본문)
    ├── selection.md                        # 종목 선정 결과 (가독성)
    ├── meta.json                           # 실행 메타 (소요시간, 에러, 사용 config 스냅샷)
    ├── evidence/
    │   └── {ticker}.md                     # 종목별 근거 통합 (지표 + 이슈 + 4관점 판정)
    └── raw/
        ├── selection.json
        ├── indicators/{ticker}.json
        └── issues/{ticker}.json
```

**보존 정책 (✅ 확정)**
- 리포트와 근거는 **영구 보존** — 추후 시그널 백테스트 및 모델 개선에 활용
- `cache/`는 동일 일자 재수집 회피용 (재실행 시 빠르게)
- `evidence/{ticker}.md`는 **사람이 직접 읽고 판단을 검증**할 수 있는 형태로 작성
  (지표 값 + 해석 + 이슈 원문 링크 + 4관점 판정 근거)

---

## 6. 실행 흐름

### 6.1 정기 실행 (자동, MVP)
macOS **launchd**가 평일 08:30 KST에 다음을 실행:

```bash
cd /Users/daehyeon_kim/dev/kor_trading
claude -p "오늘의 한국 주식 분석을 실행하고 텔레그램으로 결과를 보내라" \
  --output-format text
```

- `claude -p`(헤드리스 모드)가 `.claude/agents/orchestrator.md` 정의대로 워크플로우 실행
- 모든 LLM 호출은 **Claude Max 구독 안에서 처리** (토큰 비용 0)
- Mac이 절전모드면 실패 → `pmset repeat wakeorpoweron MTWRF 08:25:00` 으로 자동 wake 설정 권장 (전원 연결 필수)

### 6.2 수동 실행 (개발/디버깅)

```bash
# 기본 실행 (당일, KOSPI+KOSDAQ)
$ claude -p "오늘의 한국 주식 분석을 실행"

# 특정 일자 / 시장 한정
$ claude -p "2026-05-22 기준 KOSDAQ만 분석해서 리포트 작성"

# 후보 종목 직접 지정 (지표·이슈 분석만)
$ claude -p "005930, 035720 두 종목만 분석"

# 대화형으로 진입 (디버깅)
$ claude
> /agents  # 서브에이전트 목록 확인
> orchestrator를 호출해서 ...
```

### 6.3 launchd 설정 파일 (위치)
- `~/Library/LaunchAgents/com.kortrading.daily.plist`
- 샘플 plist는 `scripts/com.kortrading.daily.plist`에 작성 예정
- 등록: `launchctl load ~/Library/LaunchAgents/com.kortrading.daily.plist`

---

## 7. 단계별 개발 계획

| Phase | 목표 | 산출물 |
|---|---|---|
| **P0** | 인프라 셋업 | 디렉토리, 의존성, pykrx/DART 연결 확인 |
| **P1** | Stock Selector + Reporter (지표·이슈 빈약) | "오늘의 거래대금 상위 10종목" 리스트 |
| **P2** | Indicator Analyst 통합 | 지표 포함 리포트 |
| **P3** | Issue Analyst 통합 | DART 공시 포함 → 뉴스 추가 |
| **P4** | Orchestrator 정교화, 병렬화, 에러 처리 | 안정적 일일 실행 |
| **P5** | Community Sentiment Agent | Phase 2 |
| **P6** | (옵션) 자동 주문, 백테스트 | TBD |

---

## 8. 결정 사항 / 미해결 항목

### ✅ 확정된 결정 (v0.3 기준)
1. **멀티 에이전트 런타임** — Claude Code 서브에이전트 + Python 도구 호출 (v0.2)
2. **LLM 모델 / 비용** — Claude Max 구독 안에서 호출 (v0.2)
3. **결과 전달 채널** — 텔레그램 봇 (v0.2)
4. **실행 진입점** — `claude -p` 헤드리스 모드 (v0.2)
5. **개발/운영 환경** — 로컬 macOS + launchd (v0.2)
6. **실행 주기** — **`config/default.yaml`로 가변** (v0.3, 기본 1시간, 5/10/30분 등 자유)
7. **종목 선정 기준** — **거래대금 Top 50 + 급등 Top 10 + 급락 Top 10** (v0.3, 시총 하한 500억)
8. **뉴스 소스** — **DART 우선 (MVP), 네이버·RSS는 Phase 2** (v0.3)
9. **시크릿 관리** — **`.env` + `.gitignore`** (v0.3)
10. **계산 방식** — **모든 지표·정렬은 Python 코드로, LLM은 해석만** (v0.3)
11. **리포트 구조** — **종목별 4관점(초단기/단기/중기/장기) 매수/매도 추천** (v0.3)
12. **히스토리** — **모든 리포트·근거를 `data/reports/{YYYY-MM-DD}/{HHmm}/`에 영구 보존** (v0.3)
13. **각 에이전트 출력 스키마** — JSON 스키마로 엄격 명시 (v0.3, § 3.2~3.4)

### 🟡 미해결 — 추후 협의
14. **리포트 텔레그램 분할 전략** — 종목별 분할(현재 안) vs 전체 1통 + `.md` 첨부 — 운용해보고 결정
15. **자동매매 연동** (Phase 2+) — KIS Open API 모의투자부터?
16. **백테스팅** (Phase 2+) — 시그널 검증 도구 도입 시점
17. **점수 가중치 튜닝** — `config/default.yaml`의 `score_weights`는 MVP 초기값. 히스토리 축적 후 백테스트로 보정
18. **Phase 2 — 커뮤니티 감성** 도입 시점

---

## 9. 참고 — 한국 주식 API/라이브러리 메모

- **pykrx**: KRX 데이터 무료, 일봉/시총/외국인기관 매매동향 등 광범위
- **FinanceDataReader**: 다국가, 한국 포함
- **KIS Developers**: 한국투자증권 공식, 실시간 시세 + 주문, 무료
- **DART OpenAPI**: 금감원 공시, 무료, API 키 발급 필요
- **OpenDart 라이브러리**: dart-fss 등 파이썬 래퍼

---

## 10. 변경 이력
- 2026-05-26: **v0.3.1** — Issue Analyst에 **시점(recency) 분석** 도입. 모든 이슈는 `date` 필수, `recency_days`/`decay_weight`/`price_action_since`/`effective_impact` 필드 추가. 4관점별 recency 윈도우 적용. Reporter는 이슈 출력 시 `[출처, MM/DD, N일 전, 반영도]` 형식으로 날짜·시점 맥락 의무화. `config/default.yaml`에 `news.recency_decay`, `news.horizon_recency_window` 추가.
- 2026-05-26: **v0.3** — 실행 주기 가변화(`config/default.yaml`). 종목 선정 기준 확정 (거래대금 Top 50 + 급등/급락 Top 10). 뉴스는 DART 우선. 시크릿은 `.env`. 모든 계산은 코드. 리포트에 **초단기/단기/중기/장기 4관점 매수/매도 추천** 도입. 모든 리포트·근거 **영구 보존**. 각 에이전트 출력 스키마 엄격화. **`docs/INDICATORS.md` (지표 해석 가이드)**, **`docs/CONFIG.md` (설정 가이드)** 신설.
- 2026-05-22: v0.2 — 실행 환경 확정 (Claude Max 구독 + macOS launchd + `claude -p` 헤드리스 + 텔레그램 봇). Reporter 에이전트에 텔레그램 푸시 명세 추가.
- 2026-05-22: v0.1 — 초안 작성
