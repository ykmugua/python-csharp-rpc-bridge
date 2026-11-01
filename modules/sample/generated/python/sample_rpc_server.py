"""Generated single-threaded framed-JSON RPC server; do not edit."""
import json
import struct
import sys
import traceback

SOURCE_HASH = "6d872e91de24a625ce417c1b7bd6633612bdd5da2aee8466caa87870ccd69ac9"
MAX_FRAME = 64 * 1024 * 1024
INTERFACE = json.loads(r'''{"functions": ["add", "delete_item", "echo_floats", "echo_strings", "echo_bools", "echo_records"], "classes": {"TextProcessor": ["normalize", "get_calls"]}, "members": {"TextProcessor": {"lang": "str", "verbose": "bool", "calls": "int"}}, "writable_members": {"TextProcessor": ["lang", "verbose", "calls"]}}''')
INSTANCES = {}
_FRAME_OUT = sys.stdout.buffer

sys.stdout = sys.stderr
import sample as BUSINESS


def _read_exact(size):
    chunks = []
    remaining = size
    while remaining:
        chunk = sys.stdin.buffer.read(remaining)
        if not chunk:
            if remaining == size:
                return None
            raise EOFError("truncated RPC frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_frame():
    header = _read_exact(4)
    if header is None:
        return None
    size = struct.unpack("<I", header)[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError(f"invalid RPC frame length: {size}")
    payload = _read_exact(size)
    if payload is None:
        raise EOFError("truncated RPC payload")
    request = json.loads(payload.decode("utf-8"))
    if not isinstance(request, dict):
        raise ValueError("RPC request must be a JSON object")
    return request


def _write_frame(response):
    payload = json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if not 0 < len(payload) <= MAX_FRAME:
        raise ValueError(f"invalid RPC response length: {len(payload)}")
    _FRAME_OUT.write(struct.pack("<I", len(payload)))
    _FRAME_OUT.write(payload)
    _FRAME_OUT.flush()


def _error(request_id, kind, message, trace=""):
    return {
        "id": request_id,
        "error": {"type": kind, "message": message, "trace": trace},
    }


def _handle(request):
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(method, str):
        return _error(request_id, "InvalidRequest", "method must be a string")
    if not isinstance(params, dict):
        return _error(request_id, "InvalidRequest", "params must be a JSON object")

    if method == "__ping":
        return {"id": request_id, "result": {"ok": True, "source_hash": SOURCE_HASH}}
    if method == "__instance":
        class_name = params.get("class_name")
        if class_name not in INTERFACE["classes"]:
            return _error(request_id, "NoSuchClass", str(class_name))
        instance_id = params.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id:
            return _error(request_id, "InvalidRequest", "instance_id must be a non-empty string")
        key = (class_name, instance_id)
        if key in INSTANCES:
            return _error(request_id, "AlreadyInitialized", f"{class_name}:{instance_id}")
        init_params = params.get("init_params", {})
        if not isinstance(init_params, dict):
            return _error(request_id, "InvalidRequest", "init_params must be a JSON object")
        try:
            cls = getattr(BUSINESS, class_name)
            INSTANCES[key] = cls(**init_params)
            return {"id": request_id, "result": None}
        except Exception as exc:
            return _error(request_id, "InitFailed", f"{class_name}{init_params}: {exc}", traceback.format_exc())

    if method == "__dispose_instance":
        class_name = params.get("class_name")
        instance_id = params.get("instance_id")
        if class_name not in INTERFACE["classes"]:
            return _error(request_id, "NoSuchClass", str(class_name))
        if not isinstance(instance_id, str) or not instance_id:
            return _error(request_id, "InvalidRequest", "instance_id must be a non-empty string")
        key = (class_name, instance_id)
        if key not in INSTANCES:
            return _error(request_id, "NoSuchInstance", f"{class_name}:{instance_id}")
        del INSTANCES[key]
        return {"id": request_id, "result": None}

    if method in {"__get_member", "__set_member"}:
        class_name = params.get("class_name")
        member_name = params.get("member_name")
        if not isinstance(class_name, str):
            return _error(request_id, "InvalidRequest", "class_name must be a string")
        if not isinstance(member_name, str):
            return _error(request_id, "InvalidRequest", "member_name must be a string")
        if class_name not in INTERFACE["members"]:
            return _error(request_id, "NoSuchClass", str(class_name))
        if member_name not in INTERFACE["members"][class_name]:
            return _error(request_id, "NoSuchMember", str(member_name))
        if method == "__set_member" and member_name not in INTERFACE["writable_members"].get(class_name, []):
            return _error(request_id, "ReadOnlyMember", f"{class_name}.{member_name}")
        instance_id = request.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id:
            return _error(request_id, "InvalidRequest", "instance_id must be a non-empty string")
        instance = INSTANCES.get((class_name, instance_id))
        if instance is None:
            return _error(request_id, "NotInitialized", f"{class_name}:{instance_id}")
        try:
            if method == "__get_member":
                return {"id": request_id, "result": getattr(instance, member_name)}
            if "value" not in params:
                return _error(request_id, "InvalidRequest", "value is required")
            setattr(instance, member_name, params["value"])
            return {"id": request_id, "result": None}
        except Exception as exc:
            return _error(request_id, type(exc).__name__, str(exc), traceback.format_exc())

    try:
        if method in INTERFACE["functions"]:
            result = getattr(BUSINESS, method)(**params)
        elif "." in method:
            class_name, member = method.split(".", 1)
            if member not in INTERFACE["classes"].get(class_name, []):
                return _error(request_id, "NoSuchMethod", method)
            instance_id = request.get("instance_id")
            if not isinstance(instance_id, str) or not instance_id:
                return _error(request_id, "InvalidRequest", "instance_id must be a non-empty string")
            instance = INSTANCES.get((class_name, instance_id))
            if instance is None:
                return _error(request_id, "NotInitialized", f"{class_name}:{instance_id}")
            result = getattr(instance, member)(**params)
        else:
            return _error(request_id, "NoSuchMethod", method)
        return {"id": request_id, "result": result}
    except Exception as exc:
        return _error(request_id, type(exc).__name__, str(exc), traceback.format_exc())


def main():
    while True:
        try:
            request = _read_frame()
            if request is None:
                return
            response = _handle(request)
            try:
                _write_frame(response)
            except (TypeError, ValueError) as exc:
                _write_frame(_error(request.get("id"), "SerializationError", str(exc)[:2048]))
        except (EOFError, BrokenPipeError):
            return
        except Exception as exc:
            try:
                _write_frame(_error(None, type(exc).__name__, str(exc), traceback.format_exc()))
            except (BrokenPipeError, OSError):
                return


if __name__ == "__main__":
    main()
