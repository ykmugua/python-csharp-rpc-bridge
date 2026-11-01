# Python 到 C# RPC 桥接

本项目把受约束的 Python 业务模块接入 C# 应用。构建工具扫描 Python 源码，生成 RPC 服务端、元数据和 C# 调用门面；C# Runtime 通过标准输入/输出上的长度前缀 JSON 协议调用独立 Python 进程。

## 快速开始

环境要求：Python 3.14+、`uv`、.NET SDK 8（目标框架为 .NET Framework 4.8）。Release 独立后端打包还需要 Nuitka 和 Zig。

```powershell
uv sync --locked
uv run --locked python -m pytest -q
$env:SOURCE_DATE_EPOCH = "0"
uv run python -m python_csharp_rpc_bridge.build_tools.build
$backend = Join-Path (Get-Location).Path 'modules\sample\out\net48\release'
dotnet build src\csharp\ModulePlatform.csproj -c Release -o $backend -p:PyfModuleName=sample -p:PyfBackendDir="$backend"
Copy-Item modules\sample\generated\python\*.py $backend
```

Windows 一键构建会交互选择 Python 文件以及 Release/Debug：

```powershell
.\modules\build.bat
```

Debug 不使用 Nuitka；Release 会以 Nuitka 打包后端，并需要把一个 Zig 发行目录放在 `toolchain\zig-*` 下。详细说明见[工具链文档](./toolchain/README.md)。

## 目录和命名约定

```text
src/python_csharp_rpc_bridge/ Python 包、扫描器与生成器
src/csharp/            C# 桥接库和 RPC Runtime
modules/               Python 业务模块及 Windows 构建入口
  build.bat
  sample.py             示例业务源码
  sample/
    generated/          自动生成的 Python/C# 源码
    out/net48/           DLL、后端和部署依赖
examples/csharp/        可选的 C# 调用示例源码（不由一键构建）
tests/                  自动化测试
toolchain/              本地 Zig 工具链（不提交编译器文件）
doc/                    项目介绍与需求说明
```

模块名来自 Python 文件名：`sample.py` 生成 `sample.dll`、`sample_rpc_server.py` 和 `sample_rpc.exe`。多模块构建时，每个模块在 `modules/` 下有独立的同名输出目录，例如 `modules/order_service/generated/`。生成文件由工具更新，不要手工编辑；修改业务代码后重新生成并重新构建、部署匹配的 DLL 和后端。

## 示例

[示例业务源码](./modules/sample.py)提供 `add` 和带状态的 `TextProcessor`；[C# 示例源码](./examples/csharp/Program.cs)展示 `add(20, 22)` 及多个互相独立的实例。构建脚本只生成模块 DLL 和后端，不编译这个可选示例程序，也不会创建示例的 `out` 目录。

## 文档

- [项目介绍](./doc/项目介绍.md)：结构、构建流程、模块开发和运行时说明。
- [需求说明](./doc/需求说明.md)：功能范围、接口约束及验收标准。
- [Zig 工具链](./toolchain/README.md)：Release 打包所需的本地编译器配置。
