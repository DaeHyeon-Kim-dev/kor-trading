"""시장 개요(KOSPI/KOSDAQ 폭). 인자 없음."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
import ktrade  # noqa: E402

print(ktrade.market_md(ktrade.today()))
