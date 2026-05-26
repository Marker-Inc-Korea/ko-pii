from ko_pii.patterns.ip import detect


def _d(text):
    return list(detect(text))


class TestIPv6Positive:
    def test_full_form(self):
        results = _d("서버 2001:db8::1 입니다")
        assert any(r.extra.get("version") == 6 for r in results)

    def test_loopback(self):
        results = _d("로컬: ::1")
        assert any(r.extra.get("version") == 6 for r in results)

    def test_v4_mapped(self):
        results = _d("주소 ::ffff:192.0.2.1")
        # Both v4 octet and v6 may match — we accept at least the v6 form.
        assert any(r.extra.get("version") == 6 for r in results)


class TestIPv6Negative:
    def test_invalid_form_rejected(self):
        results = _d("not an ip: 2001:db8::1::2")
        assert not any(r.extra.get("version") == 6 for r in results)

    def test_hex_run_alone_no_colons(self):
        assert _d("DEADBEEF") == []


class TestIPv4StillWorks:
    def test_existing_ipv4_unchanged(self):
        results = _d("서버 192.168.0.1")
        assert any(r.extra.get("version") == 4 for r in results)
