import os
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

    @filter.command("skland绑定")
    async def cmd_bind_password(self, event: AstrMessageEvent):
        """
        用密码绑定森空岛账号。
        用法：/skland绑定 手机号 密码
        """
        parts = event.message_str.strip().split()
        if len(parts) < 3:
            yield event.plain_result(_BIND_HELP)
            event.stop_event()
            return

        phone, password = parts[1], parts[2]
        qq_id = self._sender_id(event)

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

    @filter.command("skland发送验证码")
    async def cmd_send_code(self, event: AstrMessageEvent):
        """
        向手机号发送森空岛登录验证码。
        用法：/skland发送验证码 手机号
        """
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("用法：/skland发送验证码 手机号")
            event.stop_event()
            return

        phone = parts[1]
        try:
            await send_phone_code(phone)
        except SklandAPIError as e:
            yield event.plain_result(f"❌ 发送失败：{e}")
            event.stop_event()
            return

        yield event.plain_result(f"📱 验证码已发送至 {phone[:3]}****{phone[-4:]}，请在 5 分钟内使用 /skland绑定验证码 完成绑定。")
        event.stop_event()

    @filter.command("skland绑定验证码")
    async def cmd_bind_code(self, event: AstrMessageEvent):
        """
        用短信验证码绑定森空岛账号。
        用法：/skland绑定验证码 手机号 验证码
        """
        parts = event.message_str.strip().split()
        if len(parts) < 3:
            yield event.plain_result("用法：/skland绑定验证码 手机号 验证码")
            event.stop_event()
            return

        phone, sms_code = parts[1], parts[2]
        qq_id = self._sender_id(event)

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

    @filter.command("skland状态")
    async def cmd_status(self, event: AstrMessageEvent):
        """
        查询当前账号的森空岛绑定状态及 cred 有效性。
        用法：/skland状态
        """
        qq_id = self._sender_id(event)
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

    @filter.command("skland解绑")
    async def cmd_unbind(self, event: AstrMessageEvent):
        """
        解除森空岛账号绑定并删除本地凭证。
        用法：/skland解绑
        """
        qq_id = self._sender_id(event)
        deleted = self._db.delete(qq_id)
        if deleted:
            yield event.plain_result("✅ 已成功解除森空岛账号绑定，本地凭证已删除。")
        else:
            yield event.plain_result("❌ 你尚未绑定森空岛账号。")
        event.stop_event()

    @filter.command("skland帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """
        显示所有可用命令。
        """
        help_text = (
            "🗂 森空岛Bot 可用命令\n\n"
            "绑定账号（密码）：\n  /skland绑定 手机号 密码\n\n"
            "绑定账号（验证码）：\n"
            "  第一步：/skland发送验证码 手机号\n"
            "  第二步：/skland绑定验证码 手机号 验证码\n\n"
            "查询绑定状态：\n  /skland状态\n\n"
            "解除绑定：\n  /skland解绑\n\n"
            "本帮助：\n  /skland帮助"
        )
        yield event.plain_result(help_text)
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        text = (event.message_str or "").strip()
        _reply_map = {
            "/测试1": "这是测试1的固定回复。",
            "/测试2": "这是测试2的固定回复。",
            "/测试3": "这是测试3的固定回复。",
            "测试1": "这是测试1的固定回复。",
            "测试2": "这是测试2的固定回复。",
            "测试3": "这是测试3的固定回复。",
        }
        reply = _reply_map.get(text)
        if reply:
            yield event.plain_result(reply)
            event.stop_event()
