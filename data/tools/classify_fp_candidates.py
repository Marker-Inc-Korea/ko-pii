"""Triage cycle 3 fp_collector output: split into 'likely common words' vs
'potential real names' for hand-review.

Heuristic for 'potential person name':
  - 3 characters, Korean only
  - Starts with a high-frequency Korean surname (top ~50)
  - Tail 2 chars look name-like (not common admin suffixes like -자/-부/-과/-소/-청)

Everything else → common_word candidate.

Doesn't decide automatically — just sorts. Final review still by hand.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Top common Korean surnames (covers >85% of population)
COMMON_SURNAMES = set(
    "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 류 전 홍 고 문 양 손 배 백 허 유 남 심 노 하 곽 성 차 주 우 구 민 진 지 엄 채 원 천 방 공 강 변 염 양 변 여 추 노 도 소 신 석 선 설 마 길".split()
)

# Common admin suffixes that, if at the end of a 3-char string starting with surname,
# strongly indicate it's NOT a person (it's e.g. 김해시, 박물관)
ADMIN_SUFFIXES = (
    "시", "도", "구", "군", "동", "면", "리", "읍", "촌",
    "관", "원", "장", "청", "부", "과",
    "사", "법", "안", "안", "비", "주",
    "회", "당", "단", "조", "임", "수",
    "료", "금", "료", "급", "료",
    "물", "비", "료", "선", "용",
)


def is_potential_name(token: str) -> bool:
    if len(token) != 3:
        return False
    if not all(0xAC00 <= ord(c) <= 0xD7A3 for c in token):
        return False
    if token[0] not in COMMON_SURNAMES:
        return False
    # If ends in obvious admin suffix → probably not a person name
    if token[-1] in ADMIN_SUFFIXES:
        return False
    return True


def parse_candidates(path: Path) -> list[tuple[int, str]]:
    """Parse fp_collector output table."""
    entries: list[tuple[int, str]] = []
    line_re = re.compile(r"^\s*(\d+)\s+'([^']+)'\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = line_re.match(line)
        if m:
            entries.append((int(m.group(1)), m.group(2)))
    return entries


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: classify_fp_candidates.py <fp_candidates.txt>")
        return 1
    path = Path(sys.argv[1])
    entries = parse_candidates(path)
    print(f"총 후보: {len(entries)}", file=sys.stderr)

    common_candidates: list[tuple[int, str]] = []
    potential_names: list[tuple[int, str]] = []
    for freq, token in entries:
        if is_potential_name(token):
            potential_names.append((freq, token))
        else:
            common_candidates.append((freq, token))

    print(f"\n=== POTENTIAL NAMES ({len(potential_names)}) — hand-review required ===")
    for freq, token in sorted(potential_names, key=lambda x: -x[0]):
        print(f"  {freq:>6}  {token}")

    print(f"\n=== COMMON-WORD CANDIDATES ({len(common_candidates)}) — bulk-add ===")
    for freq, token in sorted(common_candidates, key=lambda x: -x[0])[:150]:
        print(f"  {freq:>6}  {token}")

    # Also emit as a comma-separated Python list for easy paste
    print("\n=== PYTHON LIST (top 200 common, for common_words.py append) ===")
    bulk = [t for _, t in sorted(common_candidates, key=lambda x: -x[0])[:200]]
    # 8 per line
    for i in range(0, len(bulk), 8):
        chunk = bulk[i : i + 8]
        print('    ' + ', '.join(f'"{t}"' for t in chunk) + ',')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
