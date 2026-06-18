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
        gid = b.get("channel_master_id", "1")
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


@register("shurosti_bot", "iTea", "黍饼Bot — 森空岛数据查询插件", "1.0.14")
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
        self._