"""
临时脚本：填写自测报告 xlsx
直接操作 xlsx zip 内部 sharedStrings.xml 和 sheet1.xml，无需第三方库。
"""
import io
import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

SRC = r"d:/project/astrbot_plugin_ShuRosti_Bot/机器人自测报告模板-2023.xlsx"
DST = r"d:/project/astrbot_plugin_ShuRosti_Bot/机器人自测报告-黍饼Bot.xlsx"

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)

# ────────────────────────────────────────────────
# 填写内容
# ────────────────────────────────────────────────

BOT_INFO = {
    "名称": "黍饼Bot",
    "介绍": "明日方舟森空岛数据查询插件，支持账号绑定、自动签到、查询签到奖励。",
    "机器人QQ号": "（待填写）",
    "BotAppID": "（待填写）",
    "主体名称": "（待填写）",
}

# 指令面板-服务配置（功能型）
SERVICE_ROWS = [
    ("自动签到", "每日06:00自动为开启用户执行森空岛签到", "是", "需先绑定账号并执行/开启自动签到"),
]

# 指令面板-指令配置
CMD_ROWS = [
    ("/skland帮助",         "回复全部可用命令说明",                                 "是", ""),
    ("/skland登录",         "密码登录绑定森空岛账号，仅限私聊",                     "是", "群聊触发时回复严重警告并拒绝执行"),
    ("/skland绑定手机号",   "记录手机号并向其发送短信验证码",                       "是", ""),
    ("/skland验证码",       "使用验证码完成森空岛账号绑定",                         "是", "需先执行/skland绑定手机号"),
    ("/skland状态",         "查询当前绑定账号信息及凭证有效性",                     "是", "显示用户ID、手机号（脱敏）、凭证状态、自动签到开关"),
    ("/skland解绑",         "解除当前账号绑定并删除本地凭证",                       "是", "同时关闭自动签到"),
    ("/开启自动签到",       "开启自动签到并立即执行一次签到，回报签到奖励",         "是", "需先绑定账号"),
    ("/关闭自动签到",       "关闭自动签到，不再参与每日定时签到",                   "是", ""),
    ("/查阅本月签到奖励",   "查询本月每日签到奖励列表，优先以图片回复",             "是", "有Pillow时生成图片，每月缓存一张；无Pillow时文字列表"),
]

# 快捷菜单
MENU_ROWS = [
    ("/skland帮助",       "指令", "回复全部可用命令说明",       "是", ""),
    ("/开启自动签到",     "指令", "开启自动签到并立即签一次",   "是", ""),
    ("/查阅本月签到奖励", "指令", "图片/文字展示本月签到奖励",  "是", ""),
]

# 三、其他功能
OTHER_ROWS = [
    ("图片生成（sign_image.py）", "用Pillow绘制本月签到奖励卡片，每月仅生成一次并缓存", "是", "无Pillow时自动降级为文字回复"),
    ("数美dId设备指纹",           "模拟浏览器指纹获取dId以通过鹰角登录防护",            "是", "cryptography库不可用时回落固定值"),
    ("凭证有效性校验",            "调用/api/v1/user/check实时校验cred是否有效",          "是", ""),
]

# ────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────

def _q(tag):
    return f"{{{NS}}}{tag}"


def _read_zip(zin, name):
    with zin.open(name) as f:
        return f.read()


def _build_shared_strings(strings: list[str]) -> bytes:
    root = ET.Element(_q("sst"))
    root.set("xmlns", NS)
    root.set("count", str(len(strings)))
    root.set("uniqueCount", str(len(strings)))
    for s in strings:
        si = ET.SubElement(root, _q("si"))
        t = ET.SubElement(si, _q("t"))
        t.text = s
        if s and (s[0] == " " or s[-1] == " " or "\n" in s):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return ET.tostring(root, encoding="unicode", xml_declaration=False).encode("utf-8")


def _cell_ref(col: int, row: int) -> str:
    letters = ""
    c = col
    while c > 0:
        c, r = divmod(c - 1, 26)
        letters = chr(65 + r) + letters
    return f"{letters}{row}"


def _build_sheet(data: list[list]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{NS}">',
        "<sheetData>",
    ]
    for ri, row_vals in enumerate(data, start=1):
        if not any(v is not None and v != "" for v in row_vals):
            continue
        lines.append(f'<row r="{ri}">')
        for ci, val in enumerate(row_vals, start=1):
            if val is None or val == "":
                continue
            ref = _cell_ref(ci, ri)
            text = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            lines.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        lines.append("</row>")
    lines += ["</sheetData>", "</worksheet>"]
    return "\n".join(lines).encode("utf-8")


# ────────────────────────────────────────────────
# 组装表格数据（按模板行结构）
# ────────────────────────────────────────────────

def build_data() -> list[list]:
    rows = []

    def R(*cells):
        rows.append(list(cells))

    R("一、机器人基本信息")
    R("名称", "介绍", "机器人QQ号", "BotAppID", "主体名称")
    R(BOT_INFO["名称"], BOT_INFO["介绍"], BOT_INFO["机器人QQ号"], BOT_INFO["BotAppID"], BOT_INFO["主体名称"])
    R()
    R("二、机器人功能配置测试详情")
    R()

    R("指令面板-服务配置")
    R("功能名称", "预期输出", "是否已自测", "服务特殊说明", "关联小程序链接")
    for row in SERVICE_ROWS:
        R(*row, "")
    R()

    R("指令面板-指令配置")
    R("指令名称", "预期输出", "是否已自测", "指令特殊说明")
    for row in CMD_ROWS:
        R(*row)
    R()

    R("快捷菜单")
    R("功能/指令名称", "类型（功能/指令）", "预期输出", "是否已自测", "特殊说明", "关联小程序链接")
    for row in MENU_ROWS:
        R(*row, "")
    R()

    R("三、其他功能")
    R()
    R("功能名称", "预期输出", "是否已自测", "服务特殊说明")
    for row in OTHER_ROWS:
        R(*row)
    R()
    R("备注：为尽快完成审核，开发者可对部分功能配置、指令进行解释说明，如无相关配置则对应部分可留空")

    return rows


# ────────────────────────────────────────────────
# 写文件
# ────────────────────────────────────────────────

def main():
    data = build_data()
    sheet_xml = _build_sheet(data)

    buf = io.BytesIO()
    with zipfile.ZipFile(SRC, "r") as zin:
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/worksheets/sheet1.xml":
                    zout.writestr(item, sheet_xml)
                elif item.filename == "xl/sharedStrings.xml":
                    pass  # 使用 inlineStr，不再需要 sharedStrings
                else:
                    zout.writestr(item, _read_zip(zin, item.filename))

    with open(DST, "wb") as f:
        f.write(buf.getvalue())
    print("Done:", DST)


if __name__ == "__main__":
    main()
