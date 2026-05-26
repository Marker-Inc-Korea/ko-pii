from ko_pii.modes.hashed import hashed
from ko_pii.patterns.rrn import detect as detect_rrn
from ko_pii.vault.reversible import ReversibleVault


class TestHashedMode:
    def test_replaces_with_label_and_hash(self):
        text = "A 880101-1234568"
        out, v = hashed(text, detect_rrn(text), vault=ReversibleVault(salt="s"))
        assert "880101" not in out
        assert "<RRN:" in out and ">" in out

    def test_same_value_same_hash(self):
        text = "A 880101-1234568 B 880101-1234568"
        out, _ = hashed(text, detect_rrn(text), vault=ReversibleVault(salt="s"))
        toks = [t for t in out.split() if t.startswith("<RRN:")]
        assert len(toks) == 2
        assert toks[0] == toks[1]

    def test_different_salt_different_hash(self):
        text = "A 880101-1234568"
        a, _ = hashed(text, detect_rrn(text), vault=ReversibleVault(salt="x"))
        b, _ = hashed(text, detect_rrn(text), vault=ReversibleVault(salt="y"))
        assert a != b

    def test_digest_length_respected(self):
        text = "A 880101-1234568"
        out, _ = hashed(
            text, detect_rrn(text), vault=ReversibleVault(salt="s"), digest_len=8
        )
        # Tag format: <RRN:xxxxxxxx>
        import re
        m = re.search(r"<RRN:([0-9a-f]+)>", out)
        assert m is not None
        assert len(m.group(1)) == 8
