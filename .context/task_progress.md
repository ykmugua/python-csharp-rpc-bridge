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

## 2026-11-19（三）：generated 彻底清理 + 测试预期同步

- 需求：refresh 执行时要把 generated 清干净，避免旧依赖/旧类门面残留。
- 改动：`modules/build.bat` 生成前直接 `rmdir /S /Q "%MODULE_ROOT%\generated"` 整个删除再重建（三种模式都生效）；旧 exe 仍从 out\net48 删除。
- 验证：塞入 OldClass.cs / shared/deletion.py 垃圾文件，清理重建后均消失；pytest 37 passed。
- 另：用户确认 `delete_item` 硬编码返回 `[1,2,3]` 是故意的，同步更新 `tests/test_business.py` 和 `tests/test_rpc_server.py` 的断言为 `[1,2,3]`。
- 待办：本轮 build.bat / meta.json / 两个测试文件的改动需 git commit + push（上个提交 a388c18 尚未 push，本地 ahead 1）。
