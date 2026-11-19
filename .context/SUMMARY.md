# 项目状态摘要

## 最近变更（2026-11-19）

### modules/build.bat 重构
- 去掉 Release/Debug 划分，产物统一输出到 `modules/<模块名>/out/net48/`
- 三种构建模式：refresh（刷新 generated + 更新输出 py + 删除旧 exe）、compile（refresh + 重编 C# DLL）、pack（compile + Nuitka/Zig 打包）
- 任何模式都会刷新 `generated/` 内容
- 已实测 refresh 模式全流程通过

### 文档同步更新
- README.md、doc/项目介绍.md、doc/需求说明.md、doc/AI生成Python代码规范.md、toolchain/README.md
- examples/csharp/SampleExample.csproj 默认输出路径改为 `..\..\modules\sample\out\net48`
- 说明文字中的 Debug/Release 模式描述改为 refresh/compile/pack

## 构建要点
- uv 默认缓存在受限环境会报锁错误，可用 UV_CACHE_DIR 指向可写目录绕过
- pack 模式依赖 toolchain/zig-* 下唯一的 zig.exe，以及 Nuitka
