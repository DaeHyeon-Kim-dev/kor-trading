---
description: 특정 한국 주식의 외국인·기관 수급(최근 5일/20일 누적 순매수, 억원)을 조회한다. "삼성전자 외국인 사고 있어", "이 종목 기관 수급 어때", "000660 수급" 같은 요청에 사용. KIS Open API 사용.
argument-hint: <종목명 또는 6자리코드>
allowed-tools: Bash
---

# 외국인·기관 수급 (k-flow)

```bash
cd "${CLAUDE_SKILL_DIR}/../../.." && export PATH="$HOME/.local/bin:$PATH" && uv run python "${CLAUDE_SKILL_DIR}/scripts/run.py" $ARGUMENTS
```

## 출력 활용
- 외국인·기관의 5일/20일 순매수(억원)를 그대로 보여준다.
- 양쪽 모두 순매수면 "수급 우호", 양쪽 순매도면 "수급 이탈"로 한 줄 해석.
- 5일과 20일 방향이 다르면(예: 20일 매수·5일 매도) "단기 차익실현 가능성"을 짚어준다.
