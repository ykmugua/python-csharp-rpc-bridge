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
