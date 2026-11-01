from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _built_at() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is not None:
        try:
            return datetime.fromtimestamp(int(source_date_epoch), timezone.utc).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("SOURCE_DATE_EPOCH must be a valid Unix timestamp") from exc
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_meta(module: str, exe_name: str, scanned: dict, out_dir: Path) -> dict:
    meta = {
        "module": module,
        "exe_name": exe_name,
        "source_hash": scanned["source_hash"],
        "built_at": _built_at(),
        "functions": [
            {
                "qualname": f["name"],
                "params": [
                    {
                        "name": p["name"],
                        "annotation": p["annotation"],
                        "has_default": p["has_default"],
                        "default": p["default"],
                    }
                    for p in f["params"]
                ],
                "return_annotation": f["return_annotation"],
                "doc": f["doc"],
            }
            for f in scanned["functions"]
        ],
        "classes": [
            {
                "name": c["name"],
                "init_params": [
                    {
                        "name": p["name"],
                        "annotation": p["annotation"],
                        "has_default": p["has_default"],
                        "default": p["default"],
                    }
                    for p in c["init_params"]
                ],
                "fields": [
                    {
                        "name": field["name"],
                        "annotation": field["annotation"],
                        "writable": field["writable"],
                    }
                    for field in c.get("fields", [])
                ],
                "methods": [
                    {
                        "qualname": f"{c['name']}.{m['name']}",
                        "name": m["name"],
                        "params": [
                            {
                                "name": p["name"],
                                "annotation": p["annotation"],
                                "has_default": p["has_default"],
                                "default": p["default"],
                            }
                            for p in m["params"]
                        ],
                        "return_annotation": m["return_annotation"],
                        "doc": m["doc"],
                    }
                    for m in c["methods"]
                ],
            }
            for c in scanned["classes"]
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return meta
