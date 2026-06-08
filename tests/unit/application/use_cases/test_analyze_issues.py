"""AnalyzeIssuesUseCase 테스트."""

from __future__ import annotations

from datetime import date

from kor_trading.application.use_cases.analyze_issues import AnalyzeIssuesUseCase
from kor_trading.domain.entities.disclosure import Disclosure, DisclosureSource
from kor_trading.domain.entities.issue import Impact, Sentiment
from kor_trading.domain.entities.ticker import Ticker
from kor_trading.domain.ports.sentiment_classifier import Classification
from tests.fakes.fake_disclosure_provider import FakeDisclosureProvider
from tests.fakes.fake_sentiment_classifier import FakeSentimentClassifier

AS_OF = date(2026, 5, 26)


def _t(code: str = "005930", name: str = "삼성전자") -> Ticker:
    return Ticker(code=code, name=name, market="KOSPI")


def _disclosure(code: str, title: str, d: date = AS_OF) -> Disclosure:
    return Disclosure(
        ticker_code=code,
        date=d,
        title=title,
        source=DisclosureSource.DART,
        source_url="https://...",
        report_type="주요사항보고",
    )


def _positive() -> Classification:
    return Classification(
        sentiment=Sentiment.POSITIVE,
        impact=Impact.HIGH,
        confidence=0.9,
        summary="호재",
    )


class TestEmpty:
    def test_no_tickers(self) -> None:
        uc = AnalyzeIssuesUseCase(
            disclosure_provider=FakeDisclosureProvider(),
            classifier=FakeSentimentClassifier(),
        )
        result = uc.execute([], AS_OF)
        assert result.items == ()

    def test_no_disclosures_yields_no_item(self) -> None:
        uc = AnalyzeIssuesUseCase(
            disclosure_provider=FakeDisclosureProvider(),
            classifier=FakeSentimentClassifier(default=_positive()),
        )
        result = uc.execute([_t()], AS_OF)
        assert result.items == ()
        assert result.score_for("005930") == 0.0


class TestNormalFlow:
    def test_builds_issues_and_score(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add("005930", [_disclosure("005930", "1분기 영업이익 사상 최대")])
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t()], AS_OF)
        assert len(result.items) == 1
        item = result.items[0]
        assert item.ticker_code == "005930"
        assert len(item.issues) == 1
        assert item.issues[0].sentiment == Sentiment.POSITIVE
        # 당일 공시 → decay 1.0, impact high=1.0, confidence 0.9 → 0.9
        assert result.score_for("005930") > 0.8

    def test_noise_disclosure_filtered_before_classify(self) -> None:
        # 노이즈 공시만 있으면 분류도 안 하고 item 없음
        disc = FakeDisclosureProvider()
        disc.add(
            "005930",
            [
                _disclosure("005930", "임원ㆍ주요주주특정증권등소유상황보고서"),
                _disclosure("005930", "대규모기업집단현황공시"),
            ],
        )
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)
        result = uc.execute([_t()], AS_OF)
        assert result.items == ()

    def test_material_kept_noise_dropped(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add(
            "005930",
            [
                _disclosure("005930", "단일판매ㆍ공급계약체결"),
                _disclosure("005930", "임원ㆍ주요주주특정증권등소유상황보고서"),
            ],
        )
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)
        result = uc.execute([_t()], AS_OF)
        assert len(result.items[0].issues) == 1  # 재료만 통과
        assert "공급계약" in result.items[0].issues[0].title

    def test_unclassifiable_disclosure_skipped(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add(
            "005930",
            [
                _disclosure("005930", "분류가능"),
                _disclosure("005930", "분류불가"),
            ],
        )
        clf = FakeSentimentClassifier()
        clf.set_for_title("분류가능", _positive())
        clf.set_for_title("분류불가", None)  # 분류 실패
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t()], AS_OF)
        assert len(result.items[0].issues) == 1

    def test_all_unclassifiable_yields_no_item(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add("005930", [_disclosure("005930", "x")])
        clf = FakeSentimentClassifier(default=None)
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)
        result = uc.execute([_t()], AS_OF)
        assert result.items == ()


class TestFailureIsolation:
    def test_one_ticker_failure_does_not_block_others(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add("000001", [_disclosure("000001", "호재")])
        disc.raise_for_ticker("000002")
        disc.add("000003", [_disclosure("000003", "호재")])
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t("000001"), _t("000002"), _t("000003")], AS_OF)
        codes = {item.ticker_code for item in result.items}
        assert codes == {"000001", "000003"}


class TestOrdering:
    def test_results_in_input_order(self) -> None:
        disc = FakeDisclosureProvider()
        for code in ("000003", "000001", "000002"):
            disc.add(code, [_disclosure(code, "호재")])
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t("000003"), _t("000001"), _t("000002")], AS_OF, max_workers=2)
        codes = [item.ticker_code for item in result.items]
        assert codes == ["000003", "000001", "000002"]


class TestHelpers:
    def test_issues_for_returns_empty_for_unknown(self) -> None:
        uc = AnalyzeIssuesUseCase(
            disclosure_provider=FakeDisclosureProvider(),
            classifier=FakeSentimentClassifier(),
        )
        result = uc.execute([], AS_OF)
        assert result.issues_for("999999") == ()

    def test_score_for_and_issues_for_return_matched(self) -> None:
        disc = FakeDisclosureProvider()
        disc.add("005930", [_disclosure("005930", "호재")])
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t()], AS_OF)
        # 매칭되는 종목 → 실제 점수/이슈 반환 (early-return 경로)
        assert result.score_for("005930") > 0.0
        assert len(result.issues_for("005930")) == 1

    def test_lookup_skips_non_matching_items(self) -> None:
        # 여러 종목 결과에서 두 번째 종목 조회 → 첫 항목 불일치 후 매칭 경로
        disc = FakeDisclosureProvider()
        disc.add("000001", [_disclosure("000001", "호재")])
        disc.add("000002", [_disclosure("000002", "호재")])
        clf = FakeSentimentClassifier(default=_positive())
        uc = AnalyzeIssuesUseCase(disclosure_provider=disc, classifier=clf)

        result = uc.execute([_t("000001"), _t("000002")], AS_OF, max_workers=1)
        assert result.score_for("000002") > 0.0
        assert len(result.issues_for("000002")) == 1
