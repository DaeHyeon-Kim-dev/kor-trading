"""외국인·기관 수급. 사용: run.py <종목명|6자리코드>"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

query = " ".join(sys.argv[1:]).strip()
if not query:
    print("사용법: 종목명 또는 6자리 코드를 인자로 주세요. 예) 삼성전자 / 005930")
    sys.exit(0)
print(ktrade.flow_md(query, ktrade.today()))
