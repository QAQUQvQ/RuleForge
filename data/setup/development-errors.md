# 开发期故障记录摘要
本文件是实际工具输出的摘要，不是 TextIn 原始错误日志。TextIn 本次解析 stderr 原文件为空。

- 沙箱执行器初始化连续失败：helper_unknown_error: setup refresh had errors。必要命令改为经批准的沙箱外执行。
- 初次 editable 安装时 backend 目录尚不存在，安装失败；创建后安装成功。
- 一次本地 JSON 读取使用 Windows 默认 GBK 导致 UnicodeDecodeError，改用显式 UTF-8。
- npm 官方源出现 DEPTH_ZERO_SELF_SIGNED_CERT。没有关闭 TLS 校验；使用国内 npm 镜像安装成功。
- SQLite documents/parse_runs 初次写入参数数量与列数不一致；已修复，事务未留下部分成功记录。
- pnpm 自动生成的构建许可配置与本地配置重复；修复为 allowBuilds: esbuild: true 后标准构建成功。
- 早期测试真实证据路径错误导致跳过；修复路径后最终 47 项测试全部通过、无跳过。

TextIn 解析未发生失败或重试，也没有付费回退。
