"""Maintenance gates are tested without network access or real personal data."""
import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_external_selection_is_order_independent(tmp_path):
    select_rows = load_script("evaluate_external").select_rows
    rows = [{"doc_id": f"synthetic-{n}"} for n in range(30)]
    path = tmp_path / "source.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    selected, count = select_rows(path, 7)
    path.write_text("".join(json.dumps(row) + "\n" for row in reversed(rows)), encoding="utf-8")
    assert select_rows(path, 7) == (selected, count)
    assert count == 30
    path.write_text(json.dumps(rows[0]) + "\n" + json.dumps(rows[0]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        select_rows(path, 1)


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_release_uses_same_checks_and_tested_artifact():
    ci, release, checks = [workflow(name) for name in ("ci.yml", "release.yml", "checks.yml")]
    assert ci["jobs"]["validate"]["uses"] == release["jobs"]["validate"]["uses"]
    assert release["jobs"]["validate"]["uses"] == "./.github/workflows/checks.yml"
    assert "workflow_call" in checks["on"]
    assert release["permissions"] == checks["permissions"] == {"contents": "read"}
    publish = release["jobs"]["publish"]
    assert publish["needs"] == "validate"
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    steps = publish["steps"]
    download = next(step for step in steps if step.get("uses", "").startswith("actions/download-artifact@"))
    upload = next(step for step in checks["jobs"]["quality"]["steps"]
                  if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert download["with"]["name"] == upload["with"]["name"]
    assert "distribution-manifest.json" in upload["with"]["path"]
    verification = next(i for i, step in enumerate(steps)
                        if "release_bundle.py verify" in step.get("run", ""))
    publishing = next(i for i, step in enumerate(steps)
                      if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@"))
    assert verification < publishing
    assert not any("python -m build" in step.get("run", "") for step in steps)
    assert steps[publishing]["with"]["packages-dir"] == "tested-bundle/dist/"


def test_readme_example_is_exact():
    source = (ROOT / "examples/quickstart.py").read_text(encoding="utf-8").strip()
    for name in ("README.md", "README.en.md"):
        assert f"```python\n{source}\n```" in (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", [
    "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md",
    "docs/README.md", "docs/COMPATIBILITY.md", "research/README.md",
    "research/EXTERNAL_EVALUATION_20261026.md",
])
def test_maintained_navigation_targets_exist(name):
    path = ROOT / name
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        if "://" not in target and not target.startswith("#"):
            assert (path.parent / unquote(target.split("#")[0])).exists(), (name, target)


@pytest.mark.parametrize("failure", ["oversize", "digest"])
def test_failed_external_download_is_cleaned_up(tmp_path, monkeypatch, failure):
    module = load_script("evaluate_external")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({
        "url": "https://example.invalid/data",
        "source_bytes": 1 if failure == "oversize" else 10,
        "source_sha256": "0" * 64,
    }), encoding="utf-8")
    monkeypatch.setattr(module, "PROTOCOL", protocol)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"test"))
    cache = tmp_path / "cache"
    monkeypatch.setattr(sys, "argv", [
        "evaluate_external", "--cache", str(cache), "--output", str(tmp_path / "out.json"),
        "--download",
    ])
    with pytest.raises(ValueError):
        module.main()
    assert list(cache.iterdir()) == []
    assert not (tmp_path / "out.json").exists()


def test_research_corpus_is_rejected_in_source_archive():
    check = load_script("check_distributions").check_source
    names = [
        "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md",
        "examples/quickstart.py", "examples/policy.json", "examples/input.txt",
        "examples/request.json", "scripts/check_examples.py", "scripts/release_bundle.py",
        ".github/workflows/checks.yml", "tests/contracts/fixtures/1.22.0.json",
    ]
    names = ["ko_pii-1.22.1/" + name for name in names]
    check(names)
    with pytest.raises(ValueError, match="historical research"):
        check(names + ["ko_pii-1.22.1/data/kdpii/test.json"])
    with pytest.raises(ValueError, match="missing"):
        check(names[:-1])
