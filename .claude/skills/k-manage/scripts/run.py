"""보유 포지션 관리. 사용: run.py <종목명|코드> <평단가>  예) 005930 71000"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

args = [a for a in sys.argv[1:] if a.strip()]
if len(args) < 2:
    print("사용법: <종목명|코드> <평단가>  예) 삼성전자 71000")
    sys.exit(0)

avg_raw = args[-1].replace(",", "").replace("원", "")
query = " ".join(args[:-1])
try:
    avg_cost = int(avg_raw)
except ValueError:
    print(f"❌ 평단가를 숫자로 입력하세요(받은 값: {args[-1]!r}). 예) 005930 71000")
    sys.exit(0)

print(ktrade.manage_md(query, avg_cost, ktrade.today()))
