"""장중 실시간 거래대금 상위(KIS). 인자 없음."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

print(ktrade.value_rank_md(ktrade.today()))
