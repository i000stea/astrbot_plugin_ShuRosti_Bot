import os
import re
import time

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .database import TokenDatabase
from .skland_api import (
    SklandAPIError,
    check_cred,
    login_with_code,
    login_with_password,
    send_phone_code,
)

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tokens.db")

_BIND_HELP = (
    "绑定森空岛账号用法：\n"
    "  密码登录：/skland绑定 手机号 密码\n"
    "  验证码登录（先发验证码）：\n"
    "    第一步：/skland发送验证码 手机号\n"
    "    第二步：/skland绑定验证码 手机号 验证码"
)

_AT_RE = re.compile(r"\[At:[^\]]*\]")

_SKLAND_CMDS = (
    "skland绑定验证码",
    "skland绑定",
    "skland发送验证码",
    "skland状态",
    "skland解绑",
    "skland帮助",
)

_CMD_RE = re.compile(
    r"^/?(" + "|".join(re.escape(c) for c in _SKLAND_CMDS) + r")((?:\s+\S+)*)$"
)


def _extract(message_str: str):
    cleaned = _AT_RE.sub("", message_str).strip()
    m = _CMD_RE.match(cleaned)
    if m is None:
        return None, []
    cmd = m.group(1)
    args = m.group(2).split()
    return cmd, args


@register("shurosti_bot", "iTea", "黍饼Bot — 森空岛数据查询插件", "1.2.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._db = TokenDatabase(_DB_PATH)

    async def initialize(self):
        pass

    async def terminate(self):
        pass

    def _sender_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_sender_id())

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        text = _AT_RE.sub("", event.message_str or "").strip()

        _reply_map = {
            "/测试1": "这是测试1的固定回复。",
            "/测试2": "这是测试2的固定回复。",
            "/测试3": "这是测试3的固定回复。",
            "测试1": "这是测试1的固定回复。",
            "测试2": "这是测试2的固定回复。",
            "测试3": "这是测试3的固定回复。",
        }
        if text in _reply_map:
            yield event.plain_result(_reply_map[text])
            event.stop_event()
            return

        cmd, args = _extract(event.message_str or "")
        if cmd is None:
            return

        qq_id = self._sender_id(event)

        if cmd == "skland帮助":
            yield event.plain_result(
                "🗂 森空岛Bot 可用命令\n\n"
                "绑定账号（密码）：\n  /skland绑定 手机号 密码\n\n"
                "绑定账号（验证码）：\n"
                "  第一步：/skland发送验证码 手机号\n"
                "  第二步：/skland绑定验证码 手机号 验证码\n\n"
                "查询绑定状态：\n  /skland状态\n\n"
                "解除绑定：\n  /skland解绑\n\n"
                "本帮助：\n  /skland帮助"
            )
            event.stop_event()
            return

        if cmd == "skland状态":
            record = self._db.get(qq_id)
            if record is None:
                yield event.plain_result(f"❌ 你尚未绑定森空岛账号。\n{_BIND_HELP}")
                event.stop_event()
                return
            valid = await check_cred(record.cred)
            update_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.updated_at))
            status_icon = "✅ 有效" if valid else "❌ 已失效（请重新绑定）"
            yield event.plain_result(
                f"📋 森空岛绑定信息\n"
                f"森空岛用户 ID：{record.skland_user_id}\n"
                f"手机号：{record.phone[:3]}****{record.phone[-4:] if len(record.phone) >= 4 else record.phone}\n"
                f"凭证状态：{status_icon}\n"
                f"最后更新：{update_time}"
            )
            event.stop_event()
            return

        if cmd == "skland解绑":
            deleted = self._db.delete(qq_id)
            if deleted:
                yield event.plain_result("✅ 已成功解除森空岛账号绑定，本地凭证已删除。")
            else:
                yield event.plain_result("❌ 你尚未绑定森空岛账号。")
            event.stop_event()
            return

        if cmd == "skland发送验证码":
            if len(args) < 1:
                yield event.plain_result("用法：/skland发送验证码 手机号")
                event.stop_event()
                return
            phone = args[0]
            try:
                await send_phone_code(phone)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 发送失败：{e}")
                event.stop_event()
                return
            yield event.plain_result(
                f"📱 验证码已发送至 {phone[:3]}****{phone[-4:]}，"
                "请在 5 分钟内使用 /skland绑定验证码 完成绑定。"
            )
            event.stop_event()
            return

        if cmd == "skland绑定验证码":
            if len(args) < 2:
                yield event.plain_result("用法：/skland绑定验证码 手机号 验证码")
                event.stop_event()
                return
            phone, sms_code = args[0], args[1]
            try:
                result = await login_with_code(phone, sms_code)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 登录失败：{e}")
                event.stop_event()
                return
            self._db.upsert(
                qq_id=qq_id,
                cred=result["cred"],
                token=result["token"],
                skland_user_id=result["user_id"],
                phone=phone,
                updated_at=int(time.time()),
            )
            yield event.plain_result(
                f"✅ 绑定成功！\n森空岛用户 ID：{result['user_id']}\n"
                "凭证已安全保存，请勿将凭证告知他人。"
            )
            event.stop_event()
            return

        if cmd == "skland绑定":
            if len(args) < 2:
                yield event.plain_result(_BIND_HELP)
                event.stop_event()
                return
            phone, password = args[0], args[1]
            try:
                result = await login_with_password(phone, password)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 登录失败：{e}")
                event.stop_event()
                return
            self._db.upsert(
                qq_id=qq_id,
                cred=result["cred"],
                token=result["token"],
                skland_user_id=result["user_id"],
                phone=phone,
                updated_at=int(time.time()),
            )
            yield event.plain_result(
                f"✅ 绑定成功！\n森空岛用户 ID：{result['user_id']}\n"
                "凭证已安全保存，请勿将凭证告知他人。"
            )
            event.stop_event()
