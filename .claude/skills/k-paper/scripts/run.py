"""페이퍼 트레이딩 로깅/현황.
사용:
  run.py log <종목명|코드> [...]   → 현재 셋업을 페이퍼로 기록
  run.py                            → 기록된 페이퍼 트레이드 현황·forward 성과
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

args = [a for a in sys.argv[1:] if a.strip()]
if args and args[0] == "log":
    print(ktrade.paper_log_md(args[1:], ktrade.today()))
else:
    print(ktrade.paper_status_md(ktrade.today()))
