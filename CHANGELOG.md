# Changelog

All notable changes to this project will be documented in this file.

## [1.0.8] - 2026-06-18

### Fixed

- 修复网络请求异常（连接超时、DNS 解析失败等）无法被正确捕获的问题，现在会显示具体的错误信息而非模糊的"请求异常"

## [1.0.7] - 2026-06-18

### Added

- 新增 `bot_name` 配置参数，支持在 AstrBot 面板中自定义指令前缀（默认：「森空岛bot」）
- 新增 `/{bot_name}详细帮助` 指令，提供每个指令的详细解释

### Changed

- `/{bot_name}帮助` 格式改版：每个命令一行附带简短注释
- 所有 `{bot_name}XXX` 类指令前缀改为由配置参数动态控制

### Fixed

- `_run_all_auto_sign` 函数中捕获用户签到异常后添加日志记录，便于后续排查问题
- 修复「开启自动签到」命令中 `event.stop_event()` 提前调用导致签到结果无法发送的问题
- 修复「关闭自动签到」命令未校验账号绑定状态的问题，与开启自动签到逻辑保持一致

### Improved

- 所有同步数据库操作（sqlite3）调用均使用 `asyncio.to_thread()` 包裹，避免阻塞 async 事件循环