"""지금 매수할 만한 종목 스크리닝. 인자 없음(거래대금/급등 후보 스캔)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

print(ktrade.screen_md(ktrade.today()))
