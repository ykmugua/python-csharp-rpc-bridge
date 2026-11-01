import json
from pathlib import Path

from python_csharp_rpc_bridge.build_tools.build import build_module, main
from python_csharp_rpc_bridge.build_tools.cs_gen import gen_csharp
from python_csharp_rpc_bridge.build_tools.rpc_gen import gen_rpc_server
from python_csharp_rpc_bridge.build_tools.scanner import scan_module


def test_generated_rpc_and_facade_cover_the_sample(tmp_path):
    business = Path("modules/sample.py")
    scanned = scan_module(business)
    rpc_path = gen_rpc_server(scanned, business, tmp_path / "out")
    meta = {
        "module": "sample",
        "exe_name": "sample_rpc.exe",
        "source_hash": scanned["source_hash"],
        "functions": [
            {
                "qualname": function["name"],
                "params": function["params"],
                "return_annotation": function["return_annotation"],
                "doc": function["doc"],
            }
            for function in scanned["functions"]
        ],
        "classes": [
            {
                **class_info,
                "methods": [
                    {
                        **method,
                        "qualname": f"{class_info['name']}.{method['name']}",
                    }
                    for method in class_info["methods"]
                ],
            }
            for class_info in scanned["classes"]
        ],
    }
    generated_dir = tmp_path / "generated"
    gen_csharp(meta, generated_dir)

    assert rpc_path.is_file()
    assert rpc_path.name == "sample_rpc_server.py"
    assert "SOURCE_HASH" in rpc_path.read_text(encoding="utf-8")
    assert "import sample as BUSINESS" in rpc_path.read_text(encoding="utf-8")
    functions = (generated_dir / "SampleFunctions.cs").read_text(encoding="utf-8")
    assert "public static class SampleFunctions" in functions
    assert "Add_pyf(int a, int b)" in functions
    assert "SampleRuntime.Client.Invoke<int>(\"add\"" in functions
    assert "Delete_item_pyf(int[] values, int index)" in functions
    assert "JsonSerializer.SerializeToNode(values)" in functions
    assert "Invoke<int[]>(\"delete_item\"" in functions
    assert "/// <summary>" in functions
    assert "Return the sum of two integers." in functions
    assert "public SampleFunctions(" not in functions
    processor = (generated_dir / "TextProcessor.cs").read_text(encoding="utf-8")
    assert "public string Lang\n        {" in processor
    assert "public bool Verbose\n        {" in processor
    assert '["member_name"] = "lang", ["value"] = JsonValue.Create(value)' in processor
    assert '["member_name"] = "verbose", ["value"] = JsonValue.Create(value)' in processor
    assert "public int Calls" in processor
    assert '["member_name"] = "calls", ["value"] = JsonValue.Create(value)' in processor
    assert '"__get_member"' in processor
    assert '"__set_member"' in processor
    runtime = (generated_dir / "SampleRuntime.cs").read_text(encoding="utf-8")
    assert "public static class SampleRuntime" in runtime
    assert "internal static StdioRpcClient Client" in runtime
    assert "namespace ModulePlatform" in runtime
    assert "using ModulePlatform.PyfRpc;" in runtime
    assert f'SourceHash = {json.dumps(scanned["source_hash"])}' in runtime
    assert 'CreateClient("sample_rpc.exe", "sample_rpc_server.py")' in runtime
    assert "public static void Start()" in runtime
    assert "public static void Stop()" in runtime
    assert "InitOptions" not in runtime
    assert "GetDefaultInstanceId" not in runtime


def test_generated_class_facade_supports_instance_methods(tmp_path):
    business = Path("tests/fixtures/business.py")
    generated_dir = tmp_path / "csharp"
    build_module("business", business, tmp_path / "python", generated_dir)

    processor = (generated_dir / "TextProcessor.cs").read_text(encoding="utf-8")
    assert "public sealed class TextProcessor : IDisposable" in processor
    assert "public static TextProcessor Create(string? lang = null, bool? verbose = null)" in processor
    assert "Normalize_pyf_json(string jsonArgs)" in processor
    assert "public string Normalize_pyf(string text)" in processor
    assert 'InvokeInstance<string>("TextProcessor.normalize", _instanceId' in processor
    assert 'initParams["lang"] = JsonValue.Create(value_lang);' in processor
    assert 'initParams["verbose"] = JsonValue.Create(value_verbose);' in processor


def test_module_build_writes_python_and_csharp_to_requested_directories(tmp_path):
    sample_root = tmp_path / "sample"
    csharp_generated = tmp_path / "csharp_generated"
    source = Path("modules/sample.py")

    build_module(
        "sample",
        source,
        sample_root / "generated" / "python",
        csharp_generated,
    )

    assert (sample_root / "generated" / "python" / "meta.json").is_file()
    assert (sample_root / "generated" / "python" / "sample_rpc_server.py").is_file()
    copied_source = sample_root / "generated" / "python" / "sample.py"
    assert copied_source.is_file()
    rpc_server = (sample_root / "generated" / "python" / "sample_rpc_server.py").read_text(
        encoding="utf-8"
    )
    assert "import sample as BUSINESS" in rpc_server
    assert (csharp_generated / "SampleFunctions.cs").is_file()
    assert not (sample_root / "generated" / "csharp").exists()


def test_standalone_build_generates_python_and_csharp_under_output_root(tmp_path):
    source = tmp_path / "order_service.py"
    source.write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "sample"

    assert main(
        [
            "--source-file",
            str(source),
            "--output-root",
            str(output_root),
        ]
    ) == 0

    python_output = output_root / "generated" / "python"
    csharp_output = output_root / "generated" / "csharp"
    metadata = json.loads((python_output / "meta.json").read_text(encoding="utf-8"))
    assert metadata["exe_name"] == "order_service_rpc.exe"
    assert (python_output / "order_service_rpc_server.py").is_file()
    assert (python_output / "order_service.py").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    functions = (csharp_output / "OrderServiceFunctions.cs").read_text(encoding="utf-8")
    assert "Add_pyf(int a, int b)" in functions
    runtime = (csharp_output / "OrderServiceRuntime.cs").read_text(encoding="utf-8")
    assert 'CreateClient("order_service_rpc.exe", "order_service_rpc_server.py")' in runtime


def test_build_copies_recursive_local_imports(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "business.py").write_text(
        "from helper import helper\n\n"
        "def run(value: int) -> int:\n"
        "    return helper(value)\n",
        encoding="utf-8",
    )
    (source_dir / "helper.py").write_text(
        "from more import increment\n\n"
        "def helper(value):\n"
        "    return increment(value)\n",
        encoding="utf-8",
    )
    (source_dir / "more.py").write_text(
        "def increment(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "output"
    python_output = output_root / "generated" / "python"

    build_module(
        "business",
        source_dir / "business.py",
        python_output,
        output_root / "generated" / "csharp",
    )

    assert (python_output / "helper.py").read_text(encoding="utf-8") == (
        source_dir / "helper.py"
    ).read_text(encoding="utf-8")
    assert (python_output / "more.py").is_file()


def test_generated_facades_map_typed_collections_for_functions_and_methods(tmp_path):
    source = tmp_path / "collections.py"
    source.write_text(
        "def echo_numbers(values: list[float]) -> list[float]:\n"
        "    return values\n\n"
        "def echo_names(values: list[str]) -> list[str]:\n"
        "    return values\n\n"
        "def echo_flags(values: list[bool]) -> list[bool]:\n"
        "    return values\n\n"
        "def echo_records(values: list[dict[str, int]]) -> list[dict[str, int]]:\n"
        "    return values\n\n"
        "class CollectionStore:\n"
        "    def replace(self, values: list[str]) -> list[str]:\n"
        "        \"\"\"Write the stored string values.\"\"\"\n"
        "        return values\n",
        encoding="utf-8",
    )
    generated_dir = tmp_path / "csharp"
    build_module(
        "collections",
        source,
        tmp_path / "python",
        generated_dir,
    )

    functions = (generated_dir / "CollectionsFunctions.cs").read_text(encoding="utf-8")
    assert "Echo_numbers_pyf(double[] values)" in functions
    assert "Echo_names_pyf(string[] values)" in functions
    assert "Echo_flags_pyf(bool[] values)" in functions
    assert "Echo_records_pyf(JsonObject[] values)" in functions
    assert "JsonSerializer.SerializeToNode(values)" in functions
    assert "Invoke<double[]>(\"echo_numbers\"" in functions
    assert "Invoke<string[]>(\"echo_names\"" in functions
    assert "Invoke<bool[]>(\"echo_flags\"" in functions
    assert "Invoke<JsonObject[]>(\"echo_records\"" in functions

    store = (generated_dir / "CollectionStore.cs").read_text(encoding="utf-8")
    assert "public string[] Replace_pyf(string[] values)" in store
    assert "JsonSerializer.SerializeToNode(values)" in store
