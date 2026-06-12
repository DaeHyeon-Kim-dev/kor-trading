---
description: 페이퍼 트레이딩(모의) 로깅으로 셋업 신호를 기록하고, 이후 실제 가격으로 결과를 채점해 forward 검증한다. "이거 페이퍼로 기록해줘", "지금까지 기록한 신호 결과 어때", "모의매매 성과" 같은 요청에 사용. 백테스트(과거)와 달리 실시간 기록→미래 추적.
argument-hint: [log <종목>...] | (없으면 현황)
allowed-tools: Bash
---

# 페이퍼 트레이딩 로깅 (k-paper)

셋업 신호를 기록하고, 시간이 지난 뒤 실제 가격으로 채점한다.

```bash
cd "${CLAUDE_SKILL_DIR}/../../.." && export PATH="$HOME/.local/bin:$PATH" && uv run python "${CLAUDE_SKILL_DIR}/scripts/run.py" $ARGUMENTS
```

- `k-paper log 삼성전자 000660` → 두 종목의 현재 셋업을 페이퍼로 기록(셋업 없으면 미기록).
- `k-paper` → 기록된 신호의 현황: **청산된 건은 forward 결과(승/패/R)**, 미청산 건은 진행 상황.

## 출력 활용
- 청산 결과 표(승률·평균R)는 **실시간 기록 이후 실제로 어떻게 됐는지** = 진짜 forward 검증이다. 그대로 보여준다.
- 표본이 쌓이는 데 시간이 걸린다(보유 최대 20거래일). 초반엔 미청산이 많은 게 정상.
- 백테스트(과거 재현)와 달리 **미래 편향 없는 검증**임을 짚어준다.
- 기록은 `data/paper/trades.jsonl`에 누적된다.
