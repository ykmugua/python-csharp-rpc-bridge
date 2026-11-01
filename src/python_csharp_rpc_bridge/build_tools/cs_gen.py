from __future__ import annotations

import json
import html
import keyword
from pathlib import Path

BASE_TYPES = {"int", "float", "str", "bool"}
PY2CS = {
    "int": "int",
    "float": "double",
    "str": "string",
    "bool": "bool",
    "list": "JsonArray",
    "dict": "JsonObject",
    "None": "void",
}
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


def _cs_id(name: str) -> str:
    return f"@{name}" if name in CSHARP_KEYWORDS or keyword.iskeyword(name) else name


def _cs_property(name: str) -> str:
    return _cs_id(name[0].upper() + name[1:])


def _cs_method(name: str) -> str:
    return _cs_id(name[0].upper() + name[1:] + "_pyf")


def _all_base(params: list[dict]) -> bool:
    return all(param["annotation"] in BASE_TYPES for param in params)


def _strong_sig(params: list[dict]) -> str:
    return ", ".join(
        f"{PY2CS[param['annotation']]} {_cs_id(param['name'])}" for param in params
    )


def _init_property(class_info: dict) -> str:
    class_name = _cs_id(class_info["name"])
    init_type = f"{class_info['name']}Init"
    return (
        f"            /// <summary>Gets the initialization options for {class_info['name']}.</summary>\n"
        f"            public {init_type} {class_name} {{ get; set; }} = new();"
    )


def _json_args_expr(params: list[dict]) -> str:
    pairs = ", ".join(
        f"[{json.dumps(param['name'])}] = JsonValue.Create({_cs_id(param['name'])})"
        for param in params
    )
    return f"new JsonObject {{ {pairs} }}" if params else "new JsonObject()"


def _ret_cs(annotation: str) -> str:
    return PY2CS[annotation]


def _rpc_string(method: str) -> str:
    return json.dumps(method)


def _xml_summary(doc: str) -> str:
    summary = " ".join(line.strip() for line in doc.strip().splitlines() if line.strip())
    if not summary:
        summary = "Calls the corresponding Python business function."
    return "        /// <summary>\n        /// " + html.escape(summary, quote=False) + "\n        /// </summary>"


def _gen_methods(
    methods: list[dict],
    class_name: str | None,
    runtime_class: str,
    instance_id: str | None = None,
) -> str:
    chunks = []
    for method in methods:
        method_name = method.get("name", method["qualname"])
        cs_name = _cs_method(method_name)
        rpc_name = f"{class_name}.{method_name}" if class_name else method_name
        ret_type = _ret_cs(method["return_annotation"])
        if class_name is None:
            invocation = f"{runtime_class}.Client.Invoke"
            typed_invocation = f"{runtime_class}.Client.Invoke"
            static_modifier = "static "
        else:
            target_id = instance_id or f'{runtime_class}.GetDefaultInstanceId("{class_name}")'
            invocation = f"{runtime_class}.Client.InvokeInstance"
            typed_invocation = f"{runtime_class}.Client.InvokeInstance"
            static_modifier = "" if instance_id else "static "
        invoke_args = _rpc_string(rpc_name)
        if class_name is not None:
            invoke_args += f", {target_id}"
        single_str_param = (
            len(method["params"]) == 1
            and method["params"][0]["annotation"] == "str"
        )
        json_cs_name = f"{cs_name}_json" if single_str_param else cs_name
        if ret_type == "void":
            chunks.append(
                f"{_xml_summary(method['doc'])}\n"
                f"        public {static_modifier}void {json_cs_name}(string jsonArgs) =>\n"
                f"            {invocation}({invoke_args}, jsonArgs);"
            )
        else:
            chunks.append(
                f"{_xml_summary(method['doc'])}\n"
                f"        public {static_modifier}{ret_type} {json_cs_name}(string jsonArgs) =>\n"
                f"            {typed_invocation}<{ret_type}>({invoke_args}, jsonArgs);"
            )
        if _all_base(method["params"]):
            signature = _strong_sig(method["params"])
            args = _json_args_expr(method["params"])
            if ret_type == "void":
                chunks.append(
                    f"{_xml_summary(method['doc'])}\n"
                    f"        public {static_modifier}void {cs_name}({signature}) =>\n"
                    f"            {invocation}({invoke_args}, {args});"
                )
            else:
                chunks.append(
                    f"{_xml_summary(method['doc'])}\n"
                    f"        public {static_modifier}{ret_type} {cs_name}({signature}) =>\n"
                    f"            {typed_invocation}<{ret_type}>({invoke_args}, {args});"
                )
    return "\n\n".join(chunks)


RUNTIME_TEMPLATE = """// <auto-generated/> Do not edit.
#nullable enable
using System;
using System.Text.Json.Nodes;
using ModulePlatform.PyfRpc;

namespace ModulePlatform
{{
    /// <summary>Manages the Python backend for this module.</summary>
    public static class {module}Runtime
    {{
        /// <summary>Gets the source hash used to verify the matching Python backend.</summary>
        public const string SourceHash = {source_hash};

        private static StdioRpcClient? _client;
        private static bool _started;
        private static readonly object SyncRoot = new();

        internal static StdioRpcClient Client =>
            _client ?? throw new InvalidOperationException("Runtime has not been started.");

        internal static string CreateInstance(string className, JsonObject initParams)
        {{
            var instanceId = Guid.NewGuid().ToString("N");
            Client.Invoke("__instance", new JsonObject
            {{
                ["class_name"] = className,
                ["instance_id"] = instanceId,
                ["init_params"] = initParams
            }});
            return instanceId;
        }}

        internal static void DestroyInstance(string className, string instanceId) =>
            Client.Invoke("__dispose_instance", new JsonObject
            {{
                ["class_name"] = className,
                ["instance_id"] = instanceId
            }});

        /// <summary>Starts the Python backend and verifies its interface.</summary>
        public static void Start()
        {{
            lock (SyncRoot)
            {{
                if (_started)
                    throw new InvalidOperationException("Runtime is already started; call Stop or Restart first.");
                StartCore();
            }}
        }}

        private static void StartCore()
        {{
            var client = BackendLocator.CreateClient({exe_name}, {server_script_name});
            _client = client;
            try
            {{
                client.Start();
                var ping = client.InvokeRaw("__ping", null);
                var got = ping?["source_hash"]?.GetValue<string>();
                if (!String.Equals(got, SourceHash, StringComparison.Ordinal))
                    throw new RpcException("SignatureMismatch",
                        $"source_hash mismatch: dll={{SourceHash}} backend={{got}}");
                _started = true;
            }}
            catch (Exception initializationError)
            {{
                _started = false;
                _client = null;
                try
                {{
                    client.Dispose();
                }}
                catch (Exception cleanupError)
                {{
                    throw new AggregateException(
                        "Runtime initialization and backend cleanup both failed.",
                        initializationError, cleanupError);
                }}
                throw;
            }}
        }}

        /// <summary>Restarts the backend. Existing class instances are no longer available afterward.</summary>
        public static void Restart()
        {{
            lock (SyncRoot)
            {{
                if (!_started)
                    throw new InvalidOperationException("Runtime has not been started.");
                StopCore();
                StartCore();
            }}
        }}

        /// <summary>Stops the Python backend process.</summary>
        public static void Stop()
        {{
            lock (SyncRoot)
                StopCore();
        }}

        private static void StopCore()
        {{
            _started = false;
            var client = _client;
            _client = null;
            client?.Dispose();
        }}
    }}
}}
"""

FUNCTIONS_TEMPLATE = """// <auto-generated/> Do not edit.
#nullable enable
using System;
using System.Text.Json.Nodes;

namespace ModulePlatform
{{
    /// <summary>Provides access to the Python functions in this module.</summary>
    public static class {module}Functions
    {{
{methods}
    }}
}}
"""

CLASS_TEMPLATE = """// <auto-generated/> Do not edit.
#nullable enable
using System;
using System.Text.Json.Nodes;

namespace ModulePlatform
{{
    /// <summary>Represents an independent Python {class_name} instance.</summary>
    public sealed class {class_name} : IDisposable
    {{
        private readonly string _instanceId;
        private bool _disposed;

        private {class_name}(string instanceId) => _instanceId = instanceId;

        /// <summary>Creates a Python {class_name} instance.</summary>
        public static {class_name} Create({factory_signature})
        {{
            var initParams = new JsonObject();
{factory_init}
            var instanceId = {module}Runtime.CreateInstance("{class_name}", initParams);
            return new {class_name}(instanceId);
        }}

        /// <summary>Releases this Python class instance.</summary>
        public void Dispose()
        {{
            if (_disposed)
                return;
            {module}Runtime.DestroyInstance("{class_name}", _instanceId);
            _disposed = true;
        }}

{methods}
    }}
}}
"""


def _factory_init(class_info: dict) -> str:
    lines = []
    for param in class_info["init_params"]:
        name = _cs_id(param["name"])
        if param["has_default"]:
            lines.extend([
                f"            if ({name} is {{ }} value_{name})",
                f'                initParams[{json.dumps(param["name"])}] = JsonValue.Create(value_{name});',
            ])
        else:
            lines.append(
                f'            initParams[{json.dumps(param["name"])}] = JsonValue.Create({name});'
            )
    return "\n".join(lines)


def _factory_signature(class_info: dict) -> str:
    parameters = []
    for param in class_info["init_params"]:
        name = _cs_id(param["name"])
        cs_type = PY2CS[param["annotation"]]
        if param["has_default"]:
            parameters.append(f"{cs_type}? {name} = null")
        else:
            parameters.append(f"{cs_type} {name}")
    return ", ".join(parameters)

def gen_csharp(meta: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    module = "".join(part.capitalize() for part in meta["module"].split("_"))
    runtime = RUNTIME_TEMPLATE.format(
        module=module,
        source_hash=json.dumps(meta["source_hash"]),
        exe_name=json.dumps(meta["exe_name"]),
        server_script_name=json.dumps(f'{meta["module"]}_rpc_server.py'),
    )
    (out_dir / f"{module}Runtime.cs").write_text(runtime, encoding="utf-8", newline="\n")

    functions = FUNCTIONS_TEMPLATE.format(
        module=module,
        methods=_gen_methods(meta["functions"], None, f"{module}Runtime"),
    )
    (out_dir / f"{module}Functions.cs").write_text(functions, encoding="utf-8", newline="\n")

    for cls in meta["classes"]:
        generated = CLASS_TEMPLATE.format(
            module=module,
            class_name=cls["name"],
            factory_signature=_factory_signature(cls),
            factory_init=_factory_init(cls),
            methods=_gen_methods(
                cls["methods"],
                cls["name"],
                f"{module}Runtime",
                instance_id="_instanceId",
            ),
        )
        (out_dir / f"{cls['name']}.cs").write_text(generated, encoding="utf-8", newline="\n")
        obsolete_proxy = out_dir / f"{cls['name']}Instance.cs"
        if obsolete_proxy.exists():
            obsolete_proxy.unlink()
