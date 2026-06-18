"""데일리 저널.
사용:
  run.py record   → 오늘의 예측(스크리너 셋업)을 저널에 기록
  run.py review   → 직전 저널의 예측을 오늘 실제가로 검증
  run.py          → review (기본)
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

cmd = sys.argv[1] if len(sys.argv) > 1 else "review"
if cmd == "record":
    print(ktrade.journal_record_md(ktrade.today()))
else:
    print(ktrade.journal_review_md(ktrade.today()))
