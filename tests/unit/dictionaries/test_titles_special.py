"""특정직 (경찰/소방/군/외무/검사/판사) 직급 사전 검증."""
from ko_pii.dictionaries.titles import (
    TITLES_POLICE, TITLES_FIRE, TITLES_MILITARY,
    TITLES_DIPLOMAT, TITLES_PROSECUTOR, TITLES_JUDGE,
    is_title, is_gov_title, title_domain,
)


class TestPoliceRanks:
    def test_11_ranks_present(self):
        # 경찰공무원법 제3조 — 11계급
        for rank in ("치안총감", "치안정감", "치안감", "경무관", "총경",
                     "경정", "경감", "경위", "경사", "경장", "순경"):
            assert rank in TITLES_POLICE


class TestFireRanks:
    def test_11_ranks_present(self):
        # 소방공무원법 제3조 — 11계급
        for rank in ("소방총감", "소방정감", "소방감", "소방준감", "소방정",
                     "소방령", "소방경", "소방위", "소방장", "소방교", "소방사"):
            assert rank in TITLES_FIRE


class TestMilitaryRanks:
    def test_officer_ranks(self):
        for rank in ("원수", "대장", "중장", "소장", "준장",
                     "대령", "중령", "소령",
                     "대위", "중위", "소위"):
            assert rank in TITLES_MILITARY

    def test_enlisted_ranks(self):
        for rank in ("원사", "상사", "중사", "하사",
                     "병장", "상병", "일병", "이병"):
            assert rank in TITLES_MILITARY


class TestDiplomatRanks:
    def test_known_titles(self):
        for t in ("대사", "총영사", "영사", "참사관",
                  "1등서기관", "2등서기관", "3등서기관"):
            assert t in TITLES_DIPLOMAT


class TestProsecutorRanks:
    def test_known_titles(self):
        for t in ("검찰총장", "고검장", "지검장", "차장검사",
                  "부장검사", "부부장검사", "평검사", "검사"):
            assert t in TITLES_PROSECUTOR


class TestJudgeRanks:
    def test_known_titles(self):
        for t in ("대법원장", "대법관", "헌법재판소장", "헌법재판관",
                  "고등법원장", "지방법원장", "부장판사", "판사"):
            assert t in TITLES_JUDGE


class TestTitleDomain:
    def test_classification(self):
        assert title_domain("치안총감") == "police"
        assert title_domain("소방준감") == "fire"
        assert title_domain("대령") == "military"
        assert title_domain("총영사") == "diplomat"
        assert title_domain("검찰총장") == "prosecutor"
        assert title_domain("대법관") == "judge"
        assert title_domain("사무관") == "gov"
        assert title_domain("교수") == "general"
        assert title_domain("아무직책") is None

    def test_is_title_covers_all(self):
        for t in ("치안총감", "소방준감", "대령", "총영사",
                  "검찰총장", "대법관", "사무관", "교수"):
            assert is_title(t)

    def test_is_gov_title(self):
        assert is_gov_title("치안총감")
        assert is_gov_title("사무관")
        assert is_gov_title("대법관")
        assert not is_gov_title("교수")  # 일반 직책


class TestAgencyExpansion:
    def test_agencies_dict_expanded(self):
        from ko_pii.dictionaries.agencies import AGENCIES
        # 신설 청들
        for new_agency in ("우주항공청", "재외동포청", "질병관리청",
                          "국가유산청"):
            assert new_agency in AGENCIES
        # 최소 사이즈
        assert len(AGENCIES) >= 100
