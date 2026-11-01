from __future__ import annotations

import json
import keyword
from pathlib import Path

TEMPLATE = (Path(__file__).parent / "templates" / "rpc_server.py.j2").read_text(encoding="utf-8")


def gen_rpc_server(scanned: dict, business_py: Path, out_dir: Path) -> Path:
    module = business_py.stem
    if not module.isidentifier() or keyword.iskeyword(module):
        raise ValueError(f"Not a valid Python module name: {module}")

    interface = {
        "functions": [f["name"] for f in scanned["functions"]],
        "classes": {c["name"]: [m["name"] for m in c["methods"]] for c in scanned["classes"]},
    }
    substitutions = {
        "__SOURCE_HASH__": scanned["source_hash"],
        "__INTERFACE_JSON__": json.dumps(interface, ensure_ascii=False),
        "__BUSINESS_MODULE__": module,
    }
    generated = TEMPLATE
    for placeholder, value in substitutions.items():
        generated = generated.replace(placeholder, value)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{module}.py").write_text(
        business_py.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    out = out_dir / f"{module}_rpc_server.py"
    out.write_text(generated, encoding="utf-8", newline="\n")
    return out
