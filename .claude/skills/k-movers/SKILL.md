---
description: 오늘 한국 증시의 거래대금 상위·급등·급락 종목을 표로 보여준다. "오늘 거래량 급등한 주식 알려줘", "지금 급락 종목 뭐 있어", "오늘 핫한 종목", "거래대금 상위" 같은 요청에 사용.
allowed-tools: Bash
---

# 오늘의 무버스 (k-movers)

거래대금 상위 / 급등 / 급락 종목을 조회한다.

```bash
cd "${CLAUDE_SKILL_DIR}/../../.." && export PATH="$HOME/.local/bin:$PATH" && uv run python "${CLAUDE_SKILL_DIR}/scripts/run.py"
```

## 출력 활용
- 세 표(거래대금·급등·급락)를 그대로 보여준다.
- 급등 상위에 상한가(+29~30%)가 몰려 있으면 "테마/이벤트 가능성"을 한 줄로 짚어준다.
- 사용자가 특정 종목에 관심을 보이면 **k-analyze**(종목 분석)로 이어가도록 제안한다.
