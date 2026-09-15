from __future__ import annotations

import json
import hashlib
from pathlib import Path



def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def write_json_artifact(root: Path, name: str, value: object) -> str:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    expected = canonical_json_bytes(value)
    path.write_bytes(expected)
    saved = path.read_bytes()
    if saved != expected:
        raise RuntimeError("artifact bytes changed after write")
    return hashlib.sha256(saved).hexdigest()
