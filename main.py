import asyncio
import os
import re
import time

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

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
)

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tokens.db")

_BIND_HELP = (
    "绑定森空岛账号用法：\n"
    "  密码登录（建议私聊）：/skland登录 手机号 密码\n"
    "  验证码登录：\n"
    "    第一步：/skland绑定手机号 手机号\n"
    "    第二步：/skland验证码 验证码"
)

_AT_RE = re.compile(r"\[At:[^\]]*\]")

_SKLAND_CMDS = (
    "skland绑定手机号",
    "skland验证码",
    "skland登录",
    "skland状态",
    "skland解绑",
    "skland帮助",
    "开启自动签到",
    "关闭自动签到",
    "查阅本月签到奖励",
)

_CMD_RE = re.compile(
    r"^/?(" + "|".join(re.escape(c) for c in _SKLAND_CMDS) + r")((?:\s+\S+)*)$"
)

_SIGN_HOUR = 6
_SIGN_MINUTE = 0


def _extract(message_str: str):
    cleaned = _AT_RE.sub("", message_str).strip()
    m = _CMD_RE.match(cleaned)
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


async def _do_sign_for_user(db: TokenDatabase, qq_id: str) -> str:
    record = await asyncio.to_thread(db.get, qq_id)
    if record is None:
        return f"[{qq_id}] 未绑定账号，跳过。"

    valid = await check_cred(record.cred)
    if not valid:
        return f"[{qq_id}] 凭证已失效，请重新绑定。"

    try:
        bindings = await get_binding_list(record.cred)
    except SklandAPIError as e:
        return f"[{qq_id}] 获取角色列表失败：{e}"

    if not bindings:
        return f"[{qq_id}] 未找到绑定的明日方舟角色。"

    results = []
    for b in bindings:
        uid = b["uid"]
        nick = b["nick_name"] or uid
        gid = b["channel_master_id"]
        try:
            res = await do_attendance(record.cred, uid, gid)
        except SklandAPIError as e:
            results.append(f"  {nick}：签到失败 — {e}")
            continue
        if res["already_signed"]:
            results.append(f"  {nick}：今日已签到 ✓")
        else:
            awards = "、".join(
                f"{r.get('name', '')}×{r.get('count', 0)}"
                for r in res["rewards"]
            ) or "无奖励信息"
            results.append(f"  {nick}：签到成功！获得 {awards}")

    return "\n".join(results)


@register("shurosti_bot", "iTea", "黍饼Bot — 森空岛数据查询插件", "1.2.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._db = TokenDatabase(_DB_PATH)
        self._scheduler_task: asyncio.Task | None = None

    async def initialize(self):
        self._scheduler_task = asyncio.create_task(self._daily_sign_scheduler())

    async def terminate(self):
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    def _sender_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_sender_id())

    async def _daily_sign_scheduler(self):
        while True:
            now = time.localtime()
            target_h, target_m = _SIGN_HOUR, _SIGN_MINUTE
            seconds_until = (
                (target_h - now.tm_hour) * 3600
                + (target_m - now.tm_min) * 60
                - now.tm_sec
            )
            if seconds_until <= 0:
                seconds_until += 86400
            await asyncio.sleep(seconds_until)
            await self._run_all_auto_sign()

    async def _run_all_auto_sign(self):
        qq_ids = await asyncio.to_thread(self._db.all_auto_sign_qq_ids)
        for qq_id in qq_ids:
            try:
                await _do_sign_for_user(self._db, qq_id)
            except Exception as e:
                self.context.logger.error(f"用户{qq_id}自动签到失败：{e}")

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
                "登录（密码，建议私聊）：\n  /skland登录 手机号 密码\n\n"
                "绑定/登录（验证码）：\n"
                "  第一步：/skland绑定手机号 手机号\n"
                "  第二步：/skland验证码 验证码\n\n"
                "查询绑定状态：\n  /skland状态\n\n"
                "解除绑定：\n  /skland解绑\n\n"
                "自动签到：\n  /开启自动签到\n  /关闭自动签到\n\n"
                "查询本月签到奖励：\n  /查阅本月签到奖励\n\n"
                "本帮助：\n  /skland帮助"
            )
            event.stop_event()
            return

        if cmd == "skland状态":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 你尚未绑定森空岛账号。\n{_BIND_HELP}")
                event.stop_event()
                return
            valid = await check_cred(record.cred)
            update_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.updated_at))
            status_icon = "✅ 有效" if valid else "❌ 已失效（请重新绑定）"
            auto_on = await asyncio.to_thread(self._db.get_auto_sign, qq_id)
            auto_status = "开启" if auto_on else "关闭"
            yield event.plain_result(
                f"📋 森空岛绑定信息\n"
                f"森空岛用户 ID：{record.skland_user_id}\n"
                f"手机号：{record.phone[:3]}****{record.phone[-4:] if len(record.phone) >= 4 else record.phone}\n"
                f"凭证状态：{status_icon}\n"
                f"自动签到：{auto_status}\n"
                f"最后更新：{update_time}"
            )
            event.stop_event()
            return

        if cmd == "skland解绑":
            deleted = await asyncio.to_thread(self._db.delete, qq_id)
            if deleted:
                await asyncio.to_thread(self._db.set_auto_sign, qq_id, False)
                yield event.plain_result("✅ 已成功解除森空岛账号绑定，本地凭证已删除。")
            else:
                yield event.plain_result("❌ 你尚未绑定森空岛账号。")
            event.stop_event()
            return

        if cmd == "skland登录":
            if _is_group_message(event):
                yield event.plain_result(
                    "⚠️⚠️⚠️ 严重警告：请勿在群聊中发送手机号/密码等隐私信息！\n"
                    "为了你的账号安全，/skland登录 仅支持私聊使用，请私信 Bot 后重试。"
                )
                event.stop_event()
                return
            if len(args) < 2:
                yield event.plain_result("用法：/skland登录 手机号 密码")
                event.stop_event()
                return
            phone, password = args[0], args[1]
            try:
                result = await login_with_password(phone, password)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 登录失败：{e}")
                event.stop_event()
                return
            await asyncio.to_thread(
                self._db.upsert,
                qq_id=qq_id,
                cred=result["cred"],
                token=result["token"],
                skland_user_id=result["user_id"],
                phone=phone,
                updated_at=int(time.time()),
            )
            await asyncio.to_thread(self._db.delete_pending_phone, qq_id)
            yield event.plain_result(
                f"✅ 登录成功！\n森空岛用户 ID：{result['user_id']}\n"
                "凭证已安全保存，请勿将凭证告知他人。"
            )
            event.stop_event()
            return

        if cmd == "skland绑定手机号":
            if len(args) < 1:
                yield event.plain_result("用法：/skland绑定手机号 手机号")
                event.stop_event()
                return
            phone = args[0]
            await asyncio.to_thread(self._db.set_pending_phone, qq_id, phone, int(time.time()))
            try:
                await send_phone_code(phone)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 发送失败：{e}")
                event.stop_event()
                return
            yield event.plain_result(
                f"📱 验证码已发送至 {phone[:3]}****{phone[-4:]}。\n"
                "请继续发送：/skland验证码 验证码"
            )
            event.stop_event()
            return

        if cmd == "skland验证码":
            if len(args) < 1:
                yield event.plain_result("用法：/skland验证码 验证码")
                event.stop_event()
                return
            pending = await asyncio.to_thread(self._db.get_pending_phone, qq_id)
            if pending is None:
                yield event.plain_result("未找到已绑定的手机号，请先使用：/skland绑定手机号 手机号")
                event.stop_event()
                return
            phone, _ = pending
            sms_code = args[0]
            try:
                result = await login_with_code(phone, sms_code)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 登录失败：{e}")
                event.stop_event()
                return
            await asyncio.to_thread(
                self._db.upsert,
                qq_id=qq_id,
                cred=result["cred"],
                token=result["token"],
                skland_user_id=result["user_id"],
                phone=phone,
                updated_at=int(time.time()),
            )
            await asyncio.to_thread(self._db.delete_pending_phone, qq_id)
            yield event.plain_result(
                f"✅ 绑定成功！\n森空岛用户 ID：{result['user_id']}\n"
                "凭证已安全保存，请勿将凭证告知他人。"
            )
            event.stop_event()
            return

        if cmd == "开启自动签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{_BIND_HELP}")
                event.stop_event()
                return
            await asyncio.to_thread(self._db.set_auto_sign, qq_id, True)
            yield event.plain_result("⏰ 已开启自动签到！立即执行一次签到中…")

            sign_result = await _do_sign_for_user(self._db, qq_id)
            yield event.plain_result(f"📝 签到结果：\n{sign_result}")
            event.stop_event()
            return

        if cmd == "关闭自动签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{_BIND_HELP}")
                event.stop_event()
                return
            await asyncio.to_thread(self._db.set_auto_sign, qq_id, False)
            yield event.plain_result("✅ 已关闭自动签到。")
            event.stop_event()
            return

        if cmd == "查阅本月签到奖励":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{_BIND_HELP}")
                event.stop_event()
                return

            valid = await check_cred(record.cred)
            if not valid:
                yield event.plain_result("❌ 凭证已失效，请重新绑定后使用。")
                event.stop_event()
                return

            cached = cached_image_path(qq_id)
            if cached is not None:
                yield event.image_result(cached)
                event.stop_event()
                return

            try:
                bindings = await get_binding_list(record.cred)
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 获取角色列表失败：{e}")
                event.stop_event()
                return

            if not bindings:
                yield event.plain_result("❌ 未找到绑定的明日方舟角色。")
                event.stop_event()
                return

            default_binding = next((b for b in bindings if b["is_default"]), bindings[0])
            try:
                sign_list = await get_monthly_rewards(
                    record.cred,
                    default_binding["uid"],
                    default_binding["channel_master_id"],
                )
            except SklandAPIError as e:
                yield event.plain_result(f"❌ 获取签到奖励失败：{e}")
                event.stop_event()
                return

            img_path = generate_monthly_image(sign_list, qq_id)
            if img_path is not None:
                yield event.image_result(img_path)
            else:
                yield event.plain_result(format_rewards_text(sign_list))
            event.stop_event()
            return
