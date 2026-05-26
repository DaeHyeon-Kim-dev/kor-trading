# 개발 가이드

> Kor Trading Agent 구현자용 가이드. **Hexagonal + Clean Architecture**, **TDD**, **Python 3.11+** 기반.

## 0. 핵심 원칙

1. **의존성 방향은 안쪽으로만**: `domain` ← `application` ← `adapters` ← `infrastructure`
   - 안쪽 레이어는 바깥쪽을 절대 모른다. import 한 줄이라도 어기면 설계가 망가진다.
2. **Domain은 framework 0 의존성**: pandas/pykrx/pydantic 같은 외부 라이브러리는 domain에 들어오면 안 됨.
3. **TDD Red → Green → Refactor**: 테스트가 먼저, 구현이 나중.
4. **포트(인터페이스)는 안쪽, 어댑터(구현)는 바깥쪽**: 비즈니스 로직이 외부를 추상화로 사용.
5. **Composition Root만 모든 구체를 안다**: `main.py` 또는 `container.py`에서만 어댑터 ↔ 포트를 연결.

---

## 1. 기술 스택 (확정)

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 | **Python 3.11+** | match, exception group 등 활용 |
| 패키지 매니저 | **uv** | 빠름, lock 파일, Python 버전 관리 포함 |
| I/O | **sync + ThreadPoolExecutor** | 단순, TDD 쉬움. 종목 단위 병렬은 thread pool |
| HTTP 클라이언트 | **httpx** (sync) | requests보다 modern, type hint 양호 |
| 데이터 처리 | **pandas** + **pandas-ta** | 지표 계산 표준 |
| 한국 시세 | **pykrx**, **FinanceDataReader** | KRX 데이터 무료 |
| DART 공시 | **dart-fss** 또는 직접 httpx | dart-fss가 편함 |
| 모델링 (경계) | **pydantic v2** | 입력 검증, 설정 로드, agent 출력 |
| 모델링 (도메인) | **`@dataclass(frozen=True, slots=True)`** | framework 0 의존 |
| 설정 로드 | **pydantic-settings + PyYAML** | `.env` + `config/default.yaml` |
| 타입 검사 | **mypy --strict** | 컴파일 타임 안전 |
| 린트 / 포맷 | **ruff** (lint + format) | black + isort + flake8 통합, 빠름 |
| 테스트 | **pytest**, pytest-cov, pytest-mock, **freezegun**, **respx** | respx로 HTTP mock |
| 로깅 | **structlog** | JSON 구조화 로그 |
| CLI | **typer** | 자동 헬프, 타입 기반 |
| Pre-commit | **pre-commit** | ruff + mypy 자동 |
| (옵션) CI | GitHub Actions | 추후 |

---

## 2. 프로젝트 구조

```
kor_trading/
├── pyproject.toml                    # uv가 관리
├── uv.lock
├── .python-version                   # uv가 생성
├── .pre-commit-config.yaml
├── pytest.ini  또는 pyproject 안
├── mypy.ini    또는 pyproject 안
├── ruff.toml   또는 pyproject 안
│
├── src/kor_trading/
│   ├── __init__.py
│   │
│   ├── domain/                       # ❶ 가장 안쪽: 순수 비즈니스
│   │   ├── entities/                 # Ticker, Issue, IndicatorSnapshot
│   │   ├── values/                   # Score, Recency, Recommendation
│   │   ├── services/                 # 점수 계산, 추천 변환 (pure functions)
│   │   └── ports/                    # Protocol (추상 인터페이스)
│   │       ├── ohlcv_provider.py
│   │       ├── flow_provider.py      # 외국인/기관 매매동향
│   │       ├── disclosure_provider.py
│   │       ├── notifier.py
│   │       └── report_repository.py
│   │
│   ├── application/                  # ❷ 유스케이스 (오케스트레이션)
│   │   ├── dto/                      # pydantic 입출력 (경계)
│   │   └── use_cases/
│   │       ├── select_stocks.py
│   │       ├── analyze_indicators.py
│   │       ├── analyze_issues.py
│   │       ├── generate_report.py
│   │       └── run_pipeline.py       # Orchestrator
│   │
│   ├── adapters/                     # ❸ 외부 시스템 구현 (포트 구현)
│   │   ├── inbound/
│   │   │   └── cli.py                # typer 진입점
│   │   └── outbound/
│   │       ├── pykrx_ohlcv.py
│   │       ├── pykrx_flow.py
│   │       ├── dart_disclosure.py
│   │       ├── telegram_notifier.py
│   │       └── filesystem_report_repository.py
│   │
│   ├── infrastructure/               # ❹ Cross-cutting (config, log, di)
│   │   ├── config.py                 # YAML + .env (pydantic-settings)
│   │   ├── logging.py
│   │   ├── container.py              # Composition Root (DI)
│   │   └── clock.py                  # 시간 추상화 (테스트 용)
│   │
│   └── main.py                       # 진입점: container 빌드 + 실행
│
├── tests/
│   ├── unit/
│   │   ├── domain/                   # 가장 많이, 가장 빠름
│   │   └── application/              # fake 어댑터 사용
│   ├── integration/                  # 실제 어댑터 (또는 HTTP mock)
│   ├── e2e/                          # 전체 흐름 1~2개
│   ├── fakes/                        # in-memory 가짜 어댑터
│   └── conftest.py                   # 공통 fixture
│
└── (기존) docs/, config/, .claude/, scripts/, data/
```

### 의존성 방향 (위반 시 mypy 또는 ruff로 검출)

```
infrastructure ─► application ─► domain
       ▲                          ▲
       │                          │
    adapters ──────────────────────
       (outbound: domain.ports 구현)
       (inbound:  application.use_cases 호출)
```

❌ `domain` → `pandas` import: 금지
❌ `application` → `httpx` import: 금지 (어댑터 통해서만)
✅ `adapters/outbound/pykrx_ohlcv.py` → `pandas`, `pykrx` import: OK
✅ `infrastructure/container.py` → 모든 어댑터 import: OK (이게 유일하게 허용된 곳)

---

## 3. 환경 셋업 (uv)

```bash
# 1. uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Python 3.11 설치 + 가상환경
cd /Users/daehyeon_kim/dev/kor_trading
uv python install 3.11
uv venv

# 3. 의존성 추가
uv add pandas pandas-ta pykrx FinanceDataReader httpx pydantic pydantic-settings \
       structlog typer pyyaml

# 4. dev 의존성
uv add --dev pytest pytest-cov pytest-mock freezegun respx \
              mypy ruff pre-commit

# 5. pre-commit 활성화
uv run pre-commit install

# 6. 명령 실행 (가상환경 자동 활성화 없이)
uv run pytest
uv run mypy src/
uv run ruff check src/ tests/
uv run python -m kor_trading
```

### `pyproject.toml` 핵심 설정 발췌

```toml
[project]
name = "kor-trading"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF", "TCH", "ARG", "PL"]
ignore = ["PLR0913"]  # too many args

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --cov=src/kor_trading --cov-report=term-missing"

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]
```

---

## 4. TDD 워크플로우

### Red → Green → Refactor

1. **Red**: 실패하는 테스트를 먼저 작성한다.
2. **Green**: 통과하는 **최소한**의 코드를 작성한다.
3. **Refactor**: 중복 제거, 명료화. 테스트가 계속 통과하는지 확인.

### 안쪽부터 작성 (Outside-in vs Inside-out)

이 프로젝트는 **inside-out** 권장:
1. domain 엔티티/값 객체부터 (순수, 빠른 피드백)
2. domain 서비스 (점수 계산 같은 pure function)
3. application 유스케이스 (fake 어댑터 사용)
4. 마지막에 adapter 구현 (실제 또는 통합 테스트)

### 테스트 더블 전략 (Classicist 권장)

| 레이어 | 테스트 종류 | 더블 사용 |
|---|---|---|
| domain | unit | 더블 없음. 순수 객체만. |
| application | unit | **fake 어댑터** (in-memory 구현) 주입 |
| adapter | integration | 실제 외부 (또는 HTTP mock — respx) |
| e2e | end-to-end | 통합. 1~2개만. |

> Mock은 외부 시스템(HTTP, 파일, 시간)에만. 도메인 객체를 mock하지 말 것.

### Fake 어댑터 (`tests/fakes/`)

도메인 포트의 in-memory 구현. 유스케이스 테스트의 핵심.

```python
# tests/fakes/fake_ohlcv_provider.py
from kor_trading.domain.entities import OhlcvBar
from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider

class FakeOhlcvProvider(OhlcvProvider):
    def __init__(self) -> None:
        self._data: dict[str, list[OhlcvBar]] = {}

    def add(self, ticker: str, bars: list[OhlcvBar]) -> None:
        self._data[ticker] = bars

    def get_daily(self, ticker: str, days: int) -> list[OhlcvBar]:
        return self._data.get(ticker, [])[-days:]
```

---

## 5. 핵심 패턴 — 코드로 보는 Hexagonal

### 5.1 도메인 엔티티 (frozen dataclass, framework 0 의존)

```python
# src/kor_trading/domain/entities/ticker.py
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Ticker:
    code: str       # "005930"
    name: str       # "삼성전자"
    market: str     # "KOSPI" | "KOSDAQ"

    def __post_init__(self) -> None:
        if not (self.code.isdigit() and len(self.code) == 6):
            raise ValueError(f"invalid ticker code: {self.code}")
```

### 5.2 값 객체 (값으로 비교, 불변)

```python
# src/kor_trading/domain/values/score.py
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Score:
    value: float  # -1.0 ~ +1.0

    def __post_init__(self) -> None:
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"score out of range: {self.value}")

    def weighted(self, w: float) -> "Score":
        return Score(self.value * w)
```

### 5.3 포트 (Protocol — typing 기반 덕타이핑)

```python
# src/kor_trading/domain/ports/ohlcv_provider.py
from typing import Protocol
from kor_trading.domain.entities.ohlcv_bar import OhlcvBar

class OhlcvProvider(Protocol):
    def get_daily(self, ticker: str, days: int) -> list[OhlcvBar]: ...
```

> `Protocol`을 쓰면 구현체가 명시적 상속 없이도 타입 호환된다 (덕타이핑 + 정적 검사).

### 5.4 도메인 서비스 (pure function — 가장 테스트하기 쉬움)

```python
# src/kor_trading/domain/services/indicator_scoring.py
from kor_trading.domain.values.score import Score
from kor_trading.domain.values.indicator_snapshot import IndicatorSnapshot

def compute_overall_score(snap: IndicatorSnapshot, weights: dict[str, float]) -> Score:
    total = (
        snap.trend.value * weights["trend"]
        + snap.momentum.value * weights["momentum"]
        + snap.volatility.value * weights["volatility"]
        + snap.volume.value * weights["volume"]
        + snap.flow.value * weights["flow"]
    )
    return Score(max(-1.0, min(1.0, total)))
```

### 5.5 유스케이스 (포트만 의존, framework 0)

```python
# src/kor_trading/application/use_cases/select_stocks.py
from dataclasses import dataclass
from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider
from kor_trading.application.dto.selection import SelectionCriteria, SelectionResult

@dataclass
class SelectStocksUseCase:
    ohlcv: OhlcvProvider  # 포트만 의존

    def execute(self, criteria: SelectionCriteria) -> SelectionResult:
        # 1. 전체 종목 fetch
        # 2. 거래대금 Top N, 급등 Top N, 급락 Top N 분리
        # 3. 합집합, 필터 (시총, 우선주 등) 적용
        # 4. SelectionResult 반환
        ...
```

### 5.6 어댑터 (포트 구현 — pandas/pykrx 등 외부 라이브러리는 여기서만)

```python
# src/kor_trading/adapters/outbound/pykrx_ohlcv.py
from datetime import date, timedelta
import pykrx.stock as ks
from kor_trading.domain.entities.ohlcv_bar import OhlcvBar
from kor_trading.domain.ports.ohlcv_provider import OhlcvProvider

class PykrxOhlcvProvider:  # Protocol을 묵시적으로 구현
    def get_daily(self, ticker: str, days: int) -> list[OhlcvBar]:
        end = date.today()
        start = end - timedelta(days=days * 2)  # 휴장일 보정
        df = ks.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
        return [OhlcvBar(...) for _, row in df.tail(days).iterrows()]
```

### 5.7 Composition Root (모든 구체를 아는 유일한 곳)

```python
# src/kor_trading/infrastructure/container.py
from kor_trading.infrastructure.config import Settings
from kor_trading.adapters.outbound.pykrx_ohlcv import PykrxOhlcvProvider
from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider
from kor_trading.adapters.outbound.telegram_notifier import TelegramNotifier
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase
from kor_trading.application.use_cases.run_pipeline import RunPipelineUseCase

def build_pipeline(settings: Settings) -> RunPipelineUseCase:
    ohlcv = PykrxOhlcvProvider()
    disclosures = DartDisclosureProvider(api_key=settings.dart_api_key)
    notifier = TelegramNotifier(token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)
    # ... 다른 어댑터들

    select_uc = SelectStocksUseCase(ohlcv=ohlcv)
    # ... 다른 유스케이스들

    return RunPipelineUseCase(
        select=select_uc,
        # ...
        notifier=notifier,
    )
```

---

## 6. TDD 사이클 예시 — "거래대금 Top 50" 선정

### Step 1: Red (실패하는 테스트)

```python
# tests/unit/application/test_select_stocks.py
from kor_trading.application.use_cases.select_stocks import SelectStocksUseCase
from kor_trading.application.dto.selection import SelectionCriteria
from tests.fakes.fake_ohlcv_provider import FakeOhlcvProvider

def test_top_volume_returns_n_tickers_sorted_by_trading_value() -> None:
    # given
    ohlcv = FakeOhlcvProvider()
    ohlcv.add_market_snapshot(date="2026-05-26", bars=[
        ("005930", "삼성전자", "KOSPI", 78500, 25_300_000, 1_980_000_000_000),
        ("000660", "SK하이닉스", "KOSPI",   220_000,  8_000_000, 1_760_000_000_000),
        # ... 51건
    ])
    uc = SelectStocksUseCase(ohlcv=ohlcv)
    criteria = SelectionCriteria(top_volume_n=50, surge_top_n=0, plunge_top_n=0)

    # when
    result = uc.execute(criteria)

    # then
    assert len(result.candidates) == 50
    assert result.candidates[0].ticker == "005930"  # 거래대금 1위
```

이 시점에 `SelectStocksUseCase`는 존재하지 않거나 비어 있어야 함 → 테스트 실패 (Red).

### Step 2: Green (최소 구현)

```python
# src/kor_trading/application/use_cases/select_stocks.py
@dataclass
class SelectStocksUseCase:
    ohlcv: OhlcvProvider

    def execute(self, criteria: SelectionCriteria) -> SelectionResult:
        snapshot = self.ohlcv.get_market_snapshot()
        by_value = sorted(snapshot, key=lambda b: b.trading_value, reverse=True)
        candidates = by_value[: criteria.top_volume_n]
        return SelectionResult(candidates=candidates)
```

테스트 통과 (Green).

### Step 3: 다음 Red — "급등 Top 10 추가"

```python
def test_surge_top_n_added_to_candidates() -> None:
    ...
    criteria = SelectionCriteria(top_volume_n=0, surge_top_n=10, plunge_top_n=0)
    result = uc.execute(criteria)
    assert all(c.change_pct >= 0 for c in result.candidates[:10])
```

→ 구현 → Refactor (합집합 로직 추출) → 다음 케이스로.

### Step 4: 엣지 케이스

- 거래대금 ↑ + 시총 < 500억 → 필터링되는지
- 우선주 → 제외되는지
- 동일 종목이 거래량 + 급등 둘 다 해당 → 한 번만 포함되는지
- 휴장일 → 가장 최근 영업일로 자동 조정되는지

각 케이스마다 Red → Green → Refactor.

---

## 7. 테스트 전략

### 7.1 단위 테스트 (`tests/unit/`)

- 도메인: 순수 객체, 테스트는 빠르고 많이 (테스트 1ms 이내)
- 유스케이스: fake 어댑터 주입, 비즈니스 흐름 검증
- **빠르고 결정적**: 외부 호출 0, 랜덤 0, 시간 의존 시 `freezegun`

### 7.2 통합 테스트 (`tests/integration/`)

- 어댑터 단위 (pykrx, DART, telegram 각각)
- HTTP는 `respx`로 mock (실제 네트워크 안 탐)
- pykrx는 통신 라이브러리라 mock하거나 한 번 fetch해서 fixture로

```python
# tests/integration/adapters/test_dart_disclosure.py
import respx
from kor_trading.adapters.outbound.dart_disclosure import DartDisclosureProvider

@respx.mock
def test_fetches_recent_disclosures() -> None:
    respx.get("https://opendart.fss.or.kr/api/list.json").mock(
        return_value=httpx.Response(200, json={"list": [...]})
    )
    provider = DartDisclosureProvider(api_key="test")
    result = provider.get_recent("005930", days=7)
    assert len(result) > 0
```

### 7.3 e2e 테스트 (`tests/e2e/`)

- 전체 파이프라인 1~2개 시나리오만
- 모든 어댑터를 fake로 → orchestrator 흐름 검증
- 또는 실제 외부에 한 번씩 (CI 분리 권장, MVP는 생략 가능)

### 7.4 커버리지 목표

| 레이어 | 목표 |
|---|---|
| domain | 95%+ (순수 함수만 있어 어렵지 않음) |
| application | 90%+ |
| adapters | 70%+ (외부 의존성 제외) |
| infrastructure | 60% (대부분 boilerplate) |

`pytest --cov` 리포트로 확인. 90% 미만 PR은 리뷰 거절 권장 (운영 시 룰).

### 7.5 테스트 명명

```python
# pattern: test_<action>_<given_when>_<expected>
def test_select_stocks_with_market_cap_filter_excludes_micro_caps() -> None: ...
def test_recency_decay_for_today_returns_full_weight() -> None: ...
```

### 7.6 시간 / 랜덤 처리

- 시간이 필요한 곳은 `Clock` 포트 통해서만. 테스트에서는 `FakeClock`.

```python
# domain/ports/clock.py
class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...
```

---

## 8. 의존성 주입 (수동 DI, 충분)

이 프로젝트 크기에서는 **생성자 주입 + composition root** 만으로 충분. `dependency-injector` 같은 라이브러리는 오버킬.

**규칙**:
- 클래스는 자기 의존성을 **생성자**에서만 받는다 (필드에 보관)
- `new`/`global`/`singleton` 패턴 금지 (테스트성 ↓)
- `container.py`에서만 `new` 호출

```python
# 좋은 예
@dataclass
class GenerateReportUseCase:
    indicator_analyst: AnalyzeIndicatorsUseCase  # 다른 유스케이스 의존
    issue_analyst: AnalyzeIssuesUseCase
    notifier: Notifier                            # 포트
    repository: ReportRepository                  # 포트

# 나쁜 예 (전역 의존, 테스트 불가)
class GenerateReportUseCase:
    def execute(self) -> None:
        notifier = TelegramNotifier(os.environ["..."])  # ❌ 직접 생성
```

---

## 9. 설정 / 시크릿 로드

### `infrastructure/config.py`

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

class Settings(BaseSettings):
    """`.env` 자동 로드"""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    telegram_chat_id: str
    dart_api_key: str
    kis_app_key: str | None = None
    kis_app_secret: str | None = None

class AppConfig:
    """`config/default.yaml` + Settings 합친 컨테이너"""
    def __init__(self, yaml_path: Path = Path("config/default.yaml")) -> None:
        with yaml_path.open("r", encoding="utf-8") as f:
            self.yaml = yaml.safe_load(f)
        self.secrets = Settings()  # 자동으로 .env 로드

    @property
    def schedule(self) -> dict: return self.yaml["schedule"]
    @property
    def selection(self) -> dict: return self.yaml["selection"]
    # ...
```

> pydantic-settings가 `.env` → 환경변수 → 클래스 필드로 자동 매핑. 누락 시 컴파일 타임 같은 에러.

---

## 10. 로깅 (structlog)

```python
# infrastructure/logging.py
import structlog
import logging

def configure_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
    )

# 사용
log = structlog.get_logger()
log.info("selection.start", market="KOSPI", criteria={"top_volume_n": 50})
log.info("selection.done", candidates=42, duration_ms=1230)
```

JSON 라인 로그로 출력 → `data/reports/{date}/{HHmm}/meta.json`에서 파싱하기 좋음.

---

## 11. 에러 처리

### 도메인 예외는 도메인에서

```python
# domain/exceptions.py
class DomainError(Exception):
    """모든 도메인 예외의 부모"""

class InvalidScoreRange(DomainError): ...
class MarketHolidayError(DomainError):
    def __init__(self, requested_date: date, latest_business_day: date) -> None:
        self.requested_date = requested_date
        self.latest_business_day = latest_business_day
        super().__init__(f"{requested_date}는 휴장. 직전 영업일 {latest_business_day} 사용 권장.")
```

### 어댑터에서 외부 예외 → 도메인 예외로 변환

```python
# adapters/outbound/dart_disclosure.py
try:
    resp = httpx.get(url, params=params)
    resp.raise_for_status()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 429:
        raise RateLimitedError(...) from e
    raise ExternalServiceError("DART") from e
```

> **외부 라이브러리 예외는 절대 application/domain까지 전파시키지 말 것.** 어댑터에서 catch + 도메인 예외로 wrap.

### 부분 실패 허용

Orchestrator는 종목 하나가 실패해도 나머지로 진행해야 한다.

```python
# application/use_cases/run_pipeline.py
results: list[StockAnalysis] = []
errors: list[StockError] = []

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(self._analyze_one, t): t for t in candidates}
    for f in as_completed(futures):
        ticker = futures[f]
        try:
            results.append(f.result(timeout=30))
        except Exception as e:
            errors.append(StockError(ticker, repr(e)))
            log.error("analyze.failed", ticker=ticker.code, error=str(e))
```

---

## 12. 병렬화 (ThreadPoolExecutor)

I/O bound 작업(API 호출)이므로 GIL 영향 없음. CPU bound(pandas-ta 지표 계산)도 종목당 ~수십 ms 수준이라 thread로 충분.

```python
# application/use_cases/run_pipeline.py
from concurrent.futures import ThreadPoolExecutor, as_completed

def analyze_all(candidates: list[Ticker], max_workers: int = 4) -> list[Analysis]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(analyze_one, t) for t in candidates]
        return [f.result(timeout=30) for f in as_completed(futures)]
```

- `max_workers`: 4~8 권장. DART API rate limit(분당 1000회) 안에 들도록.
- 외부 API rate limit 위반 시 `time.sleep` 또는 토큰 버킷 (`adapters/outbound/rate_limit.py`).

---

## 13. CLI / Claude 서브에이전트 통합

### typer CLI (직접 실행)

```python
# adapters/inbound/cli.py
import typer
from kor_trading.infrastructure.container import build_pipeline
from kor_trading.infrastructure.config import AppConfig

app = typer.Typer()

@app.command()
def run(date: str | None = None, market: str | None = None) -> None:
    config = AppConfig()
    pipeline = build_pipeline(config)
    result = pipeline.execute(date=date, market=market)
    typer.echo(result.report_path)

if __name__ == "__main__":
    app()
```

### Claude 서브에이전트와의 연결

Claude 서브에이전트(`.claude/agents/*.md`)는 다음 둘 중 하나로 동작:

1. **Python CLI를 Bash로 호출**: `claude -p` 진입 → orchestrator agent가 `uv run python -m kor_trading run` 실행
2. **Python을 도구처럼 사용**: 에이전트가 단계별로 `python -c "from kor_trading.application... ; ..."` 호출

**MVP는 1번 권장**. 에이전트는 워크플로우 지시만 하고, 실제 로직은 Python이 담당.

```
orchestrator.md (Claude 서브에이전트)
  └─ Bash: `uv run python -m kor_trading run --config config/default.yaml`
              └─ src/kor_trading/main.py
                    └─ container.build_pipeline() → execute()
```

---

## 14. Pre-commit 훅

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.x.x
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.x.x
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-PyYAML]
        args: [--strict]
```

커밋 시 자동 실행. 실패하면 커밋 불가 → 깨끗한 main 유지.

---

## 15. 폴더 의존성 강제 (architecture test)

mypy + import linter로 의존성 위반을 자동 검출.

```toml
# pyproject.toml (import-linter)
[tool.importlinter]
root_package = "kor_trading"

[[tool.importlinter.contracts]]
name = "Domain has no external deps"
type = "forbidden"
source_modules = ["kor_trading.domain"]
forbidden_modules = ["pandas", "pykrx", "httpx", "pydantic", "kor_trading.adapters", "kor_trading.application", "kor_trading.infrastructure"]

[[tool.importlinter.contracts]]
name = "Application depends only on domain (+ stdlib + pydantic)"
type = "forbidden"
source_modules = ["kor_trading.application"]
forbidden_modules = ["kor_trading.adapters", "kor_trading.infrastructure", "pandas", "pykrx", "httpx"]
```

`uv run lint-imports`로 검사. CI에 추가.

---

## 16. 개발 흐름 (실제 한 사이클)

새 기능 "거래량 급증 종목 추가 선정"을 구현한다고 하면:

1. **PRD 확인** — `docs/PRD.md` § 3.2 + `docs/INDICATORS.md`에서 정의 찾기
2. **테스트 작성** — `tests/unit/application/test_select_stocks.py`에 새 케이스 추가 (Red)
3. **DTO 변경** — `application/dto/selection.py`에 `volume_spike_n` 필드 추가
4. **유스케이스 구현** — `select_stocks.py`에 로직 추가 (Green)
5. **Refactor** — 중복 제거, 명료화
6. **통합 테스트** — pykrx 어댑터에 거래량 평균 fetch 필요하면 `tests/integration/`에 추가
7. **mypy / ruff / pre-commit 통과** 확인
8. **`config/default.yaml` 업데이트** — 새 파라미터 기본값
9. **`docs/CONFIG.md` 갱신** — 사용자가 변경하는 법
10. **PRD 갱신 (필요 시)** — § 3.2 + 변경 이력
11. 커밋

---

## 17. 빠른 시작 (새 개발자 온보딩)

```bash
# 1. 클론 + 환경
git clone <repo> kor_trading && cd kor_trading
uv sync                              # 의존성 설치 (uv.lock 기반)

# 2. 시크릿
cp .env.example .env
$EDITOR .env                         # 텔레그램·DART 키 입력

# 3. 테스트 한 번
uv run pytest                        # 모두 green이어야 함

# 4. 타입 / 린트
uv run mypy src/
uv run ruff check src/ tests/

# 5. 수동 실행
uv run python -m kor_trading run --dry-run

# 6. Pre-commit 활성화
uv run pre-commit install
```

---

## 18. PR / 브랜치 워크플로우 ⭐

### 18.1 원칙
- **모든 작업은 적절한 단위로 PR로 분리**한다. **main 직접 푸시 금지**.
- 한 PR = 한 가지 일. "지표 분석 + 텔레그램 수정"처럼 두 가지 섞지 말 것.
- 큰 작업은 같은 task에서 여러 PR로 쪼개고, PR 제목의 끝 번호로 순서를 표시한다.

### 18.2 브랜치 명명
- `feat/<영문 슬러그>` — 새 기능
- `fix/<영문 슬러그>` — 버그 수정
- `chore/<영문 슬러그>` — 설정/문서/리팩터링
- `test/<영문 슬러그>` — 테스트만 추가

예) `feat/stock-selector-top-volume`, `chore/pr-template`

### 18.3 PR 제목 형식 (✅ 확정)
```
[task 번호]-task 제목-번호
```
- `task 번호`: 작업 트래킹 번호 (없으면 `0` = 셋업/잡일)
- `task 제목`: 한국어 또는 영어, 간결하게
- 끝의 `번호`: 같은 task가 여러 PR로 쪼개진 경우 순번 (단일 PR이면 `1`)

예시
- `[1]-도메인 엔티티 구현-1`
- `[1]-도메인 엔티티 구현-2` (같은 task의 2번째 PR)
- `[3]-Stock Selector 유스케이스-1`
- `[0]-PR 템플릿 도입-1`

### 18.4 PR 본문 (`.github/PULL_REQUEST_TEMPLATE.md` 자동 적용)
4개 섹션을 **반드시** 모두 채운다:

1. **관련 컨텍스트** — 관련 PRD 섹션, 이슈 번호, 배경 결정
2. **목적** — 이 PR이 달성하려는 것 (WHY)
3. **변경사항 요약** — 무엇이 어떻게 바뀌었는지 (WHAT, 파일/모듈 단위)
4. **이슈 & 고민** — 미해결 사항, 후속 작업, 트레이드오프, 리뷰 요청

각 섹션에 항목이 여러 개면 `### 1.`, `### 2.` 식으로 번호 매김.

### 18.5 PR 크기 가이드
- **이상적**: 200~400 라인 변경
- 800라인 넘으면 분할 고려
- **문서만 변경**하는 PR은 1000라인 넘어도 OK

### 18.6 머지 정책
- pre-commit 통과 필수 (ruff + mypy)
- 모든 테스트 green
- (추후) CI green
- **Squash merge 권장** — main 히스토리 깔끔하게

### 18.7 워크플로우 예시
```bash
# 1. main 최신화
git checkout main && git pull

# 2. 브랜치 생성
git checkout -b feat/stock-selector-top-volume

# 3. TDD 사이클 반복 → 변경 커밋
# (작은 커밋 여러 개 OK — squash로 정리됨)

# 4. push
git push -u origin feat/stock-selector-top-volume

# 5. PR 생성 (gh CLI)
gh pr create --title "[3]-Stock Selector 유스케이스-1" --body "..."

# 6. 리뷰 + 머지 후 브랜치 정리
git checkout main && git pull && git branch -d feat/stock-selector-top-volume
```

---

## 19. 안티 패턴 (피해야 할 것)

❌ **god object**: 하나의 유스케이스가 5개 이상의 어댑터에 의존 → 분할 필요
❌ **anemic domain**: 엔티티가 getter/setter만 있고 로직은 service에 있음 → 엔티티에 로직 넣기
❌ **leaky abstraction**: 포트 인터페이스에 pandas DataFrame을 그대로 노출 → 도메인 타입으로 감싸기
❌ **테스트가 구현 디테일을 검증**: `mock.assert_called_with(...)` 남발 → 결과 행동을 검증할 것
❌ **try/except로 silent fail**: 로그 없이 빈 결과 반환 → 명시적 에러 또는 로깅
❌ **시간/랜덤 직접 사용**: `datetime.now()` 직접 호출 → Clock 포트 통해서
❌ **싱글톤·모듈 전역 상태**: `_cache = {}` 같은 모듈 변수 → DI로 주입

---

## 20. 참고 자료

- Robert C. Martin, "Clean Architecture"
- Alistair Cockburn, "Hexagonal architecture" 원문
- Kent Beck, "Test-Driven Development: By Example"
- pytest docs: https://docs.pytest.org
- uv docs: https://docs.astral.sh/uv/
- structlog: https://www.structlog.org/
- pydantic v2: https://docs.pydantic.dev/

---

## 21. 변경 이력
- 2026-05-26: v0.2 — § 18 **PR / 브랜치 워크플로우** 신설 (제목 형식, 본문 템플릿, 머지 정책).
- 2026-05-26: v0.1 — 초안 작성. uv + sync/ThreadPool + Pydantic+dataclass+mypy strict 조합 확정.
