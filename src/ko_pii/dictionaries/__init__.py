"""사전 (Dictionaries) — 한국 공공 부문 도메인 특화 어휘 자원.

데이터 출처는 각 모듈의 docstring 참고. 모두 공개데이터 / 공식 자료에서 추출.
"""
from ko_pii.dictionaries.surnames import KOREAN_SURNAMES, is_surname
from ko_pii.dictionaries.titles import (
    TITLES, TITLES_GOV, ALL_GOV_TITLES,
    TITLES_POLICE, TITLES_FIRE, TITLES_MILITARY,
    TITLES_DIPLOMAT, TITLES_PROSECUTOR, TITLES_JUDGE,
    is_title, is_gov_title, title_domain,
)
from ko_pii.dictionaries.agencies import (
    AGENCIES, MINISTRIES, SERVICES, AGENCIES_CHEONG,
    COMMISSIONS, JUDICIAL, LOCAL_GOV, PUBLIC_CORPS,
    is_agency, is_ministry, is_cheong, is_commission, is_local_gov,
)
from ko_pii.dictionaries.agency_abbrev import (
    KOR_ABBREV_TO_FULL, ENG_ABBREV_TO_KOR,
    DOC_ID_PREFIXES, normalize_agency, is_doc_id_prefix,
)
from ko_pii.dictionaries.districts import (
    PROVINCES, PROVINCE_ABBREV,
    SEOUL_DISTRICTS, METRO_DISTRICTS, ALL_CITIES_GUNS, ALL_DISTRICTS,
    PROVINCE_DISTRICTS,
    COUNTRIES, EXTRA_CITY_ABBREV, COMMON_DONGS,
    is_province, is_district, is_admin_unit, normalize_province,
    is_valid_province_district, districts_of,
    is_country, is_common_dong, is_extra_city,
)
from ko_pii.dictionaries.agency_titles import (
    valid_titles_for, is_valid_agency_title, specialized_agencies_for,
)
from ko_pii.dictionaries.field_labels import FIELD_LABELS, is_field_label
from ko_pii.dictionaries.common_words import COMMON_WORDS, is_common_word

__all__ = [
    # surnames
    "KOREAN_SURNAMES", "is_surname",
    # titles
    "TITLES", "TITLES_GOV", "ALL_GOV_TITLES",
    "TITLES_POLICE", "TITLES_FIRE", "TITLES_MILITARY",
    "TITLES_DIPLOMAT", "TITLES_PROSECUTOR", "TITLES_JUDGE",
    "is_title", "is_gov_title", "title_domain",
    # agencies
    "AGENCIES", "MINISTRIES", "SERVICES", "AGENCIES_CHEONG",
    "COMMISSIONS", "JUDICIAL", "LOCAL_GOV", "PUBLIC_CORPS",
    "is_agency", "is_ministry", "is_cheong", "is_commission", "is_local_gov",
    # abbreviations
    "KOR_ABBREV_TO_FULL", "ENG_ABBREV_TO_KOR",
    "DOC_ID_PREFIXES", "normalize_agency", "is_doc_id_prefix",
    # districts (조합 사전 포함)
    "PROVINCES", "PROVINCE_ABBREV", "PROVINCE_DISTRICTS",
    "SEOUL_DISTRICTS", "METRO_DISTRICTS", "ALL_CITIES_GUNS", "ALL_DISTRICTS",
    "is_province", "is_district", "is_admin_unit", "normalize_province",
    "is_valid_province_district", "districts_of",
    # 부처×직급 조합
    "valid_titles_for", "is_valid_agency_title", "specialized_agencies_for",
    # other
    "FIELD_LABELS", "is_field_label",
    "COMMON_WORDS", "is_common_word",
]
