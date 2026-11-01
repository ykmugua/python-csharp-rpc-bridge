from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from .cs_gen import gen_csharp
from .meta_gen import write_meta
from .rpc_gen import gen_rpc_server
from .scanner import scan_module

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE_ROOT = ROOT / "modules" / "sample"
DEFAULT_BUSINESS = ROOT / "modules" / "sample.py"
CSHARP_GENERATED = DEFAULT_SAMPLE_ROOT / "generated" / "csharp"
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_module(
    module: str,
    business: Path,
    out_dir: Path,
    csharp_generated_dir: Path,
    *,
    nuitka: bool = False,
    nuitka_zig: bool = False,
) -> None:
    if not MODULE_RE.fullmatch(module):
        raise ValueError(f"Not a valid Python module name: {module}")
    if not business.is_file():
        raise FileNotFoundError(f"Missing business module: {business}")

    scanned = scan_module(business)
    exe_name = f"{module}_rpc.exe"
    meta = write_meta(module, exe_name, scanned, out_dir)
    rpc_server = gen_rpc_server(scanned, business, out_dir)
    gen_csharp(meta, csharp_generated_dir)
    print(f"[ok] {module}: generated metadata, RPC server, and C# facade")

    if nuitka:
        command = [
            sys.executable,
            "-m",
            "nuitka",
            "--onefile",
            "--assume-yes-for-downloads",
            f"--output-dir={out_dir.resolve()}",
            f"--output-filename={exe_name}",
            str(rpc_server.resolve()),
        ]
        if nuitka_zig:
            command.insert(4, "--zig")
        print("run:", " ".join(command))
        subprocess.run(command, cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate RPC backends and C# facades.")
    parser.add_argument("module", nargs="?", help="Module name (defaults to the source file name).")
    parser.add_argument("--nuitka", action="store_true", help="Package the selected backend as a one-file executable.")
    parser.add_argument(
        "--nuitka-zig",
        action="store_true",
        help="Use Nuitka's Zig compiler backend (requires --nuitka).",
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Build a standalone module from a Python source file.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Write standalone generated files under this directory.",
    )
    args = parser.parse_args(argv)

    if args.nuitka_zig and not args.nuitka:
        parser.error("--nuitka-zig requires --nuitka.")

    if args.source_file is not None or args.output_root is not None:
        if args.source_file is None or args.output_root is None:
            parser.error("--source-file and --output-root must be used together.")
        if args.module is not None:
            parser.error("Standalone source builds cannot be combined with a positional module name.")
        source_file = args.source_file.resolve()
        module = source_file.stem
        if not MODULE_RE.fullmatch(module):
            parser.error(f"Source file name is not a valid Python module name: {module}")
        output_root = args.output_root.resolve()
        build_module(
            module,
            source_file,
            output_root / "generated" / "python",
            output_root / "generated" / "csharp",
            nuitka=args.nuitka,
            nuitka_zig=args.nuitka_zig,
        )
        return 0

    business = DEFAULT_BUSINESS
    out_dir = DEFAULT_SAMPLE_ROOT / "generated" / "python"
    build_module(
        args.module or business.stem,
        business,
        out_dir,
        CSHARP_GENERATED,
        nuitka=args.nuitka,
        nuitka_zig=args.nuitka_zig,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
