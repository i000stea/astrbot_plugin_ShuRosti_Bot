import asyncio
import logging
import os
import re
import time

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools

from .database import TokenDatabase
from .sign_image import cached_image_path, format_rewards_text, generate_monthly_image
from .skland_api import (
    SklandAPIError,
    check_cred,
    do_attendance,
    get_binding_list,
    get_monthly_rewards,
    login_with_code,
    login_with_password,
    send_phone_code,
    setup_file_logger,
)

_plugin_logger = logging.getLogger("astrbot_plugin_ShuRosti_Bot")

_AT_RE = re.compile(r"\[At:[^\]]*\]")

_SIGN_HOUR = 6
_SIGN_MINUTE = 0


def _extract(message_str: str, bot_name: str):
    cleaned = _AT_RE.sub("", message_str).strip()
    skland_cmds = (
        f"{bot_name}绑定手机号",
        f"{bot_name}验证码",
        f"{bot_name}登录",
        f"{bot_name}状态",
        f"{bot_name}解绑",
        f"{bot_name}帮助",
        f"{bot_name}详细帮助",
        f"{bot_name}签到",
        "开启自动签到",
        "关闭自动签到",
        "查阅本月签到奖励",
    )
    cmd_re = re.compile(
        r"^/?(" + "|".join(re.escape(c) for c in skland_cmds) + r")((?:\s+\S+)*)$"
    )
    m = cmd_re.match(cleaned)
    if m is None:
        return None, []
    cmd = m.group(1)
    args = m.group(2).split()
    return cmd, args


def _is_group_message(event: AstrMessageEvent) -> bool:
    try:
        gid = event.get_group_id() if callable(getattr(event, "get_group_id", None)) else None
        if gid not in (None, "", 0):
            return True
    except Exception:
        pass
    for k in ("group_id", "groupId", "group"):
        gid = getattr(event, k, None)
        if gid not in (None, "", 0):
            return True
    try:
        obj = getattr(event, "message_obj", None) or getattr(event, "message", None)
        if obj is not None:
            for k in ("group_id", "groupId", "group"):
                v = getattr(obj, k, None) if not isinstance(obj, dict) else obj.get(k)
                if v not in (None, "", 0):
                    return True
    except Exception:
        pass
    return False


def _format_awards(rewards: list) -> str:
    parts = []
    for r in rewards:
        if isinstance(r, dict):
            res = r.get("resource") or r
            name = res.get("name", "")
            count = r.get("count") or res.get("count", 1)
            if name:
                parts.append(f"{name}×{count}")
    return "、".join(parts) or "无奖励信息"


async def _do_sign_for_user(db: TokenDatabase, qq_id: str) -> str:
    _plugin_logger.info(f"[sign] 开始为用户 {qq_id} 执行签到")
    record = await asyncio.to_thread(db.get, qq_id)
    if record is None:
        msg = f"[{qq_id}] 未绑定账号，跳过。"
        _plugin_logger.info(msg)
        return msg

    _plugin_logger.info(f"[sign] [{qq_id}] 检查凭证有效性")
    valid = await check_cred(record.cred)
    if not valid:
        msg = f"[{qq_id}] 凭证已失效，请重新绑定。"
        _plugin_logger.warning(msg)
        return msg

    try:
        _plugin_logger.info(f"[sign] [{qq_id}] 获取角色列表")
        bindings = await get_binding_list(record.cred, record.token)
    except SklandAPIError as e:
        msg = f"[{qq_id}] 获取角色列表失败：{e}"
        _plugin_logger.error(msg)
        return msg

    if not bindings:
        return f"[{qq_id}] 未找到绑定的明日方舟角色。"

    results = []
    for b in bindings:
        uid = b["uid"]
        nick = b.get("nick_name") or uid
        gid = b.get("game_id", "1")
        _plugin_logger.info(f"[sign] [{qq_id}] 正在签到角色 nick={nick} uid={uid}")
        try:
            res = await do_attendance(record.cred, uid, gid, record.token)
        except SklandAPIError as e:
            _plugin_logger.error(f"[sign] [{qq_id}] 角色 {nick} 签到失败：{e}")
            results.append(f"  {nick}：签到失败 — {e}")
            continue
        if res["already_signed"]:
            results.append(f"  {nick}：今日已签到 ✓")
        else:
            awards = _format_awards(res["rewards"])
            results.append(f"  {nick}：签到成功！获得 {awards}")

    result_str = "\n".join(results)
    _plugin_logger.info(f"[sign] [{qq_id}] 签到完成：{result_str}")
    return result_str


@register("shurosti_bot", "iTea", "黍饼Bot — 森空岛数据查询插件", "1.0.16")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self._config = config
        self._data_dir = StarTools.get_data_dir("shurosti_bot")
        self._img_dir = str(self._data_dir / "sign_images")
        self._log_dir = str(self._data_dir / "logs")
        setup_file_logger(self._log_dir)
        _plugin_logger.info(f"[init] 插件初始化，数据目录：{self._data_dir}")
        db_path = str(self._data_dir / "tokens.db")
        self._db = TokenDatabase(db_path)
        self._sign_task = None

    async def initialize(self):
        self._sign_task = asyncio.create_task(self._auto_sign_loop())

    async def _auto_sign_loop(self):
        while True:
            now = time.localtime()
            if now.tm_hour == _SIGN_HOUR and now.tm_min == _SIGN_MINUTE:
                await self._run_auto_sign()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)

    async def _run_auto_sign(self):
        qq_ids = await asyncio.to_thread(self._db.all_auto_sign_qq_ids)
        _plugin_logger.info(f"[auto_sign] 开始自动签到，共 {len(qq_ids)} 位用户")
        for qq_id in qq_ids:
            try:
                result = await _do_sign_for_user(self._db, qq_id)
                _plugin_logger.info(f"[auto_sign] {qq_id} 签到结果：{result}")
            except Exception as e:
                _plugin_logger.error(f"[auto_sign] {qq_id} 签到异常：{e}")

    @filter.command_group("shurosti_bot")
    async def skland(self, event: AstrMessageEvent):
        pass

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        bot_name = self._config.get("bot_name", "黍饼")
        msg = str(event.message_str)
        cmd, args = _extract(msg, bot_name)
        if cmd is None:
            return

        qq_id = str(event.get_sender_id())

        if cmd == f"{bot_name}帮助":
            yield event.plain_result(
                f"黍饼Bot 指令列表：\n"
                f"  /{bot_name}绑定手机号 <手机号> — 发送验证码\n"
                f"  /{bot_name}验证码 <验证码> — 完成绑定\n"
                f"  /{bot_name}状态 — 查看绑定状态\n"
                f"  /{bot_name}解绑 — 解除绑定\n"
                f"  /{bot_name}签到 — 立即签到\n"
                f"  /开启自动签到 — 每日 {_SIGN_HOUR:02d}:{_SIGN_MINUTE:02d} 自动签到\n"
                f"  /关闭自动签到 — 关闭自动签到\n"
                f"  /查阅本月签到奖励 — 查看本月签到奖励"
            )
            return

        if cmd == f"{bot_name}详细帮助":
            yield event.plain_result(
                f"黍饼Bot 详细说明：\n"
                f"1. 先用 /{bot_name}绑定手机号 <手机号> 发送验证码\n"
                f"2. 再用 /{bot_name}验证码 <验证码> 完成登录绑定\n"
                f"3. 绑定成功后可使用签到相关功能\n"
                f"4. 自动签到时间为每日 {_SIGN_HOUR:02d}:{_SIGN_MINUTE:02d}\n"
                f"5. 凭证失效时需重新绑定"
            )
            return

        if cmd == f"{bot_name}绑定手机号":
            if not args:
                yield event.plain_result("请提供手机号，例如：/{bot_name}绑定手机号 138xxxxxxxx")
                return
            phone = args[0]
            await asyncio.to_thread(self._db.set_pending_phone, qq_id, phone, int(time.time()))
            try:
                await send_phone_code(phone)
                yield event.plain_result(f"验证码已发送至 {phone}，请在 5 分钟内使用 /{bot_name}验证码 <验证码> 完成绑定。")
            except SklandAPIError as e:
                yield event.plain_result(f"发送验证码失败：{e}")
            return

        if cmd == f"{bot_name}验证码":
            if not args:
                yield event.plain_result(f"请提供验证码，例如：/{bot_name}验证码 123456")
                return
            code = args[0]
            pending = await asyncio.to_thread(self._db.get_pending_phone, qq_id)
            if pending is None:
                yield event.plain_result(f"未找到待绑定的手机号，请先使用 /{bot_name}绑定手机号 <手机号>")
                return
            phone, _ = pending
            try:
                token_obj = await login_with_code(phone, code)
                await asyncio.to_thread(
                    self._db.upsert,
                    qq_id,
                    token_obj["cred"],
                    token_obj["token"],
                    token_obj.get("userId", ""),
                    phone,
                    int(time.time()),
                )
                await asyncio.to_thread(self._db.delete_pending_phone, qq_id)
                yield event.plain_result("绑定成功！森空岛账号已关联。")
            except SklandAPIError as e:
                yield event.plain_result(f"登录失败：{e}")
            return

        if cmd == f"{bot_name}登录":
            if len(args) < 2:
                yield event.plain_result(f"用法：/{bot_name}登录 <手机号> <密码>")
                return
            phone, password = args[0], args[1]
            try:
                token_obj = await login_with_password(phone, password)
                await asyncio.to_thread(
                    self._db.upsert,
                    qq_id,
                    token_obj["cred"],
                    token_obj["token"],
                    token_obj.get("userId", ""),
                    phone,
                    int(time.time()),
                )
                yield event.plain_result("登录并绑定成功！")
            except SklandAPIError as e:
                yield event.plain_result(f"登录失败：{e}")
            return

        if cmd == f"{bot_name}状态":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result("你尚未绑定森空岛账号。")
                return
            valid = await check_cred(record.cred)
            status = "有效 ✓" if valid else "已失效 ✗（请重新绑定）"
            auto = await asyncio.to_thread(self._db.get_auto_sign, qq_id)
            auto_str = "已开启" if auto else "未开启"
            yield event.plain_result(
                f"绑定手机：{record.phone or '未知'}\n"
                f"凭证状态：{status}\n"
                f"自动签到：{auto_str}"
            )
            return

        if cmd == f"{bot_name}解绑":
            deleted = await asyncio.to_thread(self._db.delete, qq_id)
            if deleted:
                yield event.plain_result("已解除绑定。")
            else:
                yield event.plain_result("你尚未绑定账号。")
            return

        if cmd == f"{bot_name}签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result("你尚未绑定账号，请先绑定。")
                return
            yield event.plain_result("正在签到，请稍候...")
            result = await _do_sign_for_user(self._db, qq_id)
            yield event.plain_result(f"签到结果：\n{result}")
            return

        if cmd == "开启自动签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result("你尚未绑定账号，请先绑定。")
                return
            await asyncio.to_thread(self._db.set_auto_sign, qq_id, True)
            yield event.plain_result(f"已开启自动签到，每日 {_SIGN_HOUR:02d}:{_SIGN_MINUTE:02d} 自动为你签到。")
            return

        if cmd == "关闭自动签到":
            await asyncio.to_thread(self._db.set_auto_sign, qq_id, False)
            yield event.plain_result("已关闭自动签到。")
            return

        if cmd == "查阅本月签到奖励":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result("你尚未绑定账号，请先绑定。")
                return
            try:
                bindings = await get_binding_list(record.cred, record.token)
            except SklandAPIError as e:
                yield event.plain_result(f"获取角色列表失败：{e}")
                return
            if not bindings:
                yield event.plain_result("未找到绑定的明日方舟角色。")
                return
            default_binding = bindings[0]
            try:
                sign_list = await get_monthly_rewards(
                    record.cred,
                    default_binding["uid"],
                    default_binding.get("game_id", "1"),
                    record.token,
                )
            except SklandAPIError as e:
                yield event.plain_result(f"获取签到奖励失败：{e}")
                return

            img_path = cached_image_path(self._img_dir, qq_id)
            try:
                await asyncio.to_thread(generate_monthly_image, sign_list, img_path)
                yield event.image_result(img_path)
            except Exception:
                text = format_rewards_text(sign_list)
                yield event.plain_result(text)
            return

    async def terminate(self):
        if self._sign_task is not None:
            self._sign_task.cancel()
            try:
                await self._sign_task
            except asyncio.CancelledError:
                pass
