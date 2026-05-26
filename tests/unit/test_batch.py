import os

from ko_pii.batch import collect_files, process_paths
from ko_pii.core.modes import ProcessingMode


class TestCollectFiles:
    def test_single_file(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("hello", encoding="utf-8")
        assert collect_files([str(p)]) == [str(p)]

    def test_directory_recursive(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.csv").write_text("h\nv", encoding="utf-8")
        (tmp_path / "sub" / "c.txt").write_text("c", encoding="utf-8")
        files = collect_files([str(tmp_path)], recursive=True)
        names = sorted(os.path.basename(f) for f in files)
        assert "a.txt" in names
        assert "b.csv" in names
        assert "c.txt" in names

    def test_extension_filter(self, tmp_path):
        (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
        (tmp_path / "skip.bin").write_text("y", encoding="utf-8")
        files = collect_files([str(tmp_path)])
        assert any(f.endswith("ok.txt") for f in files)
        assert not any(f.endswith("skip.bin") for f in files)


class TestProcessPaths:
    def test_basic_batch(self, tmp_path):
        in_dir = tmp_path / "in"
        in_dir.mkdir()
        (in_dir / "doc1.txt").write_text("신청인 880101-1234568", encoding="utf-8")
        (in_dir / "doc2.txt").write_text("연락처 010-1234-5678", encoding="utf-8")
        out_dir = tmp_path / "out"

        summary = process_paths(
            inputs=[str(in_dir)],
            output_dir=str(out_dir),
            mode=ProcessingMode.STRICT,
            strategy="tokenize",
            workers=1,
            progress=False,
        )
        assert summary.total_files == 2
        assert summary.succeeded == 2
        assert summary.failed == 0

        out_files = sorted(os.listdir(out_dir))
        assert "doc1.txt" in out_files
        assert "doc2.txt" in out_files

        # 결과에서 원본 PII 가 사라졌는지
        body = (out_dir / "doc1.txt").read_text(encoding="utf-8")
        assert "880101-1234568" not in body

    def test_skip_unreadable(self, tmp_path):
        in_dir = tmp_path / "in"
        in_dir.mkdir()
        # 정상 파일
        (in_dir / "ok.txt").write_text("plain", encoding="utf-8")
        # 손상된 HWPX 흉내 (잘못된 ZIP)
        (in_dir / "broken.hwpx").write_bytes(b"not a zip")
        out_dir = tmp_path / "out"

        summary = process_paths(
            inputs=[str(in_dir)],
            output_dir=str(out_dir),
            workers=1,
            progress=False,
        )
        # 1개 성공, 1개 실패
        assert summary.succeeded == 1
        assert summary.failed == 1
