import asyncio
import base64
import gzip
import hashlib
import json
import time
import uuid

import aiohttp

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


async def _get_did() -> str:
    crypto = _try_import_crypto()
    if crypto is None:
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
                if body.get("code") == 1100:
                    return "B" + body["detail"]["deviceId"]
    except Exception:
        pass

    return _get_fallback_did()


async def _hg_post(path: str, payload: dict, did: str) -> dict:
    headers = {**_HEADERS, "dId": did}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _HG_BASE + path,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.json(content_type=None)
    except Exception as e:
        raise SklandAPIError(f"网络请求失败：{e}") from e
    if body.get("status") != 0:
        raise SklandAPIError(body.get("msg") or body.get("message") or str(body))
    return body.get("data", {})


async def _sk_post(path: str, payload: dict, cred: str | None = None) -> dict:
    headers = {**_HEADERS}
    if cred:
        headers["cred"] = cred
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _SK_BASE + path,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.json(content_type=None)
    except Exception as e:
        raise SklandAPIError(f"网络请求失败：{e}") from e
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
    return await _get_cred_by_code(oauth_code)


async def login_with_code(phone: str, sms_code: str) -> dict:
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
    return await _get_cred_by_code(oauth_code)


async def check_cred(cred: str) -> bool:
    headers = {**_HEADERS, "cred": cred}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _SK_BASE + "/api/v1/user/check",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json(content_type=None)
        return body.get("code") == 0
    except Exception:
        return False


async def _sk_get(path: str, params: dict | None, cred: str) -> dict:
    headers = {**_HEADERS, "cred": cred}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _SK_BASE + path,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.json(content_type=None)
    except Exception as e:
        raise SklandAPIError(f"网络请求失败：{e}") from e
    if body.get("code") != 0:
        raise SklandAPIError(body.get("message") or str(body))
    return body.get("data", {})


async def get_binding_list(cred: str) -> list[dict]:
    data = await _sk_get("/api/v1/game/player/binding", None, cred)
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
                })
    return result


async def do_attendance(cred: str, uid: str, game_id: str = "1") -> dict:
    try:
        data = await _sk_post(
            "/api/v1/game/attendance",
            {"uid": uid, "gameId": game_id},
            cred,
        )
        return {"already_signed": False, "rewards": data.get("awards", data.get("resourceList", []))}
    except SklandAPIError as e:
        msg = str(e)
        if "今天已经签到" in msg or "10001" in msg:
            return {"already_signed": True, "rewards": []}
        raise


async def get_monthly_rewards(cred: str, uid: str, game_id: str = "1") -> list[dict]:
    data = await _sk_get(
        "/api/v1/game/attendance/reward",
        {"uid": uid, "gameId": game_id},
        cred,
    )
    return data.get("signInList", [])