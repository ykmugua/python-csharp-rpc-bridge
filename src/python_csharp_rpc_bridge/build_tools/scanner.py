"""Validate business modules and extract the interface used by the generators."""
from __future__ import annotations

import ast
import hashlib
import keyword
import re
from pathlib import Path
from typing import Any

from .errors import ScanError

ALLOWED = {"int", "float", "str", "bool", "list", "dict", "None"}
BASE_TYPES = {"int", "float", "str", "bool"}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CSHARP_KEYWORDS = {
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch",
    "char", "checked", "class", "const", "continue", "decimal", "default",
    "delegate", "do", "double", "else", "enum", "event", "explicit",
    "extern", "false", "finally", "fixed", "float", "for", "foreach",
    "goto", "if", "implicit", "in", "int", "interface", "internal", "is",
    "lock", "long", "namespace", "new", "null", "object", "operator", "out",
    "override", "params", "private", "protected", "public", "readonly", "ref",
    "return", "sbyte", "sealed", "short", "sizeof", "stackalloc", "static",
    "string", "struct", "switch", "this", "throw", "true", "try", "typeof",
    "uint", "ulong", "unchecked", "unsafe", "ushort", "using", "virtual",
    "void", "volatile", "while",
}


def _ann_to_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and node.value is None:
        return "None"
    return ast.unparse(node)


def _check_name(name: str, where: str) -> None:
    if not NAME_RE.fullmatch(name):
        raise ScanError(f"{where}: name must match {NAME_RE.pattern}")
    if keyword.iskeyword(name):
        raise ScanError(f"{where}: Python keyword {name!r} is not allowed")


def _check_ann(ann: str | None, where: str) -> str:
    if ann is None:
        raise ScanError(f"{where}: missing type annotation")
    if ann in ALLOWED:
        return ann

    try:
        node = ast.parse(ann, mode="eval").body
    except SyntaxError:
        node = None
    if _is_supported_generic(node):
        return ann

    allowed = f"{sorted(ALLOWED)} and list[<supported type>] / dict[str, <supported type>]"
    raise ScanError(f"{where}: unsupported annotation {ann!r}; allowed: {allowed}")


def _is_supported_generic(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Name):
        return node.id in BASE_TYPES | {"dict", "list"}
    if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
        return False
    if node.value.id == "list":
        if isinstance(node.slice, ast.Subscript) and (
            isinstance(node.slice.value, ast.Name) and node.slice.value.id == "list"
        ):
            return False
        return _is_supported_generic(node.slice)
    if node.value.id == "dict" and isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2:
        key, value = node.slice.elts
        return isinstance(key, ast.Name) and key.id == "str" and _is_supported_generic(value)
    return False


def _field_annotation(node: ast.expr) -> str:
    annotation = _check_ann(ast.unparse(node), "instance field")
    if annotation == "None":
        raise ScanError("instance fields cannot use the None annotation")
    return annotation


def _collect_instance_fields(init: ast.FunctionDef, class_name: str) -> list[dict[str, Any]]:
    fields = []
    seen: set[str] = set()
    property_names: set[str] = set()
    for node in ast.walk(init):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            continue
        if node.value is None:
            raise ScanError(f"{class_name}.{target.attr}: instance fields must be initialized")
        _check_name(target.attr, f"{class_name} instance field")
        annotation = _field_annotation(node.annotation)
        property_name = target.attr[0].upper() + target.attr[1:]
        if target.attr in seen or property_name in property_names:
            raise ScanError(f"{class_name}: duplicate or colliding generated field {target.attr!r}")
        if property_name in {"Dispose", class_name}:
            raise ScanError(f"{class_name}.{target.attr}: collides with a generated C# member")
        seen.add(target.attr)
        property_names.add(property_name)
        fields.append({
            "name": target.attr,
            "annotation": annotation,
            "writable": True,
        })
    return fields


def _literal_default(node: ast.expr, where: str) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError) as exc:
        raise ScanError(f"{where}: default must be a literal JSON value") from exc
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ScanError(f"{where}: default must be a scalar literal")
    return value


def _check_func(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    cls: str | None,
    *,
    is_init: bool = False,
) -> dict[str, Any]:
    where = f"{cls + '.' if cls else ''}{fn.name}"
    _check_name(fn.name, where)
    if isinstance(fn, ast.AsyncFunctionDef):
        raise ScanError(f"{where}: async functions are not supported")
    if fn.decorator_list:
        raise ScanError(f"{where}: decorators are not supported")
    if fn.args.posonlyargs:
        raise ScanError(f"{where}: positional-only parameters are not supported")
    if fn.args.vararg or fn.args.kwarg:
        raise ScanError(f"{where}: *args and **kwargs are not supported")
    doc = ast.get_docstring(fn) or ""
    if cls and not is_init and not re.search(r"\b(?:read|write)\b|[读写]", doc, re.IGNORECASE):
        raise ScanError(f"{where}: docstring must identify whether it reads or writes shared state")
    for child in ast.walk(fn):
        if child is not fn and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if isinstance(child, ast.AsyncFunctionDef):
                raise ScanError(f"{where}: nested async functions are not supported")
        if isinstance(child, ast.Import) and any(
            alias.name.split(".", 1)[0] in {"asyncio", "threading", "concurrent", "socket"}
            for alias in child.names
        ):
            raise ScanError(f"{where}: asyncio, threads, and sockets are not supported")
        if isinstance(child, ast.ImportFrom) and child.module and child.module.split(".", 1)[0] in {
            "asyncio", "threading", "concurrent", "socket"
        }:
            raise ScanError(f"{where}: asyncio, threads, and sockets are not supported")
        if isinstance(child, (ast.Global, ast.Nonlocal)):
            raise ScanError(f"{where}: global and nonlocal statements are not supported")
        if isinstance(child, ast.Await):
            raise ScanError(f"{where}: asyncio is not supported")
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id in {"open", "socket", "create_connection", "urlopen", "Thread"}:
                raise ScanError(f"{where}: explicit resource and thread creation is not supported")
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            if child.value.id in {"asyncio", "threading", "concurrent"}:
                raise ScanError(f"{where}: asyncio and thread-based code is not supported")

    args = list(fn.args.args)
    if cls:
        if not args or args[0].arg != "self":
            raise ScanError(f"{where}: instance methods must declare self as the first parameter")
        args = args[1:]
    elif any(a.arg in {"self", "cls"} for a in args):
        raise ScanError(f"{where}: self/cls parameters are only valid on instance methods")

    all_args = args + list(fn.args.kwonlyargs)
    defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
    defaults += list(fn.args.kw_defaults)
    params = []
    for arg, default in zip(all_args, defaults, strict=True):
        _check_name(arg.arg, f"{where}.{arg.arg}")
        ann = _check_ann(_ann_to_str(arg.annotation), f"{where}.{arg.arg}")
        has_default = default is not None
        params.append({
            "name": arg.arg,
            "annotation": ann,
            "has_default": has_default,
            "default": _literal_default(default, f"{where}.{arg.arg}") if has_default else None,
        })

    ret = _ann_to_str(fn.returns)
    if ret is None:
        raise ScanError(f"{where}: missing return annotation")
    if ret != "None":
        _check_ann(ret, f"{where} return value")
    if is_init and ret != "None":
        raise ScanError(f"{where}: __init__ must return None")
    return {
        "name": fn.name,
        "params": params,
        "return_annotation": ret,
        "doc": doc,
    }


def _validate_function_names(functions: list[dict[str, Any]], where: str) -> None:
    seen: set[str] = set()
    for fn in functions:
        generated = fn["name"][0].upper() + fn["name"][1:] + "_pyf"
        if generated in seen:
            raise ScanError(f"{where}: generated C# method name collision: {generated}")
        seen.add(generated)


def scan_module(business_py: Path) -> dict[str, Any]:
    """Parse and validate a module without importing or executing its business code."""
    src = business_py.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(business_py))
    except SyntaxError as exc:
        raise ScanError(f"{business_py}:{exc.lineno}: {exc.msg}") from exc

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] in {"asyncio", "threading", "concurrent", "socket"} for alias in node.names):
                raise ScanError(f"line {node.lineno}: asyncio, threads, and sockets are not supported")
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level:
                raise ScanError(f"line {node.lineno}: relative imports are not supported in a standalone backend")
            if node.module and node.module.split(".", 1)[0] in {"asyncio", "threading", "concurrent", "socket"}:
                raise ScanError(f"line {node.lineno}: asyncio, threads, and sockets are not supported")
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.FunctionDef):
            functions.append(_check_func(node, None))
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            raise ScanError(f"line {node.lineno}: async functions are not supported")
        if isinstance(node, ast.ClassDef):
            _check_name(node.name, f"line {node.lineno} class")
            if node.bases or node.keywords or node.decorator_list:
                raise ScanError(f"{node.name}: inheritance, metaclasses, and decorators are not supported")
            init_params = []
            methods = []
            fields = []
            init_seen = False
            for item in node.body:
                if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                    continue
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    raise ScanError(
                        f"{node.name}: class body may contain only a docstring and instance methods "
                        f"(line {item.lineno})"
                    )
                if item.name == "__init__":
                    if init_seen:
                        raise ScanError(f"{node.name}: duplicate __init__")
                    init_seen = True
                    init_params = _check_func(item, node.name, is_init=True)["params"]
                    fields = _collect_instance_fields(item, node.name)
                    init_names: set[str] = set()
                    for param in init_params:
                        if param["annotation"] not in BASE_TYPES:
                            raise ScanError(
                                f"{node.name}.__init__.{param['name']}: "
                                "constructor parameters must be int/float/str/bool"
                            )
                        property_name = param["name"][0].upper() + param["name"][1:]
                        if property_name in init_names:
                            raise ScanError(
                                f"{node.name}.__init__: generated C# option property collision: "
                                f"{property_name}"
                            )
                        init_names.add(property_name)
                elif item.name in {"__del__", "close"}:
                    raise ScanError(f"{node.name}.{item.name}: resource finalizers/close methods are forbidden")
                elif item.name.startswith("__") and item.name.endswith("__"):
                    raise ScanError(f"{node.name}.{item.name}: dunder methods are not supported")
                else:
                    methods.append(_check_func(item, node.name))

            _validate_function_names(methods, node.name)
            classes.append({
                "name": node.name,
                "init_params": init_params,
                "methods": methods,
                "fields": fields,
            })
            continue
        raise ScanError(
            f"line {getattr(node, 'lineno', '?')}: module-level variables and executable statements are forbidden"
        )

    _validate_function_names(functions, "module")
    reserved = {"__ping", "__instance"}
    for fn in functions:
        if fn["name"] in reserved:
            raise ScanError(f"{fn['name']}: RPC method name is reserved")
    class_names: set[str] = set()
    for cls in classes:
        if cls["name"] in class_names:
            raise ScanError(f"duplicate class name: {cls['name']}")
        class_names.add(cls["name"])
        if cls["name"] in CSHARP_KEYWORDS:
            raise ScanError(f"{cls['name']}: C# keyword class names are not supported")

    return {
        "functions": functions,
        "classes": classes,
        "source_hash": hashlib.sha256(src.encode("utf-8")).hexdigest(),
    }
