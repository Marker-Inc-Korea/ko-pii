"""Internal subprocess entry point; errors never include document contents."""
from __future__ import annotations

from dataclasses import asdict
import json
import sys

from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy, read_text_bounded


def main() -> int:
    try:
        if sys.platform.startswith("linux"):
            import resource
            limit = 512 * 1024 * 1024
            _, hard = resource.getrlimit(resource.RLIMIT_AS)
            if hard != resource.RLIM_INFINITY:
                limit = min(limit, hard)
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        policy = FileReadPolicy(**json.loads(sys.stdin.read(16_384)))
        result = read_text_bounded(sys.argv[1], policy=policy)
        print(json.dumps(asdict(result), ensure_ascii=False))
        return 0
    except BoundedReadError as exc:
        print(json.dumps({"code": exc.code, "message": str(exc), "coverage": exc.coverage}))
    except Exception:
        print(json.dumps({"code": "extract_worker_failed", "message": "document extraction worker failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
