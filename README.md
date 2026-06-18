# 黍饼Bot — 森空岛数据查询插件

基于 [AstrBot](https://github.com/Soulter/AstrBot) 的 《明日方舟》森空岛数据查询插件。

## 功能

- 通过手机号+密码或手机号+短信验证码绑定森空岛账号
- QQ 用户与森空岛凭证（cred/token）一一对应，本地 SQLite 安全存储
- 查询绑定状态及凭证有效性
- 解绑账号

## 命令列表

| 命令 | 说明 |
|---|---|
| `/skland绑定 手机号 密码` | 用密码登录并绑定森空岛账号 |
| `/skland发送验证码 手机号` | 向手机号发送短信验证码 |
| `/skland绑定验证码 手机号 验证码` | 用短信验证码绑定森空岛账号 |
| `/skland状态` | 查询当前绑定状态及凭证有效性 |
| `/skland解绑` | 解除绑定并删除本地凭证 |
| `/skland帮助` | 显示所有可用命令 |

## 目录结构

```
astrbot_plugin_ShuRosti_Bot/
├── main.py          # 插件主入口，注册所有命令
├── skland_api.py    # 森空岛 API 封装（登录/签名/校验）
├── database.py      # SQLite 数据库操作（用户凭证存储）
├── data/
│   └── tokens.db    # 运行时自动创建，存储用户凭证
├── metadata.yaml
└── README.md
```

## 登录流程说明

```
[密码登录]
1. 手机号+密码 → 鹰角账号 token
2. 鹰角 token  → OAuth2 授权码
3. OAuth2 码   → 森空岛 cred + token（存入数据库）

[验证码登录]
1. /skland发送验证码 手机号
2. 手机号+验证码 → 鹰角账号 token
3. 鹰角 token  → OAuth2 授权码
4. OAuth2 码   → 森空岛 cred + token（存入数据库）
```

## 安全说明

- 凭证仅存储在 Bot 服务器本地，不会上传到任何第三方
- 请勿在公开场合发送包含手机号/密码的绑定命令
- 建议使用验证码登录方式，避免密码明文传输

## 依赖

- `aiohttp`（AstrBot 已内置）
- Python 标准库：`sqlite3`、`hashlib`、`hmac`
