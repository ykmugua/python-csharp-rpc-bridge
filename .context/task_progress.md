# 任务进度

## 当前项目：python-csharp-rpc-bridge
- **当前分支**：main
- **项目标题**：Python-C# RPC Bridge
- [x] 已初始化 Context Sync
- [ ] 梳理当前项目目标与范围
- [ ] 记录首批 gotchas / architecture / api_notes
- [ ] 完成首次 /sync-save 与 /sync-load 验证

## 2026-11-19（二）：去掉运行时哈希校验

- 需求：移除 SampleRuntime.cs 的源码哈希校验；后续命令默认用 PowerShell 7（已确认 pwsh 7.7.0 可用）。
- 改动从生成源头下手（generated 文件会被覆盖）：
  - `cs_gen.py` RUNTIME_TEMPLATE：删除 `SourceHash` 常量与 `__ping` 哈希比对块，Start 注释改 “Starts the Python backend.”；`gen_csharp` 去掉 source_hash format 参数。
  - `rpc_server.py.j2`：删除 `SOURCE_HASH` 常量，`__ping` 只返回 `{"ok": True}`（保留存活探测）。
  - `rpc_gen.py`：删除 `__SOURCE_HASH__` 占位符替换。
  - 重新生成 `modules/sample/generated/`（C# 与 Python 两端）。
  - 测试：`test_generators.py` 改为断言无 SourceHash/SOURCE_HASH；`test_rpc_server.py` ping 断言改为 `{"ok": True}`。
  - 文档：README、项目介绍、需求说明、AI生成Python代码规范 去掉哈希校验描述。
- 保留：scanner/meta_gen 仍计算 `source_hash` 写入元数据（仅构建期指纹，不参与运行时校验）。
- 验证：`uv run --locked python -m pytest -q` → 37 passed。
- 环境：受限环境 uv 默认缓存锁会失败，用 `UV_CACHE_DIR=$TEMP/uv-cache-test` 绕过。
