# Changelog

All notable changes to this project will be documented in this file.

## [1.0.15] - 2026-06-18

### Fixed

- 修复森空岛游戏接口返回 HTTP 401 的根本原因：所有需鉴权的请求现在正确生成并携带 `sign` 签名请求头
- 新增 `_generate_sign` 函数，实现官方 HMAC-SHA256 + MD5 双重签名算法（以 `token` 为密钥，对 `请求路径 + body/query + 时间戳 + 固定 header JSON` 进行签名）
- `_sk_get` 与 `_sk_post` 在持有 `token` 时自动注入 `sign`、`platform`、`timestamp`、`dId`、`vName` 等必要请求头

## [1.0.14] - 2026-06-18

### Fixed

- 修复游戏相关 API 接口认证失败的问题（再次修复）。确保 `_sk_get` 与 `_sk_post` 在所有游戏接口调用路径中均正确传递 `token` 请求头，解决登录后立即签到仍返回 401 的问题

## [1.0.13] - 2026-06-18

### Fixed

- 修复游戏相关 API 接口认证失败的问题。森空岛游戏接口（获取角色列表、签到、获取奖励）需要同时提供 `cred` 和 `token` 两个请求头，现在已在所有游戏相关 API 调用中正确传递 `token` 参数
- 修复登录成功后立即调用游戏接口返回 401 错误的问题，用户重新绑定账号后可正常使用

## [1.0.12] - 2026-06-18

### Added

- 新增手动签到指令 `/{bot_name}签到`，用户可随时触发立即签到
- 新增日志文件写入功能，日志保存至 `{data_dir}/logs/shurosti_bot.log`

### Fixed

- 修复已签到状态判断逻辑，现在正确匹配森空岛返回的多种"重复签到"消息
- 修复签到奖励格式化函数 `_format_awards`，正确解析嵌套的 `resource` 结构
- 修复 `_do_sign_for_user` 内部日志记录，移除对外部 logger 参数的依赖

## [1.0.11] - 2026-06-18

### Added

- 新增详细日志记录，便于追踪签到过程中的 API 请求和响应
- `_hg_post`, `_sk_post`, `_sk_get` 函数新增请求/响应日志
- `check_cred`, `get_binding_list`, `do_attendance`, `get_monthly_rewards` 函数新增日志
- `login_with_password`, `login_with_code` 函数新增登录流程日志

### Changed

- `_do_sign_for_user` 函数增加 logger 参数，支持详细日志输出

## [1.0.9] - 2026-06-18

### Fixed

- 优化持久化存储相关处理，确保数据目录迁移稳定性

### Changed

- 签到功能异常捕获机制进一步完善

## [1.0.8] - 2026-06-18

### Changed

- 持久化存储路径改用 `StarTools.get_data_dir()` 获取标准数据目录，确保数据可靠存储
- 签到图片存储路径支持动态配置，通过 `_img_dir` 参数传递

### Added

- 旧数据迁移功能，升级时自动迁移原有数据库和签到图片

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