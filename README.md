# python-csharp-rpc-bridge
本项目把受约束的 Python 业务模块接入 C# 应用。构建工具扫描 Python 源码，生成 RPC 服务端、元数据和 C# 调用门面；C# Runtime 通过标准输入/输出上的长度前缀 JSON 协议调用独立 Python 进程。
