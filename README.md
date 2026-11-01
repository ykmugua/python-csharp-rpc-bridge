# Python-C# RPC Bridge

将 Python 业务模块接入 C# 应用。构建工具扫描 Python 接口，生成 RPC 服务端、接口元数据和 C# 调用 API；C# 桥接库启动独立 Python 进程，通过长度前缀 JSON 请求调用业务代码。

## 工作流程

1. 在 `modules/` 编写 Python 模块，例如 `sample.py`。
2. 生成器检查函数和类接口，输出 Python RPC 服务端与 C# API。
3. .NET 构建将通用桥接库和生成的 C# API 编译成 DLL。
4. C# Runtime 启动 Python 后端并校验源码哈希，再转发函数和类实例调用。

Python 代码不会被翻译成 C#；业务逻辑仍由 Python 进程执行。

## 快速开始

### 环境

- Python 3.14 或更高版本
- [uv](https://docs.astral.sh/uv/)
- .NET SDK 8，用于构建目标为 .NET Framework 4.8 的桥接库
- Release 后端打包需要 Nuitka 和 Zig；Debug 不需要 Zig

### 构建示例

在 Windows PowerShell 仓库根目录运行：

```powershell
uv sync --locked
uv run --locked python -m pytest -q
.\modules\build.bat
```

脚本会列出 `modules/` 下的 Python 文件。选择 `sample.py` 后，再选择配置：

- **Debug**：不运行 Nuitka，输出 Python 脚本后端；运行时需要 Python 解释器。默认使用 PATH 中的 `python`，也可通过 `PYF_PYTHON` 指定解释器。
- **Release**：通过 Nuitka 生成独立后端 EXE；需要在 `toolchain/zig-*` 下放置一个 Zig 发行目录。

详细的 Zig 放置要求见[工具链说明](./toolchain/README.md)。

## 构建产物

以 `sample.py` 为例，构建后目录如下：

```text
modules/
├── sample.py
└── sample/
    ├── generated/
    │   ├── python/             元数据、RPC 服务端和业务源码副本
    │   └── csharp/             生成的 Runtime、函数门面和类代理
    └── out/net48/
        ├── debug/              sample.dll、Python 后端及依赖
        └── release/            sample.dll、sample_rpc.exe 及依赖
```

DLL 和后端使用 Python 文件基名命名：`sample.py` 对应 `sample.dll`、`sample_rpc_server.py` 和 `sample_rpc.exe`。`generated/` 中的文件由工具生成，不要手工编辑。修改 Python 源码后重新构建，并部署同一次构建生成的 DLL 和后端。

## C# 调用

示例模块提供 `add` 和带状态的 `TextProcessor`。生成后的 API 可以这样使用：

```csharp
using System;
using ModulePlatform;

SampleRuntime.Start();
try
{
    Console.WriteLine(SampleFunctions.Add_pyf(20, 22));

    using var processor = TextProcessor.Create(lang: "fr", verbose: true);
    Console.WriteLine(processor.Normalize_pyf("  hello   world "));
}
finally
{
    SampleRuntime.Stop();
}
```

可运行的完整调用示例见 [examples/csharp/Program.cs](./examples/csharp/Program.cs)。一键构建只生成模块 DLL 和后端，不会编译该可选示例程序。

## 目录

```text
src/python_csharp_rpc_bridge/  Python 扫描器与生成器
src/csharp/                   C# RPC 桥接库
modules/                      Python 业务模块、生成文件和构建产物
examples/csharp/              可选 C# 调用示例源码
tests/                        自动化测试
toolchain/                    本地 Zig 工具链目录
doc/                          项目介绍与需求说明
```

## 其他文档

- [项目介绍](./doc/项目介绍.md)：架构、模块接入、运行时和手动构建说明。
- [需求说明](./doc/需求说明.md)：功能范围、接口约束和验收标准。
- [Zig 工具链](./toolchain/README.md)：Release 打包所需的 Zig 配置。
