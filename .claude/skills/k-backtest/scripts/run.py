"""셋업 백테스트. 사용: run.py [종목명|코드 ...]  (없으면 거래대금 상위 20종목)"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

codes = [a for a in sys.argv[1:] if a.strip()]
print(ktrade.backtest_md(codes, ktrade.today()))
