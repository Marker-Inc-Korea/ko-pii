"""Probe AI Hub dataset page to see what's accessible without login."""
from __future__ import annotations

import re
import ssl
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://aihub.or.kr/",
}
CTX = ssl.create_default_context()


def probe(data_set_sn: int) -> None:
    url = (
        "https://aihub.or.kr/aihubdata/data/view.do"
        f"?srchOptnCnd=OPTNCND001&currMenu=115&topMenu=100&searchKeyword=569"
        f"&aihubDataSe=data&dataSetSn={data_set_sn}"
    )
    print(f"--- dataset {data_set_sn} ---")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return

    print(f"  HTTP OK, body len={len(body):,}")

    # Title
    m = re.search(r"<title>([^<]+)</title>", body)
    if m:
        print(f"  Title: {m.group(1).strip()}")

    # H1/H2 headings
    for h in re.findall(r"<h[1-3][^>]*>([^<]+)</h[1-3]>", body):
        h = h.strip()
        if h and 3 < len(h) < 120:
            print(f"  H: {h}")

    # Look for dataset name / description in common containers
    for pat in [
        r"<dt[^>]*>구축내용</dt>\s*<dd[^>]*>([^<]+)</dd>",
        r"<dt[^>]*>활용용도</dt>\s*<dd[^>]*>([^<]+)</dd>",
        r"<dt[^>]*>라이선스</dt>\s*<dd[^>]*>([^<]+)</dd>",
        r'class="[^"]*data_tit[^"]*"[^>]*>([^<]+)<',
        r'class="[^"]*dt_tit[^"]*"[^>]*>([^<]+)<',
    ]:
        for m in re.finditer(pat, body, re.IGNORECASE | re.DOTALL):
            val = re.sub(r"\s+", " ", m.group(1)).strip()
            if val:
                print(f"  meta: {val[:200]}")

    # Look for any sample/download link
    for m in re.finditer(r'href="([^"]*(?:sample|download|file)[^"]*)"', body, re.IGNORECASE):
        href = m.group(1)
        if href.startswith("/") or "aihub" in href:
            print(f"  link: {href[:120]}")


if __name__ == "__main__":
    probe(71844)
    print()
    probe(569)
