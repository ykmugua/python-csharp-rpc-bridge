import hashlib
from pathlib import Path

import pytest

from python_csharp_rpc_bridge.build_tools.errors import ScanError
from python_csharp_rpc_bridge.build_tools.meta_gen import write_meta
from python_csharp_rpc_bridge.build_tools.scanner import scan_module


def test_scan_fixture_module_records_supported_api():
    business = Path("tests/fixtures/business.py")
    scanned = scan_module(business)

    assert [function["name"] for function in scanned["functions"]] == ["add", "summarize"]
    assert scanned["classes"][0]["name"] == "TextProcessor"
    normalized_source = business.read_text(encoding="utf-8").encode("utf-8")
    assert scanned["source_hash"] == hashlib.sha256(normalized_source).hexdigest()


@pytest.mark.parametrize(
    "source, message",
    [
        ("value = []\n", "module-level"),
        ("def run(*args: int) -> int:\n    return 0\n", "not supported"),
        ("async def run() -> None:\n    pass\n", "async"),
        ("def run(value: tuple) -> int:\n    return 0\n", "unsupported annotation"),
        (
            "class Worker:\n    def close(self) -> None:\n        pass\n",
            "close",
        ),
        ("def run() -> int:\n    global value\n    return 0\n", "global"),
        (
            "def run() -> int:\n    async def helper() -> int:\n        return 0\n    return 0\n",
            "nested async",
        ),
    ],
)
def test_scan_rejects_unsupported_constructs(tmp_path, source, message):
    business = tmp_path / "business.py"
    business.write_text(source, encoding="utf-8")

    with pytest.raises(ScanError, match=message):
        scan_module(business)


@pytest.mark.parametrize(
    "annotation",
    [
        "list[int]",
        "list[float]",
        "list[str]",
        "list[bool]",
        "list[dict]",
        "list[dict[str, int]]",
        "dict[str, list[float]]",
    ],
)
def test_scan_accepts_typed_array_annotations(tmp_path, annotation):
    business = tmp_path / "arrays.py"
    business.write_text(
        f"def echo(values: {annotation}) -> {annotation}:\n"
        "    return values\n",
        encoding="utf-8",
    )

    scanned = scan_module(business)

    assert scanned["functions"][0]["params"][0]["annotation"] == annotation
    assert scanned["functions"][0]["return_annotation"] == annotation


def test_scan_collects_writable_instance_fields(tmp_path):
    business = tmp_path / "members.py"
    business.write_text(
        "class Counter:\n"
        "    def __init__(self) -> None:\n"
        "        self.value: int = 0\n"
        "        self.limit: int = 10\n",
        encoding="utf-8",
    )

    fields = scan_module(business)["classes"][0]["fields"]

    assert fields == [
        {"name": "value", "annotation": "int", "writable": True},
        {"name": "limit", "annotation": "int", "writable": True},
    ]


@pytest.mark.parametrize(
    "annotation",
    ["list[tuple]", "list[None]", "dict[int, str]", "list[list[int]]"],
)
def test_scan_rejects_unsupported_generic_annotations(tmp_path, annotation):
    business = tmp_path / "arrays.py"
    business.write_text(
        f"def echo(values: {annotation}) -> int:\n"
        "    return 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ScanError, match="unsupported annotation"):
        scan_module(business)


def test_meta_timestamp_is_reproducible_with_source_date_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    scanned = scan_module(Path("tests/fixtures/business.py"))

    first = write_meta("sample", "sample_rpc.exe", scanned, tmp_path / "first")
    second = write_meta("sample", "sample_rpc.exe", scanned, tmp_path / "second")

    assert first["built_at"] == "1970-01-01T00:00:00+00:00"
    assert (tmp_path / "first" / "meta.json").read_bytes() == (
        tmp_path / "second" / "meta.json"
    ).read_bytes()
