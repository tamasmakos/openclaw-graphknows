"""Write-ahead log — append-only JSONL audit trail for all writes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class WAL:
    def __init__(self, artifact_dir: Path):
        self._path = artifact_dir / "wal.jsonl"

    def log(self, operation: str, payload: dict) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": operation,
            **payload,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tail(self, n: int = 20) -> list[dict]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines[-n:]]
