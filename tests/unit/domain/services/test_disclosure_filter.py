"""공시 노이즈 필터 테스트."""

import pytest

from kor_trading.domain.services.disclosure_filter import is_noise_disclosure


class TestNoise:
    @pytest.mark.parametrize(
        "title",
        [
            "임원ㆍ주요주주특정증권등소유상황보고서",
            "대규모기업집단현황공시[연1회(동일인용)]",
            "기업지배구조보고서공시",
            "최대주주등소유주식변동신고서",
            "주식등의대량보유상황보고서",
            "사외이사의선임ㆍ해임또는중도퇴임에관한신고",
        ],
    )
    def test_noise_titles_filtered(self, title: str) -> None:
        assert is_noise_disclosure(title) is True


class TestMaterial:
    @pytest.mark.parametrize(
        "title",
        [
            "단일판매ㆍ공급계약체결",
            "유상증자결정",
            "전환사채권발행결정",
            "자기주식취득결정",
            "영업(잠정)실적(공정공시)",
            "분기보고서",
            "횡령ㆍ배임혐의발생",
            "최대주주변경",
        ],
    )
    def test_material_titles_pass(self, title: str) -> None:
        assert is_noise_disclosure(title) is False
