import asyncio
import logging
import os
import re
import shutil
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
        bindings = await get_binding_list(record.cred)
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
        gid = b.get("channel_master_id", "1")
        _plugin_logger.info(f"[sign] [{qq_id}] 正在签到角色 nick={nick} uid={uid}")
        try:
            res = await do_attendance(record.cred, uid, gid)
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


@register("shurosti_bot", "iTea", "黍饼Bot — 森空岛数据查询插件", "1.0.13")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self._config = config
        self._data_dir = StarTools.get_data_dir("shurosti_bot")
        self._img_dir = str(self._data_dir / "sign_images")
        self._log_dir = str(self._data_dir / "logs")
        setup_file_logger(self._log_dir)
        _plugin_logger.info(f"[init] 插件初始化，数据目录：{self._data_dir}")
        self._migrate_old_data()
        self._db = TokenDatabase(str(self._data_dir / "tokens.db"))
        self._scheduler_task: asyncio.Task | None = None

    def _migrate_old_data(self) -> None:
        old_db_path = os.path.join(os.path.dirname(__file__), "data", "tokens.db")
        new_db_path = str(self._data_dir / "tokens.db")
        if os.path.exists(old_db_path) and not os.path.exists(new_db_path):
            os.makedirs(os.path.dirname(new_db_path), exist_ok=True)
            shutil.copy2(old_db_path, new_db_path)
        old_img_dir = os.path.join(os.path.dirname(__file__), "data", "sign_images")
        if os.path.exists(old_img_dir) and not os.path.exists(self._img_dir):
            os.makedirs(os.path.dirname(self._img_dir), exist_ok=True)
            for f in os.listdir(old_img_dir):
                src = os.path.join(old_img_dir, f)
                dst = os.path.join(self._img_dir, f)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

    @property
    def _bot_name(self) -> str:
        try:
            return self._config.get("bot_name", "森空岛bot") or "森空岛bot"
        except Exception:
            return "森空岛bot"

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
        _plugin_logger.info(f"[auto_sign] 开始批量自动签到，共 {len(qq_ids)} 个用户")
        for qq_id in qq_ids:
            try:
                await _do_sign_for_user(self._db, qq_id)
            except Exception as e:
                _plugin_logger.error(f"[auto_sign] 用户 {qq_id} 自动签到异常：{e}", exc_info=True)

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

        bot_name = self._bot_name
        cmd, args = _extract(event.message_str or "", bot_name)
        if cmd is None:
            return

        qq_id = self._sender_id(event)

        bind_help = (
            f"绑定{bot_name}账号用法：\n"
            f"  密码登录（建议私聊）：/{bot_name}登录 手机号 密码\n"
            f"  验证码登录：\n"
            f"    第一步：/{bot_name}绑定手机号 手机号\n"
            f"    第二步：/{bot_name}验证码 验证码"
        )

        if cmd == f"{bot_name}帮助":
            yield event.plain_result(
                f"🗂 {bot_name} 可用命令\n"
                f"/{bot_name}登录 手机号 密码      — 密码登录（建议私聊）\n"
                f"/{bot_name}绑定手机号 手机号      — 验证码登录第一步\n"
                f"/{bot_name}验证码 验证码          — 验证码登录第二步\n"
                f"/{bot_name}状态                  — 查看绑定状态\n"
                f"/{bot_name}解绑                  — 解除账号绑定\n"
                f"/{bot_name}签到                  — 立即手动签到一次\n"
                f"/开启自动签到                     — 开启每日自动签到\n"
                f"/关闭自动签到                     — 关闭每日自动签到\n"
                f"/查阅本月签到奖励                 — 查看本月签到奖励\n"
                f"/{bot_name}帮助                  — 显示此帮助\n"
                f"/{bot_name}详细帮助              — 显示详细说明"
            )
            event.stop_event()
            return

        if cmd == f"{bot_name}详细帮助":
            yield event.plain_result(
                f"📖 {bot_name} 详细帮助\n"
                "\n"
                f"【/{bot_name}登录 手机号 密码】\n"
                "使用手机号和密码登录森空岛账号，登录成功后自动保存凭证。\n"
                "⚠️ 含有隐私信息，请务必在私聊中使用，群聊中发送将被拒绝。\n"
                "\n"
                f"【/{bot_name}绑定手机号 手机号】\n"
                "验证码登录的第一步，向指定手机号发送短信验证码。\n"
                "收到验证码后，继续使用下方指令完成绑定。\n"
                "\n"
                f"【/{bot_name}验证码 验证码】\n"
                "验证码登录的第二步，输入收到的短信验证码完成账号绑定。\n"
                f"请确保已先执行 /{bot_name}绑定手机号。\n"
                "\n"
                f"【/{bot_name}状态】\n"
                "查看当前绑定的森空岛账号信息，包括用户ID、手机号（脱敏）、\n"
                "凭证有效性以及自动签到开关状态。\n"
                "\n"
                f"【/{bot_name}解绑】\n"
                "解除当前账号与Bot的绑定，本地保存的凭证将被彻底删除。\n"
                "解绑后自动签到也将同步关闭。\n"
                "\n"
                f"【/{bot_name}签到】\n"
                "立即手动触发一次森空岛签到，适用于不想等待自动签到的情况。\n"
                "\n"
                f"【/开启自动签到】\n"
                "开启每日自动签到功能，Bot 将在每天早上 6:00 自动完成签到。\n"
                "开启后会立即执行一次签到以确认配置正常。\n"
                "\n"
                "【/关闭自动签到】\n"
                "关闭每日自动签到功能，之后每天不再自动执行签到。\n"
                "\n"
                "【/查阅本月签到奖励】\n"
                "查询明日方舟森空岛本月签到奖励列表，优先以图片形式展示，\n"
                "若图片生成失败则以文字形式返回。"
            )
            event.stop_event()
            return

        if cmd == f"{bot_name}状态":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 你尚未绑定森空岛账号。\n{bind_help}")
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

        if cmd == f"{bot_name}解绑":
            deleted = await asyncio.to_thread(self._db.delete, qq_id)
            if deleted:
                await asyncio.to_thread(self._db.set_auto_sign, qq_id, False)
                yield event.plain_result("✅ 已成功解除森空岛账号绑定，本地凭证已删除。")
            else:
                yield event.plain_result("❌ 你尚未绑定森空岛账号。")
            event.stop_event()
            return

        if cmd == f"{bot_name}登录":
            if _is_group_message(event):
                yield event.plain_result(
                    "⚠️⚠️⚠️ 严重警告：请勿在群聊中发送手机号/密码等隐私信息！\n"
                    f"为了你的账号安全，/{bot_name}登录 仅支持私聊使用，请私信 Bot 后重试。"
                )
                event.stop_event()
                return
            if len(args) < 2:
                yield event.plain_result(f"用法：/{bot_name}登录 手机号 密码")
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

        if cmd == f"{bot_name}绑定手机号":
            if len(args) < 1:
                yield event.plain_result(f"用法：/{bot_name}绑定手机号 手机号")
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
                f"请继续发送：/{bot_name}验证码 验证码"
            )
            event.stop_event()
            return

        if cmd == f"{bot_name}验证码":
            if len(args) < 1:
                yield event.plain_result(f"用法：/{bot_name}验证码 验证码")
                event.stop_event()
                return
            pending = await asyncio.to_thread(self._db.get_pending_phone, qq_id)
            if pending is None:
                yield event.plain_result(f"未找到已绑定的手机号，请先使用：/{bot_name}绑定手机号 手机号")
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

        if cmd == f"{bot_name}签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{bind_help}")
                event.stop_event()
                return
            _plugin_logger.info(f"[manual_sign] 用户 {qq_id} 触发手动签到")
            yield event.plain_result("⏳ 正在签到，请稍候…")
            sign_result = await _do_sign_for_user(self._db, qq_id)
            yield event.plain_result(f"📝 签到结果：\n{sign_result}")
            event.stop_event()
            return

        if cmd == "开启自动签到":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{bind_help}")
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
                yield event.plain_result(f"❌ 请先绑定账号。\n{bind_help}")
                event.stop_event()
                return
            await asyncio.to_thread(self._db.set_auto_sign, qq_id, False)
            yield event.plain_result("✅ 已关闭自动签到。")
            event.stop_event()
            return

        if cmd == "查阅本月签到奖励":
            record = await asyncio.to_thread(self._db.get, qq_id)
            if record is None:
                yield event.plain_result(f"❌ 请先绑定账号。\n{bind_help}")
                event.stop_event()
                return

            valid = await check_cred(record.cred)
            if not valid:
                yield event.plain_result("❌ 凭证已失效，请重新绑定后使用。")
                event.stop_event()
                return

            cached = cached_image_path(qq_id, self._img_dir)
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

            img_path = generate_monthly_image(sign_list, qq_id, self._img_dir)
            if img_path is not None:
                yield event.image_result(img_path)
            else:
                yield event.plain_result(format_rewards_text(sign_list))
            event.stop_event()
            return
