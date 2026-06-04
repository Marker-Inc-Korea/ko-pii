# ko-pii 발표 자료

`ko-pii` 구현·사용법·성능을 다루는 12슬라이드 발표 덱.

| 파일 | 내용 |
|---|---|
| `ko-pii-발표.md` | 소스 (Marp 덱 — `marp: true` frontmatter) |
| `ko-pii-발표.pdf` | 렌더된 발표 자료 (12페이지, 16:9) |

## 렌더

표준 [Marp](https://marp.app/) 으로 재생성:

```bash
marp ko-pii-발표.md --pdf --allow-local-files
```

성능 수치(슬라이드 9)는 KDPII 전체 4,891문서를 단일 매처로 재측정한 값
(`ko_pii.eval.model_comparison --mode kdpii --include-presidio`).
