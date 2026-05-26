from ko_pii.context.particles import strip_trailing_particle, starts_with_particle


def test_strip_subject_particle():
    assert strip_trailing_particle("홍길동이") == ("홍길동", "이")
    assert strip_trailing_particle("홍길동은") == ("홍길동", "은")


def test_strip_object_particle():
    assert strip_trailing_particle("홍길동을") == ("홍길동", "을")


def test_strip_compound_particle():
    assert strip_trailing_particle("홍길동에게") == ("홍길동", "에게")
    assert strip_trailing_particle("홍길동한테서") == ("홍길동", "한테서")


def test_no_particle():
    assert strip_trailing_particle("홍길동") == ("홍길동", None)


def test_starts_with_particle():
    assert starts_with_particle("이는")
    assert not starts_with_particle("홍길동")
