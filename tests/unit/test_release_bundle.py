import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_bundle", ROOT / "scripts/release_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


@pytest.fixture
def release(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in ("ko_pii-1.22.1-py3-none-any.whl", "ko_pii-1.22.1.tar.gz"):
        (dist / name).write_bytes(b"synthetic distribution fixture")
    return tmp_path


def command(action, root, version="1.22.1", commit="a" * 40):
    return [action, "--root", str(root), "--version", version, "--commit", commit]


def test_seal_and_verify(release):
    assert bundle.main(command("seal", release)) == 0
    assert bundle.main(command("verify", release)) == 0
    with pytest.raises(SystemExit):
        bundle.main(command("seal", release))


@pytest.mark.parametrize("change", ["hash", "missing", "extra", "tag", "commit", "manifest"])
def test_reject_changed_bundle(release, change):
    bundle.main(command("seal", release))
    args = command("verify", release)
    target = release / "dist/ko_pii-1.22.1.tar.gz"
    if change == "hash":
        target.write_bytes(b"changed")
    elif change == "missing":
        target.unlink()
    elif change == "extra":
        (release / "dist/extra.whl").write_bytes(b"unexpected")
    elif change == "tag":
        args = command("verify", release, version="1.22.2")
    elif change == "commit":
        args = command("verify", release, commit="b" * 40)
    else:
        (release / "distribution-manifest.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        bundle.main(args)
    assert error.value.code == 1
