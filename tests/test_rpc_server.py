import json
import struct
import subprocess
import sys
from pathlib import Path

from python_csharp_rpc_bridge.build_tools.rpc_gen import gen_rpc_server
from python_csharp_rpc_bridge.build_tools.scanner import scan_module


def _send(process, request):
    payload = json.dumps(request).encode("utf-8")
    process.stdin.write(struct.pack("<I", len(payload)) + payload)
    process.stdin.flush()
    header = process.stdout.read(4)
    assert len(header) == 4
    length = struct.unpack("<I", header)[0]
    response = process.stdout.read(length)
    assert len(response) == length
    return json.loads(response)


def test_generated_rpc_server_dispatches_and_isolates_class_instances(tmp_path):
    business = Path("tests/fixtures/business.py")
    server = gen_rpc_server(scan_module(business), business, tmp_path)
    assert server.name == "business_rpc_server.py"
    process = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        ping = _send(process, {"id": 1, "method": "__ping", "params": {}})
        assert ping["result"] == {
            "ok": True,
            "source_hash": scan_module(business)["source_hash"],
        }
        assert _send(process, {"id": 3, "method": "add", "params": {"a": 2, "b": 3}})["result"] == 5
        assert _send(
            process,
            {"id": 7, "method": "summarize", "params": {"values": [1, 2, 3]}},
        )["result"] == {"count": 3, "sum": 6.0, "mean": 2.0}
        assert _send(
            process,
            {
                "id": 2,
                "method": "__instance",
                "params": {
                    "class_name": "TextProcessor",
                    "instance_id": "default",
                    "init_params": {"lang": "zh"},
                },
            },
        )["result"] is None
        for request_id, instance_id, lang, verbose in [
            (9, "first", "fr", True),
            (10, "second", "de", False),
        ]:
            assert _send(
                process,
                {
                    "id": request_id,
                    "method": "__instance",
                    "params": {
                        "class_name": "TextProcessor",
                        "instance_id": instance_id,
                        "init_params": {"lang": lang, "verbose": verbose},
                    },
                },
            )["result"] is None
        assert _send(
            process,
            {
                "id": 4,
                "method": "TextProcessor.normalize",
                "instance_id": "default",
                "params": {"text": "  hello   world "},
            },
        )["result"] == "hello world"
        assert _send(
            process,
            {
                "id": 5,
                "method": "TextProcessor.get_calls",
                "instance_id": "default",
                "params": {},
            },
        )["result"] == 1
        assert _send(
            process,
            {
                "id": 11,
                "method": "TextProcessor.normalize",
                "instance_id": "first",
                "params": {"text": " first  instance "},
            },
        )["result"] == "[fr] first instance"
        assert _send(
            process,
            {
                "id": 12,
                "method": "TextProcessor.get_calls",
                "instance_id": "first",
                "params": {},
            },
        )["result"] == 1
        assert _send(
            process,
            {
                "id": 13,
                "method": "TextProcessor.get_calls",
                "instance_id": "second",
                "params": {},
            },
        )["result"] == 0
        assert _send(
            process,
            {
                "id": 14,
                "method": "__dispose_instance",
                "params": {"class_name": "TextProcessor", "instance_id": "first"},
            },
        )["result"] is None
        missing_instance = _send(
            process,
            {
                "id": 15,
                "method": "TextProcessor.get_calls",
                "instance_id": "first",
                "params": {},
            },
        )
        assert missing_instance["error"]["type"] == "NotInitialized"
        failure = _send(process, {"id": 6, "method": "missing", "params": {}})
        assert failure["error"]["type"] == "NoSuchMethod"
        invalid = _send(process, {"id": 8, "method": "add", "params": []})
        assert invalid["error"]["type"] == "InvalidRequest"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_generated_rpc_server_loads_local_import_dependencies(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    package_dir = source_dir / "package"
    package_dir.mkdir()
    business = source_dir / "business.py"
    business.write_text(
        "from package.helper import helper\n\n"
        "def run(value: int) -> int:\n"
        "    return helper(value)\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "helper.py").write_text(
        "from .more import increment\n\n"
        "def helper(value):\n"
        "    return increment(value)\n",
        encoding="utf-8",
    )
    (package_dir / "more.py").write_text(
        "def increment(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    server = gen_rpc_server(scan_module(business), business, tmp_path / "backend")
    process = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _send(process, {"id": 1, "method": "run", "params": {"value": 41}})["result"] == 42
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_sample_delete_function_calls_imported_helper_over_rpc(tmp_path):
    business = Path("modules/sample.py")
    server = gen_rpc_server(scan_module(business), business, tmp_path / "backend")
    process = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        response = _send(
            process,
            {
                "id": 1,
                "method": "delete_item",
                "params": {"values": [10, 20, 30], "index": 1},
            },
        )
        assert response["result"] == [10, 30]
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_generated_rpc_server_round_trips_supported_typed_collections(tmp_path):
    business = tmp_path / "typed_collections.py"
    business.write_text(
        "def echo_ints(values: list[int]) -> list[int]:\n"
        "    return values\n\n"
        "def echo_floats(values: list[float]) -> list[float]:\n"
        "    return values\n\n"
        "def echo_strings(values: list[str]) -> list[str]:\n"
        "    return values\n\n"
        "def echo_bools(values: list[bool]) -> list[bool]:\n"
        "    return values\n\n"
        "def echo_records(values: list[dict[str, int]]) -> list[dict[str, int]]:\n"
        "    return values\n",
        encoding="utf-8",
    )
    server = gen_rpc_server(scan_module(business), business, tmp_path / "backend")
    process = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cases = [
        ("echo_ints", [1, -2, 3], [1, -2, 3]),
        ("echo_floats", [1.25, -2.5, 3.0], [1.25, -2.5, 3.0]),
        ("echo_strings", ["hello", "你好", ""], ["hello", "你好", ""]),
        ("echo_bools", [True, False, True], [True, False, True]),
        (
            "echo_records",
            [{"id": 1, "score": 99}, {"id": 2, "score": -1}],
            [{"id": 1, "score": 99}, {"id": 2, "score": -1}],
        ),
    ]
    try:
        for request_id, (method, values, expected) in enumerate(cases, start=1):
            response = _send(
                process,
                {"id": request_id, "method": method, "params": {"values": values}},
            )
            assert response["result"] == expected
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_generated_rpc_server_reads_and_writes_typed_instance_fields(tmp_path):
    business = tmp_path / "member_case.py"
    business.write_text(
        "class Counter:\n"
        "    def __init__(self, initial: int = 0) -> None:\n"
        "        self.value: int = initial\n"
        "        self.limit: int = 10\n",
        encoding="utf-8",
    )
    server = gen_rpc_server(scan_module(business), business, tmp_path / "backend")
    process = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _send(
            process,
            {
                "id": 1,
                "method": "__instance",
                "params": {
                    "class_name": "Counter",
                    "instance_id": "counter-1",
                    "init_params": {"initial": 4},
                },
            },
        )["result"] is None
        read_value = {
            "method": "__get_member",
            "instance_id": "counter-1",
            "params": {"class_name": "Counter", "member_name": "value"},
        }
        assert _send(process, {"id": 2, **read_value})["result"] == 4
        assert _send(
            process,
            {
                "id": 3,
                "method": "__set_member",
                "instance_id": "counter-1",
                "params": {"class_name": "Counter", "member_name": "limit", "value": 20},
            },
        )["result"] is None
        assert _send(
            process,
            {
                "id": 4,
                "method": "__get_member",
                "instance_id": "counter-1",
                "params": {"class_name": "Counter", "member_name": "limit"},
            },
        )["result"] == 20
        assert _send(
            process,
            {
                "id": 5,
                "method": "__set_member",
                "instance_id": "counter-1",
                "params": {"class_name": "Counter", "member_name": "value", "value": 9},
            },
        )["result"] is None
        assert _send(
            process,
            {
                "id": 6,
                "method": "__get_member",
                "instance_id": "counter-1",
                "params": {"class_name": "Counter", "member_name": "value"},
            },
        )["result"] == 9
        unknown = _send(
            process,
            {
                "id": 7,
                "method": "__get_member",
                "instance_id": "counter-1",
                "params": {"class_name": "Counter", "member_name": "__dict__"},
            },
        )
        assert unknown["error"]["type"] == "NoSuchMember"
    finally:
        process.terminate()
        process.wait(timeout=5)
