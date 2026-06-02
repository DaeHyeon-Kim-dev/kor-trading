# 로드맵 — 구현 현황 & 남은 작업

> 최종 갱신: 2026-06-02
> 기준 커밋: 36개 PR 머지, 325 tests, 100% coverage, mypy strict / ruff / import-linter clean

---

## ✅ 구현 완료 (MVP 핵심 흐름)

전 흐름이 코드 레벨에서 연결됨:

```
종목 선정 → 지표 분석(추세/모멘텀/변동성/거래량/수급) → DART 공시 수집
   → LLM 분류(Claude 구독) → 이슈 점수 → 4관점 추천
   → 마크다운 리포트(+이슈) → 텔레그램 푸시 → 히스토리 영구 저장
```

### 레이어별 완료 항목

| 레이어 | 항목 |
|---|---|
| **Domain 엔티티** | Ticker, OhlcvBar, StockSnapshot, IndicatorSnapshot, Disclosure, Issue |
| **Domain 값객체** | Score, RecommendationLevel/Thresholds, Sentiment/Impact/DisclosureSource |
| **Domain 포트** | MarketSnapshotProvider, OhlcvProvider, DisclosureProvider, SentimentClassifier, InvestorFlowProvider, TickerNameResolver, CorpCodeResolver, Notifier, ReportRepository, Clock |
| **Domain 서비스** | 지표 계산(SMA/MACD/RSI/Bollinger/ATR/Stochastic/OBV), 신호 분류, 종합·4관점 점수, recency decay, issue_factory, issue_scoring, horizon_recommendation |
| **Application** | SelectStocks, AnalyzeIndicators, AnalyzeIssues, GenerateReport, RunPipeline, 마크다운 렌더링 |
| **Adapters** | pykrx(시세/수급/OHLCV), DART(공시/corp_code), FinanceDataReader(종목명), Claude Code 분류기, Telegram, FileSystem, typer CLI |
| **Infra** | config 로더(pydantic-settings+YAML), structlog, SystemClock, Composition Root |
| **품질** | 100% coverage, mypy --strict, ruff, import-linter(헥사고날 계약 3개), CI(GitHub Actions), pre-commit |
| **운용** | launchd plist, `claude -p` 헤드리스, 활성 시간/요일 자동 skip |

---

## 🔴 남은 작업 — MVP 마감용 (선택)

### R1. 실 운용 end-to-end 검증 ⭐ 최우선
- **무엇**: 실제 `claude -p` + DART API + pykrx + Telegram으로 1회 전체 흐름 실행
- **필요**: `.env`에 `DART_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 입력
- **확인 포인트**:
  - pykrx 실 데이터 fetch (영업일/휴장일)
  - DART corp_code 매핑 다운로드 + 공시 조회
  - `claude -p` subprocess 분류가 구독 한도 내 정상 동작 + 속도(종목당 ~1.6s)
  - 텔레그램 실제 수신
  - 리포트/evidence 파일 저장 확인
- **규모**: 코드 변경 거의 없음, 디버깅 위주. 통합 테스트(`-m integration`) 1~2개 추가 가능.

### R2. 시장 개요 섹션
- **무엇**: 리포트 상단에 KOSPI/KOSDAQ 지수·등락률, 외국인/기관 일별 순매수 요약
- **필요**: `MarketIndexProvider` 포트 + pykrx 어댑터 (`get_index_ohlcv`)
- **규모**: 1~2 PR (포트+어댑터, 렌더러 통합)

### R3. ATR 기반 손절폭 리포트 표시
- **무엇**: ATR은 이미 계산됨. evidence/카드에 "손절 제안가 = 종가 - ATR×2" 표시
- **규모**: 1 PR (렌더러만)

### R4. 공매도 잔고 fetch (flow 보강)
- **무엇**: `IndicatorSnapshot.short_balance_ratio` 채우기
- **필요**: pykrx `get_shorting_balance_by_ticker` 어댑터 연동
- **규모**: 1 PR

---

## 🟡 보강 — 품질·정확도 향상 (후순위)

### Q1. 지표 세부 파라미터 config 주입
- 현재 SMA 기간(5/20/60/120), MACD(12/26/9) 등이 코드 상수
- `config/default.yaml`의 `indicators.sma_periods`/`macd` 등을 계산기에 주입
- **규모**: 중 (indicator_calculator를 config 주입형으로 리팩터링)

### Q2. reporting/recommendation_levels config 주입
- 추천 임계값(±0.5/±0.2)이 코드 상수. config로 노출
- **규모**: 소

### Q3. price_action_since 산출
- 공시일 이후 가격 변화율 → "재료 소진" 판정 (PRD § 3.4 명시)
- AnalyzeIssues가 OhlcvProvider 연계 필요
- **규모**: 1 PR

### Q4. OBV 다이버전스 분류
- 현재 OBV trend(up/down/flat)만. 가격 추세와 교차 비교해 다이버전스 신호
- **규모**: 소

### Q5. 텔레그램 종목별 카드 분할 전송
- 현재 헤더 메시지 + `.md` 첨부. PRD는 종목별 카드 분할 전송(rate limit sleep) 명시
- **규모**: 소

### Q6. Anthropic SDK 직접 호출 분류기 (대안 어댑터)
- 현재 Claude Code subprocess만. 토큰 과금형 SDK 어댑터를 동일 포트 뒤로 추가
- 병렬 처리·속도 우위 (구독 한도 부담 시 대안)
- **규모**: 1 PR

---

## 🟢 Phase 2+ — 기능 확장 (PRD 명시 비범위)

### P1. 커뮤니티 감성 분석 (PRD § 4)
- 네이버 종목토론실, 디시 주식갤러리, X 종목 해시태그
- 언급량 급증 + 감성 분포 + 작전성 의심도
- ⚠️ 법적/약관 검토 선행 필수
- 별도 PRD 작성 예정

### P2. 백테스팅 (PRD § 7 Phase 2)
- 히스토리(`data/reports/`)는 이미 영구 보존 중 → 시그널 검증 도구
- 과거 추천 vs 실제 가격으로 점수 가중치 튜닝
- Clock 포트가 이미 있어 시점 주입 가능

### P3. 자동 주문 — KIS Open API (PRD § 8.15)
- 모의투자부터. OrderExecutor 포트 + KIS 어댑터
- 리스크 매니지먼트(포지션 크기, 손절) 별도 설계 필요

### P4. 장중 실시간 알람 (PRD § 1.4)
- 5분 주기 모드. 급등/급락 실시간 감지
- 분봉 데이터(VWAP, 분봉 RSI) 어댑터 필요 → 초단기 관점 정확도 ↑

### P5. 분기·반기 실적, 산업·재무 (중기/장기 관점 보강)
- 현재 중기/장기 관점은 기술적 지표 위주
- DART 정기보고서 파싱 → 재무 지표

### P6. 신용잔고 분석 (INDICATORS.md § 5.3)
- 반대매매 위험, 과열 신호

---

## 우선순위 제안

1. **R1 (실 운용 검증)** — 코드는 됐으니 실제로 한번 돌려서 동작 확인. 가장 가치 높음.
2. **R2 (시장 개요)** + **R3 (손절폭)** — 리포트 완성도. 작은 작업.
3. **Q3 (price_action_since)** — PRD 명시 기능 완결.
4. 이후 Phase 2 중 관심사 선택 (백테스트가 시그널 품질 개선에 직결).

---

## 변경 이력
- 2026-06-02: 초안 — 36개 PR 완료 시점 기준 정리.
