# 설정 가이드

> 자주 바뀌는 설정은 모두 `config/default.yaml`에서 관리한다.
> 시크릿(API 키, 토큰)은 `.env`에서 별도로 관리한다.

---

## 1. 실행 주기 변경

### 1.1 `config/default.yaml` 수정
```yaml
schedule:
  interval_seconds: 300    # 5분
  # interval_seconds: 600  # 10분
  # interval_seconds: 3600 # 1시간
```

### 1.2 launchd plist 동기화
`scripts/com.kortrading.daily.plist`의 `<StartInterval>` 값을 동일하게 맞춘다.

```xml
<key>StartInterval</key>
<integer>300</integer>  <!-- 위 interval_seconds와 동일 -->
```

### 1.3 재로드
```bash
launchctl unload ~/Library/LaunchAgents/com.kortrading.daily.plist
launchctl load   ~/Library/LaunchAgents/com.kortrading.daily.plist
```

> **장 시간 외에는 자동 스킵**됨 (`active_hours_kst`, `active_weekdays`로 제어).
> 5분 주기로 돌려도 평일 08:30~16:30 외에는 실행 안 되어 알림 폭주가 안 일어남.

---

## 2. 종목 선정 기준 변경

`config/default.yaml`의 `selection` 섹션:

```yaml
selection:
  top_volume_n: 50      # 거래대금 상위 N (✅ 기본값)
  surge_top_n: 10       # 급등 Top N (✅ 기본값)
  plunge_top_n: 10      # 급락 Top N (✅ 기본값)
  market_cap_min_krw: 50_000_000_000  # 시총 하한 (500억)
  max_candidates: 30    # 지표·이슈 분석 대상 cap
```

**자주 쓰는 변경 시나리오**

| 시나리오 | 변경 |
|---|---|
| "코스닥 소형주만 보고싶다" | `market_cap_min_krw: 10_000_000_000` (100억) |
| "대형주만 보고싶다" | `market_cap_min_krw: 1_000_000_000_000` (1조) |
| "거래량 폭증만 찾기" | `top_volume_n: 20`, `surge_top_n: 0`, `plunge_top_n: 0` |
| "급락만 추적 (저점 매수)" | `surge_top_n: 0`, `plunge_top_n: 20` |

---

## 3. 뉴스 소스 변경

```yaml
news:
  sources:
    dart:
      enabled: true       # ✅ 확정 — MVP는 DART만
      priority: 1
    naver_finance:
      enabled: false      # 약관 검토 후 활성화
      priority: 2
```

DART OpenAPI 키는 `.env`의 `DART_API_KEY`로 관리.

---

## 4. 지표 파라미터 변경

`config/default.yaml`의 `indicators` 섹션에서 SMA 기간, MACD 파라미터 등 조정 가능.
종합 점수 가중치(`score_weights`)도 여기서 튜닝.

지표 의미와 적정값은 `docs/INDICATORS.md` 참조.

---

## 5. 시크릿 관리 (`.env`)

`.env.example` 복사 → `.env`로 저장 → 값 채우기.

```bash
# Telegram (확정 ✅)
TELEGRAM_BOT_TOKEN=1234567890:AAA...
TELEGRAM_CHAT_ID=123456789

# DART OpenAPI (https://opendart.fss.or.kr/)
DART_API_KEY=...

# (Phase 2) KIS Open API
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
```

⚠️ `.env`는 **반드시 `.gitignore`** 처리. 절대 커밋 금지.

---

## 6. 텔레그램 봇 셋업

1. 텔레그램에서 **@BotFather** 검색
2. `/newbot` → 봇 이름·핸들 설정 → **봇 토큰** 발급 → `TELEGRAM_BOT_TOKEN`에 저장
3. 만든 봇과 대화 시작 (`/start`)
4. 브라우저에서 `https://api.telegram.org/bot<TOKEN>/getUpdates` 접속
5. JSON 응답에서 `"chat":{"id":...}` 값 확인 → `TELEGRAM_CHAT_ID`에 저장

---

## 7. 변경 적용 흐름 요약

| 변경 항목 | 파일 | 재시작 필요? |
|---|---|---|
| 실행 주기 | `config/default.yaml` + plist | ✅ launchctl reload |
| 종목 선정 기준 | `config/default.yaml` | ❌ 다음 실행부터 반영 |
| 지표 파라미터 | `config/default.yaml` | ❌ |
| 뉴스 소스 on/off | `config/default.yaml` | ❌ |
| API 키 변경 | `.env` | ❌ |
