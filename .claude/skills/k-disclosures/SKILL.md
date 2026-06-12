---
description: 특정 한국 주식의 최근 공시(DART)를 가져와 호재/악재/중립으로 분류한다. "삼성전자 최근 공시 있어", "이 종목 무슨 일 있었어", "035720 공시 호재야 악재야" 같은 요청에 사용. 노이즈 공시(소유상황보고 등)는 자동 제외.
argument-hint: <종목명 또는 6자리코드>
allowed-tools: Bash
---

# 최근 공시 + 호재/악재 분류 (k-disclosures)

```bash
cd "${CLAUDE_SKILL_DIR}/../../.." && export PATH="$HOME/.local/bin:$PATH" && uv run python "${CLAUDE_SKILL_DIR}/scripts/run.py" $ARGUMENTS
```

분류는 로컬 Claude로 수행되어 수 초~십수 초 걸릴 수 있다.

## 출력 활용
- 공시 목록과 호재/악재/중립 마크를 그대로 보여준다.
- 호재·악재가 섞여 있으면 영향도(impact)가 높은 쪽을 우선 강조한다.
- "분류 대상 공시 없음"이면 최근 특이 공시가 없다는 뜻이라고 안내한다.
- 공시 해석은 매매 권유가 아니라 참고 정보임을 명시한다.
