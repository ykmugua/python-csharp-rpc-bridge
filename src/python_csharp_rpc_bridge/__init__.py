from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    from .build_tools.build import main as build_main

    return build_main(argv)

__all__ = ["main"]
