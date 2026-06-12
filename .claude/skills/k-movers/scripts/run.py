"""오늘의 급등·급락·거래량 상위. 인자 없음."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

print(ktrade.movers_md(ktrade.today()))
