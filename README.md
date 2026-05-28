# Kor Trading Agent

한국 주식(KOSPI/KOSDAQ) 매매 의사결정 보조용 멀티 에이전트 시스템.

> ⚠️ 기획 단계 (PRD v0.3) — 구현 전. PRD는 사용자와 협의하며 갱신 중.

## 핵심 기능

- **종목 선정** — 거래대금 Top 50 + 급등 Top 10 + 급락 Top 10 (`config/default.yaml`로 변경 가능)
- **기술적 지표 분석** — 추세/모멘텀/변동성/거래량 + 한국 특화(외국인·기관·공매도)
- **뉴스 분석** — DART 공시 우선 (MVP), Phase 2에 네이버·RSS 추가
- **4관점 매수/매도 추천** — 초단기 / 단기 / 중기 / 장기 각각 추천 + 근거
- **텔레그램 푸시** — 분석 완료 후 실시간 전송
- **히스토리 영구 보존** — 모든 리포트와 근거 마크다운 저장 (백테스트·개선 활용)

## 디렉토리 구조

```
kor_trading/
├── .claude/agents/                       # Claude Code 서브에이전트 정의
│   ├── orchestrator.md
│   ├── stock-selector.md
│   ├── indicator-analyst.md
│   ├── issue-analyst.md
│   └── reporter.md
├── docs/
│   ├── PRD.md                            # 제품 요구사항 (v0.3)
│   ├── INDICATORS.md                     # 지표 해석 가이드 ⭐
│   └── CONFIG.md                         # 설정 변경 가이드
├── config/
│   └── default.yaml                      # 실행 주기, 선정 기준, 지표 파라미터
├── scripts/                              # (추후) launchd plist, 헬퍼 스크립트
├── data/
│   ├── cache/                            # 재사용 가능한 원본 (git ignore)
│   └── reports/{YYYY-MM-DD}/{HHmm}/      # 영구 히스토리 (git ignore)
│       ├── report.md
│       ├── selection.md
│       ├── evidence/{ticker}.md
│       └── raw/...
├── .env.example                          # 시크릿 템플릿
├── .gitignore
└── README.md
```

## 멀티 에이전트 흐름

```
[Orchestrator]
   │ (설정 로드, 활성 시간 체크)
   ▼
[Stock Selector] ─── 거래대금/급등/급락 후보
   │
   ├──▶ [Indicator Analyst] (병렬, 종목별)  ── 4관점 점수 산출
   │
   ├──▶ [Issue Analyst]     (병렬, 종목별)  ── DART 공시 분석
   │
   └──▶ [Reporter] ── 4관점 매수/매도 추천 + 텔레그램 푸시
```

향후 추가: **Community Sentiment Agent** (네이버 종목토론실, 디시, X 등) — Phase 2

## 빠른 시작

```bash
# 1. uv 설치 + 의존성
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 2. 시크릿 설정
cp .env.example .env
$EDITOR .env  # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DART_API_KEY

# 3. 수동 실행 (활성 시간/요일 무관하게 강제 실행)
uv run python -m kor_trading run --force

# 4. 자동화 (macOS launchd)
$EDITOR scripts/com.kortrading.daily.plist  # 경로/주기 본인 환경에 맞게
cp scripts/com.kortrading.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kortrading.daily.plist

# 절전 모드 우회 (전원 연결 시 평일 08:25 자동 wake)
sudo pmset repeat wakeorpoweron MTWRF 08:25:00
```

## CLI 옵션

```bash
uv run python -m kor_trading run [OPTIONS]
  --config / -c   설정 파일 경로 (기본: config/default.yaml)
  --data / -d     저장 베이스 디렉토리 (기본: data)
  --date          분석 기준일 YYYY-MM-DD (기본: 오늘)
  --log-level     INFO | DEBUG | WARNING ...
  --force         active_hours/weekdays 체크 무시
```

활성 시간/요일 밖에서 호출되면 \`OUT_OF_HOURS — skip\`을 출력하고 종료.

## 문서

- [PRD](docs/PRD.md) — 전체 명세 (v0.3.1)
- [INDICATORS](docs/INDICATORS.md) — 지표 해석 (학습용) ⭐
- [CONFIG](docs/CONFIG.md) — 설정 변경 가이드
- [DEVELOPMENT](docs/DEVELOPMENT.md) — 개발 가이드 (Hexagonal + Clean Arch + TDD) ⭐

## 결정 사항 요약 (PRD v0.3)

| 항목 | 값 |
|---|---|
| 멀티 에이전트 런타임 | Claude Code 서브에이전트 + Python |
| LLM | Claude Max 구독 (추가 비용 0) |
| 실행 진입점 | `claude -p` 헤드리스 |
| 스케줄러 | macOS launchd |
| 실행 주기 | 가변 (1h 기본, 5/10/30분 등) |
| 종목 선정 | 거래대금 Top 50 + 급등 Top 10 + 급락 Top 10 |
| 뉴스 소스 | DART 우선 (MVP) |
| 결과 전달 | 텔레그램 봇 |
| 시크릿 | `.env` |
| 계산 | Python 코드 (LLM은 해석만) |
| 추천 | 종목별 4관점 (초단기/단기/중기/장기) |
| 히스토리 | 모든 리포트·근거 영구 보존 |
