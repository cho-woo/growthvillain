"""Read committed crawler rows without modifying interrupted source files."""
from __future__ import annotations
import json
from pathlib import Path


def read_completed_jsonl(path, *, max_bytes=20 * 1024 * 1024, max_rows=5000):
    """Read newline-committed strict JSON objects; ignore only a final fragment.

    Semantic/media/path validation remains the caller's normalize_row job.
    The original file and media are never changed by this reader.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("완료된 광고 원본 파일이 없거나 크기 한도를 초과했습니다.")
    rows, total, ignored = [], 0, 0
    with path.open("rb") as stream:
        for line_index, raw in enumerate(stream):
            total += len(raw)
            if total > max_bytes:
                raise ValueError("광고 원본 파일의 크기 한도를 초과했습니다.")
            if not raw.endswith(b"\n"):
                ignored = len(raw)
                break
            if not raw.strip():
                continue
            if len(rows) >= max_rows:
                raise ValueError("완료 광고 행의 개수 한도를 초과했습니다.")
            try:
                value = json.loads(raw.decode("utf-8-sig" if line_index == 0 else "utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise ValueError("완결된 광고 행의 문자 또는 JSON 형식이 올바르지 않습니다.") from None
            if not isinstance(value, dict):
                raise ValueError("완료 광고 행은 객체여야 합니다.")
            rows.append(value)
    return {"rows": rows, "ignoredTrailingBytes": ignored}
