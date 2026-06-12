---
description: 오늘 한국 증시(KOSPI·KOSDAQ) 전체 분위기를 요약한다. 상승/하락/보합 종목 수, 평균 등락률, 거래대금, 강세/약세/혼조 판정. "오늘 장 어때", "시장 분위기", "코스피 코스닥 상황" 같은 요청에 사용.
allowed-tools: Bash
---

# 시장 개요 (k-market)

```bash
cd "${CLAUDE_SKILL_DIR}/../../.." && export PATH="$HOME/.local/bin:$PATH" && uv run python "${CLAUDE_SKILL_DIR}/scripts/run.py"
```

## 출력 활용
- KOSPI/KOSDAQ 두 줄을 그대로 보여준다.
- 강세/약세에 따라 "오늘은 매수 우호적/관망 우위" 같은 한 줄 톤을 덧붙인다.
- 기준일이 직전 거래일일 수 있으니 날짜를 함께 안내한다.
