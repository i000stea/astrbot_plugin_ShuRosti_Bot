import asyncio
import base64
import gzip
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import aiohttp

logger = logging.getLogger("astrbot_plugin_ShuRosti_Bot")


def setup_file_logger(log_dir: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "shurosti_bot.log")
    if any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(log_path)
           for h in logger.handlers):
        return
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)

_HG_BASE = "https://as.hypergryph.com"
_SK_BASE = "https://zonai.skland.com"
_SM_URL = "https://fp-it.portal101.cn/deviceprofile/v4"

_SM_ORG = "UWXspnCCJN4sfYlNfqps"
_SM_PUB = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPix"
    "oinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8m"
    "N28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjv"
    "g0iYWRByfRsK2gdl7llqCwIDAQAB"
)

_DES_RULE = {
    "appId":       {"cipher": "DES", "is_encrypt": 1, "key": "uy7mzc4h", "ob": "xx"},
    "box":         {"is_encrypt": 0, "ob": "jf"},
    "canvas":      {"cipher": "DES", "is_encrypt": 1, "key": "snrn887t", "ob": "yk"},
    "clientSize":  {"cipher": "DES", "is_encrypt": 1, "key": "cpmjjgsu", "ob": "zx"},
    "organization":{"cipher": "DES", "is_encrypt": 1, "key": "78moqjfc", "ob": "dp"},
    "os":          {"cipher": "DES", "is_encrypt": 1, "key": "je6vk6t4", "ob": "pj"},
    "platform":    {"cipher": "DES", "is_encrypt": 1, "key": "pakxhcd2", "ob": "gm"},
    "plugins":     {"cipher": "DES", "is_encrypt": 1, "key": "v51m3pzl", "ob": "kq"},
    "pmf":         {"cipher": "DES", "is_encrypt": 1, "key": "2mdeslu3", "ob": "vw"},
    "protocol":    {"is_encrypt": 0, "ob": "protocol"},
    "referer":     {"cipher": "DES", "is_encrypt": 1, "key": "y7bmrjlc", "ob": "ab"},
    "res":         {"cipher": "DES", "is_encrypt": 1, "key": "whxqm2a7", "ob": "hf"},
    "rtype":       {"cipher": "DES", "is_encrypt": 1, "key": "x8o2h2bl", "ob": "lo"},
    "sdkver":      {"cipher": "DES", "is_encrypt": 1, "key": "9q3dcxp2", "ob": "sc"},
    "status":      {"cipher": "DES", "is_encrypt": 1, "key": "2jbrxxw4", "ob": "an"},
    "subVersion":  {"cipher": "DES", "is_encrypt": 1, "key": "eo3i2puh", "ob": "ns"},
    "svm":         {"cipher": "DES", "is_encrypt": 1, "key": "fzj3kaeh", "ob": "qr"},
    "time":        {"cipher": "DES", "is_encrypt": 1, "key": "q2t3odsk", "ob": "nb"},
    "timezone":    {"cipher": "DES", "is_encrypt": 1, "key": "1uv05lj5", "ob": "as"},
    "tn":          {"cipher": "DES", "is_encrypt": 1, "key": "x9nzj1bp", "ob": "py"},
    "trees":       {"cipher": "DES", "is_encrypt": 1, "key": "acfs0xo4", "ob": "pi"},
    "ua":          {"cipher": "DES", "is_encrypt": 1, "key": "k92crp1t", "ob": "bj"},
    "url":         {"cipher": "DES", "is_encrypt": 1, "key": "y95hjkoo", "ob": "cf"},
    "version":     {"is_encrypt": 0, "ob": "version"},
    "vpw":         {"cipher": "DES", "is_encrypt": 1, "key": "r9924ab5", "ob": "ca"},
    "smid":        {"cipher": "DES", "is_encrypt": 1, "key": "j5rvclaq", "ob": "sm"},
}

_BROWSER_ENV = {
    "plugins": "MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,"
               "MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "canvas": "259ffe69",
    "timezone": -480,
    "platform": "Win32",
    "url": "https://www.skland.com/",
    "referer": "",
    "res": "1920_1080_24_1.25",
    "clientSize": "0_0_1080_1920_1920_1080_1920_1080",
    "status": "0011",
}

_APP_CODE = "4ca99fa6b56cc2ba"

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0",
}


class SklandAPIError(Exception):
    pass


def _try_import_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES, AES
        from cryptography.hazmat.primitives.ciphers.base import Cipher
        from cryptography.hazmat.primitives.ciphers.modes import CBC, ECB
        return serialization, asym_padding, TripleDES, AES, Cipher, CBC, ECB
    except ImportError:
        return None


def _des_encrypt(value: str, key: str) -> str:
    crypto = _try_import_crypto()
    if crypto is None:
        return base64.b64encode(value.encode("utf-8")).decode("utf-8")
    _, _, TripleDES, _, Cipher, _, ECB = crypto
    data = value.encode("utf-8")
    data += b"\x00" * 8
    c = Cipher(TripleDES(key.encode("utf-8")), ECB())
    return base64.b64encode(c.encryptor().update(data)).decode("utf-8")


def _apply_des_rule(obj: dict) -> dict:
    result = {}
    for k, v in obj.items():
        rule = _DES_RULE.get(k)
        if rule is None:
            result[k] = v
            continue
        ob = rule["ob"]
        if rule["is_encrypt"] == 1:
            result[ob] = _des_encrypt(str(v), rule["key"])
        else:
            result[ob] = v
    return result


def _aes_encrypt(data: bytes, key: bytes) -> str:
    crypto = _try_import_crypto()
    if crypto is None:
        return base64.b64encode(data).decode("utf-8")
    _, _, _, AES, Cipher, CBC, _ = crypto
    iv = b"0102030405060708"
    data += b"\x00"
    while len(data) % 16 != 0:
        data += b"\x00"
    c = Cipher(AES(key), CBC(iv))
    return c.encryptor().update(data).hex()


def _gzip_b64(obj: dict) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, compresslevel=2, mtime=0))


def _get_tn(obj: dict) -> str:
    parts = []
    for k in sorted(obj.keys()):
        v = obj[k]
        if isinstance(v, (int, float)):
            parts.append(str(v * 10000))
        elif isinstance(v, dict):
            parts.append(_get_tn(v))
        else:
            parts.append(str(v))
    return "".join(parts)


def _get_smid() -> str:
    t = time.localtime()
    ts = "{}{:0>2d}{:0>2d}{:0>2d}{:0>2d}{:0>2d}".format(
        t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec
    )
    uid = str(uuid.uuid4())
    v = ts + hashlib.md5(uid.encode("utf-8")).hexdigest() + "00"
    smsk = hashlib.md5(("smsk_web_" + v).encode("utf-8")).hexdigest()[:14]
    return v + smsk + "0"


def _get_fallback_did() -> str:
    return "de9759a5afaa634f"


def _generate_sign(token: str, path: str, body_or_query: str) -> tuple[str, dict]:
    t = str(int(time.time()) - 2)
    header_ca = {"platform": "", "timestamp": t, "dId": "", "vName": ""}
    header_ca_str = json.dumps(header_ca, separators=(",", ":"))
    s = path + body_or_query + t + header_ca_str
    hex_s = hmac.new(token.encode("utf-8"), s.encode("utf-8"), hashlib.sha256).hexdigest()
    sign = hashlib.md5(hex_s.encode("utf-8")).hexdigest()
    return sign, header_ca


async def _get_did() -> str:
    crypto = _try_import_crypto()
    if crypto is None:
        logger.warning("[_get_did] cryptography 未安装，使用回退 DID")
        return _get_fallback_did()

    serialization, asym_padding, _, _, _, _, _ = crypto

    try:
        pub = serialization.load_der_public_key(base64.b64decode(_SM_PUB))
        uid_bytes = str(uuid.uuid4()).encode("utf-8")
        pri_id = hashlib.md5(uid_bytes).hexdigest()[:16]
        ep = base64.b64encode(pub.encrypt(uid_bytes, asym_padding.PKCS1v15())).decode("utf-8")

        now_ms = int(time.time() * 1000)
        target = {
            **_BROWSER_ENV,
            "protocol": 102,
            "organization": _SM_ORG,
            "appId": "default",
            "os": "web",
            "version": "3.0.0",
            "sdkver": "3.0.0",
            "box": "",
            "rtype": "all",
            "smid": _get_smid(),
            "subVersion": "1.0.0",
            "time": 0,
            "vpw": str(uuid.uuid4()),
            "svm": now_ms,
            "trees": str(uuid.uuid4()),
            "pmf": now_ms,
        }
        target["tn"] = hashlib.md5(_get_tn(target).encode("utf-8")).hexdigest()

        des_result = _aes_encrypt(_gzip_b64(_apply_des_rule(target)), pri_id.encode("utf-8"))

        async with aiohttp.ClientSession() as session:
            async with session.post(
                _SM_URL,
                json={
                    "appId": "default",
                    "compress": 2,
                    "data": des_result,
                    "encode": 5,
                    "ep": ep,
                    "organization": _SM_ORG,
                    "os": "web",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json(content_type=None)
                logger.info(f"[_get_did] 响应码={resp.status} body={body}")
                if body.get("code") == 1100:
                    return "B" + body["detail"]["deviceId"]
    except Exception as e:
        logger.error(f"[_get_did] 异常: {e}")
        pass

    return _get_fallback_did()


async def _hg_post(path: str, payload: dict, did: str) -> dict:
    headers = {**_HEADERS, "dId": did}
    url = _HG_BASE + path
    logger.info(f"[hg_post] 请求: {url} payload={payload}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[hg_post] HTTP状态码: {resp.status}")
                body = await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[hg_post] 网络请求失败: {url} 错误={e}")
        raise SklandAPIError(f"网络请求失败：{e}") from e
    logger.info(f"[hg_post] 响应: {url} body={body}")
    if body.get("status") != 0:
        raise SklandAPIError(body.get("msg") or body.get("message") or str(body))
    return body.get("data", {})


async def _sk_post(path: str, payload: dict, cred: str | None = None, token: str | None = None) -> dict:
    headers = {**_HEADERS}
    if cred:
        headers["cred"] = cred
    if token:
        sign, header_ca = _generate_sign(token, path, json.dumps(payload, separators=(",", ":")))
        headers["sign"] = sign
        headers.update(header_ca)
    url = _SK_BASE + path
    logger.info(f"[sk_post] 请求: {url} payload={payload}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[sk_post] HTTP状态码: {resp.status}")
                body = await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[sk_post] 网络请求失败: {url} 错误={e}")
        raise SklandAPIError(f"网络请求失败：{e}") from e
    logger.info(f"[sk_post] 响应: {url} body={body}")
    if resp.status == 401 or body.get("code") == 10000:
        raise SklandAPIError("凭证已失效或请求异常，请重新绑定账号")
    if body.get("code") != 0:
        raise SklandAPIError(body.get("message") or str(body))
    return body.get("data", {})


async def _get_oauth_code(hg_token: str, did: str) -> str:
    data = await _hg_post(
        "/user/oauth2/v2/grant",
        {"token": hg_token, "appCode": _APP_CODE, "type": 0},
        did,
    )
    code = data.get("code")
    if not code:
        raise SklandAPIError("获取 OAuth2 授权码失败，响应中缺少 code 字段")
    return code


async def _get_cred_by_code(oauth_code: str) -> dict:
    data = await _sk_post(
        "/api/v1/user/auth/generate_cred_by_code",
        {"kind": 1, "code": oauth_code},
    )
    cred = data.get("cred")
    user_id = data.get("userId", "")
    token = data.get("token", "")
    if not cred:
        raise SklandAPIError("获取森空岛 cred 失败，响应中缺少 cred 字段")
    return {"cred": cred, "token": token, "user_id": user_id}


async def send_phone_code(phone: str) -> None:
    did = await _get_did()
    await _hg_post(
        "/general/v1/send_phone_code",
        {"phone": phone, "type": 2},
        did,
    )


async def login_with_password(phone: str, password: str) -> dict:
    logger.info(f"[login_with_password] 开始密码登录 phone={phone[:3]}****{phone[-4:]}")
    did = await _get_did()
    data = await _hg_post(
        "/user/auth/v1/token_by_phone_password",
        {"phone": phone, "password": password},
        did,
    )
    hg_token = data.get("token")
    if not hg_token:
        raise SklandAPIError("密码登录失败，未获取到鹰角 token")
    oauth_code = await _get_oauth_code(hg_token, did)
    logger.info(f"[login_with_password] 密码登录成功 phone={phone[:3]}****{phone[-4:]}")
    return await _get_cred_by_code(oauth_code)


async def login_with_code(phone: str, sms_code: str) -> dict:
    logger.info(f"[login_with_code] 开始验证码登录 phone={phone[:3]}****{phone[-4:]}")
    did = await _get_did()
    data = await _hg_post(
        "/user/auth/v2/token_by_phone_code",
        {"phone": phone, "code": sms_code},
        did,
    )
    hg_token = data.get("token")
    if not hg_token:
        raise SklandAPIError("验证码登录失败，未获取到鹰角 token")
    oauth_code = await _get_oauth_code(hg_token, did)
    logger.info(f"[login_with_code] 验证码登录成功 phone={phone[:3]}****{phone[-4:]}")
    return await _get_cred_by_code(oauth_code)


async def check_cred(cred: str) -> bool:
    headers = {**_HEADERS, "cred": cred}
    logger.info(f"[check_cred] 检查 cred 有效性")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _SK_BASE + "/api/v1/user/check",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                logger.info(f"[check_cred] HTTP状态码: {resp.status}")
                body = await resp.json(content_type=None)
        logger.info(f"[check_cred] 响应: code={body.get('code')}")
        if resp.status == 401:
            return False
        return resp.status == 200 and body.get("code") == 0
    except Exception as e:
        logger.error(f"[check_cred] 请求失败: {e}")
        return False


async def _sk_get(path: str, params: dict | None, cred: str, token: str | None = None) -> dict:
    headers = {**_HEADERS, "cred": cred}
    if token:
        from urllib.parse import urlencode
        query_str = urlencode(params) if params else ""
        sign, header_ca = _generate_sign(token, path, query_str)
        headers["sign"] = sign
        headers.update(header_ca)
    url = _SK_BASE + path
    logger.info(f"[sk_get] 请求: {url} params={params}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[sk_get] HTTP状态码: {resp.status}")
                body = await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[sk_get] 网络请求失败: {url} 错误={e}")
        raise SklandAPIError(f"网络请求失败：{e}") from e
    logger.info(f"[sk_get] 响应: {url} body={body}")
    if resp.status == 401 or body.get("code") == 10000:
        raise SklandAPIError("凭证已失效或请求异常，请重新绑定账号")
    if body.get("code") != 0:
        raise SklandAPIError(body.get("message") or str(body))
    return body.get("data", {})


async def get_binding_list(cred: str, token: str | None = None) -> list[dict]:
    data = await _sk_get("/api/v1/game/player/binding", None, cred, token)
    logger.info(f"[get_binding_list] 原始数据: {data}")
    result = []
    for game in data.get("list", []):
        if game.get("appCode") != "arknights":
            continue
        for binding in game.get("bindingList", []):
            if not binding.get("isDelete", False):
                result.append({
                    "uid": binding["uid"],
                    "nick_name": binding.get("nickName", ""),
                    "channel_master_id": binding.get("channelMasterId", "1"),
                    "channel_name": binding.get("channelName", "官服"),
                    "is_default": binding.get("isDefault", False),
                    "game_id": str(binding.get("gameId", 1)),
                })
    logger.info(f"[get_binding_list] 提取结果: {result}")
    return result


_ALREADY_SIGNED_KEYWORDS = ("今天已经签到", "请勿重复签到", "already", "10001", "重复签到")


async def do_attendance(cred: str, uid: str, game_id: str = "1", token: str | None = None) -> dict:
    logger.info(f"[do_attendance] 尝试签到 uid={uid} game_id={game_id}")
    try:
        data = await _sk_post(
            "/api/v1/game/attendance",
            {"uid": uid, "gameId": game_id},
            cred,
            token,
        )
        awards = data.get("awards") or data.get("resourceList") or []
        logger.info(f"[do_attendance] 签到成功 uid={uid} 奖励={awards}")
        return {"already_signed": False, "rewards": awards}
    except SklandAPIError as e:
        msg = str(e)
        if any(kw in msg for kw in _ALREADY_SIGNED_KEYWORDS):
            logger.info(f"[do_attendance] 今日已签到 uid={uid}")
            return {"already_signed": True, "rewards": []}
        logger.error(f"[do_attendance] 签到失败 uid={uid} 错误={e}")
        raise


async def get_monthly_rewards(cred: str, uid: str, game_id: str = "1", token: str | None = None) -> list[dict]:
    logger.info(f"[get_monthly_rewards] 获取签到奖励 uid={uid} game_id={game_id}")
    data = await _sk_get(
        "/api/v1/game/attendance/reward",
        {"uid": uid, "gameId": game_id},
        cred,
        token,
    )
    logger.info(f"[get_monthly_rewards] 获取成功 uid={uid} 条目数={len(data.get('signInList', []))}")
    return data.get("signInList", [])