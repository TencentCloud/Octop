#!/usr/bin/env python3
"""
tccli OAuth 登录辅助工具

解决 tccli auth login --browser no 在非交互式环境下无法输入验证码的问题。

用法:
  # 第一步: 生成授权链接
  python3 tccli-oauth-helper.py --get-url

  # 第二步: 用户访问链接登录后，获取 base64 验证码，然后:
  python3 tccli-oauth-helper.py --code "验证码字符串"

  # 或者一步完成（如果已有验证码）:
  python3 tccli-oauth-helper.py --code "eyJhY2Nlc3NUb2tlbi..."

  # 检查凭证状态（过期前会自动用 refreshToken 续期）:
  python3 tccli-oauth-helper.py --status

  # 强制续期一次:
  python3 tccli-oauth-helper.py --refresh
"""

import argparse
import base64
import contextlib
import json
import os
import random
import string
import sys
import time
from urllib.parse import urlencode

# 尝试从 tccli 动态导入常量
try:
    from tccli.oauth import _API_ENDPOINT, _APP_ID, _AUTH_URL, _DEFAULT_LANG, _REDIRECT_URL, _SITE
except (ImportError, AttributeError):
    # tccli 未安装或版本不兼容时，使用回退默认值
    _APP_ID = 100038427476
    _AUTH_URL = "https://cloud.tencent.com/open/authorize"
    _REDIRECT_URL = "https://cli.cloud.tencent.com/oauth"
    _SITE = "cn"
    _DEFAULT_LANG = "zh-CN"
    _API_ENDPOINT = "https://cli.cloud.tencent.com"

# 状态文件路径
_STATE_FILE = os.path.expanduser("~/.tccli/.oauth_state")

# 临时凭证/访问令牌在这个剩余时间内就提前续期，避免任务跑到一半失效
_REFRESH_SAFE_SECONDS = 600


def get_temp_cred(access_token, site):
    """获取临时凭证（从 tccli/oauth.py 复制）"""
    import uuid

    import requests

    api_endpoint = _API_ENDPOINT + "/get_temp_cred"
    body = {
        "TraceId": str(uuid.uuid4()),
        "AccessToken": access_token,
        "Site": site,
    }
    http_response = requests.post(api_endpoint, json=body, verify=True)
    resp = http_response.json()

    if "Error" in resp:
        raise ValueError(f"get_temp_key: {json.dumps(resp)}")

    return {
        "secretId": resp["SecretId"],
        "secretKey": resp["SecretKey"],
        "token": resp["Token"],
        "expiresAt": resp["ExpiresAt"],
    }


def cred_path_of_profile(profile):
    """凭证文件路径"""
    return os.path.join(os.path.expanduser("~"), ".tccli", profile + ".credential")


_PROFILE_POINTER = os.path.expanduser("~/.tccli/.octop-profile")


def resolve_profile(explicit=None):
    """选 profile：--profile > OCTOP_TCCLI_PROFILE > 工作台写入的指针 > default。

    多用户部署时工作台会把凭据写到 ``octop-<uid>`` 并更新指针文件，
    这样技能不用改调用方式也能读到正确的那份。
    """
    if explicit:
        return explicit
    env = os.environ.get("OCTOP_TCCLI_PROFILE", "").strip()
    if env:
        return env
    try:
        with open(_PROFILE_POINTER) as pointer:
            name = pointer.read().strip()
        if name:
            return name
    except OSError:
        pass
    return "default"


def save_credential(token, new_cred, profile):
    """保存凭证（从 tccli/oauth.py 复制）"""
    cred_path = cred_path_of_profile(profile)

    # 确保目录存在
    os.makedirs(os.path.dirname(cred_path), exist_ok=True, mode=0o700)

    cred = {
        "type": "oauth",
        "secretId": new_cred["secretId"],
        "secretKey": new_cred["secretKey"],
        "token": new_cred["token"],
        "expiresAt": new_cred["expiresAt"],
        "oauth": {
            "openId": token["openId"],
            "accessToken": token["accessToken"],
            "expiresAt": token["expiresAt"],
            "refreshToken": token["refreshToken"],
            "site": token["site"],
        },
    }
    # 文件里有 STS 和 refreshToken。先按 0600 创建，umask 仍可能放宽，所以再 chmod 一次。
    # chmod 失败就删掉文件，不能把密钥留成其他人可读。
    fd = os.open(cred_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as cred_file:
            json.dump(cred, cred_file, indent=4)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(cred_path)
        raise
    try:
        os.chmod(cred_path, 0o600)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.remove(cred_path)
        raise OSError(f"无法把凭证权限收成 0600: {cred_path}") from exc


def refresh_access_token(refresh_token, open_id, site):
    """用 refreshToken 换新的 accessToken（与 tccli / 控制台同一接口）。

    没有这一步时，2 小时临时凭证一到期就只能让用户重新扫码登录 ——
    这也是「明明授权过却总被要求重新授权」的根因。
    """
    import uuid

    import requests

    body = {
        "TraceId": str(uuid.uuid4()),
        "RefreshToken": refresh_token,
        "OpenId": open_id,
        "Site": site,
    }
    resp = requests.post(
        _API_ENDPOINT + "/refresh_user_token", json=body, verify=True, timeout=20
    ).json()
    if "Error" in resp:
        raise ValueError(f"refresh_user_token: {json.dumps(resp['Error'], ensure_ascii=False)}")
    # 服务端可能轮换 refreshToken：返回里带了就写回，否则下次续期会失败
    return resp["AccessToken"], float(resp["ExpiresAt"]), resp.get("RefreshToken")


def load_credential(profile):
    """读取凭证文件，缺失或损坏时返回 None。"""
    cred_path = cred_path_of_profile(profile)
    if not os.path.exists(cred_path):
        return None
    try:
        with open(cred_path) as cred_file:
            return json.load(cred_file)
    except (OSError, ValueError):
        return None


def ensure_credential(profile, force=False, safe_seconds=_REFRESH_SAFE_SECONDS):
    """按需续期，返回 ``(credential, action)``。

    action 取值：
      ``missing``   没有凭证文件
      ``static``    静态 API 密钥，无需续期
      ``valid``     仍有效，未做任何操作
      ``refreshed`` 已自动续期（accessToken 和/或临时凭证）
      ``expired``   refreshToken 也已失效，只能重新授权
    """
    cred = load_credential(profile)
    if cred is None:
        return None, "missing"
    if cred.get("type") != "oauth":
        return cred, "static"

    oauth = cred.get("oauth") or {}
    now = time.time()
    sts_expires_at = float(cred.get("expiresAt") or 0)
    if not force and sts_expires_at - now > safe_seconds:
        return cred, "valid"

    access_token = oauth.get("accessToken")
    access_expires_at = float(oauth.get("expiresAt") or 0)
    refresh_token = oauth.get("refreshToken")
    open_id = oauth.get("openId")
    site = oauth.get("site") or "cn"

    if force or not access_token or access_expires_at - now <= safe_seconds:
        if not (refresh_token and open_id):
            return cred, "expired"
        try:
            access_token, access_expires_at, rotated = refresh_access_token(
                refresh_token, open_id, site
            )
            refresh_token = rotated or refresh_token
        except Exception as exc:  # noqa: BLE001 - 任何失败都退回重新授权
            print(f"⚠️  accessToken 续期失败: {exc}")
            return cred, "expired"

    try:
        temp_cred = get_temp_cred(access_token, site)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  获取临时凭证失败: {exc}")
        return cred, "expired"

    save_credential(
        {
            "openId": open_id,
            "accessToken": access_token,
            "expiresAt": access_expires_at,
            "refreshToken": refresh_token,
            "site": site,
        },
        temp_cred,
        profile,
    )
    return load_credential(profile), "refreshed"


def sync_to_octop(profile):
    """登录成功后把凭据回灌给 Octop 工作台，让两侧共用同一套授权。

    工作台（云服务器页）用加密库、对话里用 tccli 文件；只在一边授权会让另一边
    一直显示"凭据失效"。回灌是一次 best-effort，失败不影响本次登录。
    """
    import shutil
    import subprocess

    candidates = [
        shutil.which("octop"),
        os.path.expanduser("~/.octop/bin/octop"),
    ]
    exe = next((c for c in candidates if c and os.path.exists(c)), None)
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "cloud", "import-tccli", "--profile", profile, "--quiet"],
            capture_output=True,
            timeout=25,
            text=True,
        )
    except Exception:  # noqa: BLE001 - 同步失败只是提示缺失，不阻塞登录
        return False
    return proc.returncode == 0


def generate_state():
    """生成随机 state"""
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(10))


def save_state(state):
    """保存 state 到文件"""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump({"state": state, "timestamp": time.time()}, f)


def load_state():
    """从文件加载 state"""
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
            # 检查是否过期（10分钟）
            if time.time() - data.get("timestamp", 0) > 600:
                return None
            return data.get("state")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def clear_state():
    """清除 state 文件"""
    with contextlib.suppress(FileNotFoundError):
        os.remove(_STATE_FILE)


def get_auth_url(state, language=_DEFAULT_LANG):
    """生成授权 URL"""
    redirect_params = {
        "browser": "no",
        "lang": language,
        "site": _SITE,
    }
    redirect_query = urlencode(redirect_params)
    redirect_url = _REDIRECT_URL + "?" + redirect_query

    url_params = {
        "scope": "login",
        "app_id": _APP_ID,
        "redirect_url": redirect_url,
        "state": state,
    }
    url_query = urlencode(url_params)
    auth_url = _AUTH_URL + "?" + url_query

    # 将 URL 中的 "_" 替换为 "%5F"，避免被 Markdown 解析器误解析为
    # 斜体标记（某些客户端的 markdownToPlainText 会吃掉下划线）。
    # "%5F" 是 "_" 的合法 URL 编码，HTTP 服务器会自动解码，功能完全等价。
    auth_url = auth_url.replace("_", "%5F")

    return auth_url


def do_get_url(args):
    """生成授权链接"""
    state = generate_state()
    save_state(state)

    auth_url = get_auth_url(state)

    print("━" * 60)
    print("🔐 腾讯云 OAuth 授权登录")
    print("━" * 60)
    print()
    print("请在浏览器中打开以下链接完成登录：")
    print()
    print(auth_url)
    print()
    print("━" * 60)
    print("登录后，页面会显示一串 base64 编码的验证码。")
    print("请复制该验证码，然后运行以下命令完成登录：")
    print()
    print('  python3 tccli-oauth-helper.py --code "验证码"')
    print()
    print("或发送给 AI 助手，让它帮你完成登录。")
    print("━" * 60)
    print()
    print(f"📌 State: {state} (10分钟内有效)")

    return 0


def do_login_with_code(args):
    """使用验证码完成登录"""
    code = args.code.strip()
    profile = resolve_profile(getattr(args, "profile", None))

    # 尝试加载保存的 state
    saved_state = load_state()

    try:
        # 解码验证码
        token_json = base64.b64decode(code)
        token = json.loads(token_json)
    except Exception as e:
        print(f"❌ 验证码解析失败: {e}")
        print()
        print("请确保复制了完整的 base64 验证码字符串。")
        return 1

    # 验证 state（如果有保存的话）
    token_state = token.get("state")
    if saved_state and token_state != saved_state:
        print("⚠️  警告: state 不匹配")
        print(f"   期望: {saved_state}")
        print(f"   实际: {token_state}")
        print()
        print("可能是使用了旧的授权链接。继续尝试...")

    try:
        # 获取临时凭证
        print("🔄 正在获取临时凭证...")
        cred = get_temp_cred(token["accessToken"], token.get("site", _SITE))

        # 保存凭证
        save_credential(token, cred, profile)
        clear_state()
        # 回灌给 Octop 工作台：以后两边共用同一套授权，不用再各扫一次
        synced = sync_to_octop(profile)

        cred_path = cred_path_of_profile(profile)

        print()
        print("━" * 60)
        print("✅ OAuth 登录成功!")
        print("━" * 60)
        print(f"📌 配置文件: {profile}")
        print(f"📌 凭证路径: {cred_path}")
        print(
            f"📌 过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cred['expiresAt']))}"
        )
        print("━" * 60)
        print()
        print(
            "同步到工作台（云服务器页）: "
            + ("✅ 已完成" if synced else "— 跳过（未找到 octop 命令）")
        )
        print()
        print("现在可以使用 tccli 了，例如：")
        print("  tccli cvm DescribeInstances --region ap-guangzhou")
        print()

        return 0

    except Exception as e:
        print(f"❌ 登录失败: {e}")
        return 1


def do_status(args):
    """检查凭证状态，必要时自动续期（避免每次都要重新授权）"""
    profile = resolve_profile(getattr(args, "profile", None))
    cred_path = cred_path_of_profile(profile)

    print("━" * 60)
    print("🔍 tccli 凭证状态检查")
    print("━" * 60)
    print(f"📌 配置文件: {profile}")
    print(f"📌 凭证路径: {cred_path}")
    print()

    if not os.path.exists(cred_path):
        print("❌ 凭证文件不存在")
        print()
        print("请先运行 OAuth 登录:")
        print("  python3 tccli-oauth-helper.py --get-url")
        return 1

    try:
        cred, action = ensure_credential(profile, force=bool(getattr(args, "refresh", False)))
    except Exception as e:  # noqa: BLE001 - 续期失败也要给出明确指引
        print(f"❌ 读取或续期凭证失败: {e}")
        return 1

    if cred is None:
        print("❌ 凭证文件不存在")
        print()
        print("请先运行 OAuth 登录:")
        print("  python3 tccli-oauth-helper.py --get-url")
        return 1

    cred_type = cred.get("type", "unknown")
    print(f"📌 凭证类型: {cred_type}")

    if cred_type != "oauth":
        # API 密钥方式
        secret_id = cred.get("secretId", "")
        if secret_id:
            print(f"📌 SecretId: {secret_id[:8]}...{secret_id[-4:]}")
            print()
            print("✅ 使用 API 密钥凭证")
        else:
            print("❌ 凭证文件格式异常")
            return 1
        print("━" * 60)
        return 0

    if action == "expired":
        expires_at = cred.get("expiresAt", 0)
        print(f"📌 过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")
        print()
        print("❌ 凭证与 refreshToken 均已失效，需要重新登录")
        print()
        print("请运行: python3 tccli-oauth-helper.py --get-url")
        return 1

    if action == "refreshed":
        print("♻️  已用 refreshToken 自动续期（无需重新授权）")
        print()

    expires_at = float(cred.get("expiresAt", 0))
    remaining = expires_at - time.time()
    hours = max(0, int(remaining // 3600))
    minutes = max(0, int((remaining % 3600) // 60))
    print(f"📌 过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")
    print(f"📌 剩余有效期: {hours}小时{minutes}分钟")
    print()
    print("✅ 凭证有效")

    print("━" * 60)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="tccli OAuth 登录辅助工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成授权链接
  python3 tccli-oauth-helper.py --get-url

  # 使用验证码完成登录
  python3 tccli-oauth-helper.py --code "eyJhY2Nlc3NUb2tlbi..."

  # 检查凭证状态（快过期会自动续期）
  python3 tccli-oauth-helper.py --status

  # 强制续期一次
  python3 tccli-oauth-helper.py --refresh

  # 指定配置文件
  python3 tccli-oauth-helper.py --code "验证码" --profile myprofile
""",
    )

    parser.add_argument("--get-url", action="store_true", help="生成 OAuth 授权链接")
    parser.add_argument("--code", type=str, help="base64 编码的验证码，用于完成登录")
    parser.add_argument("--status", action="store_true", help="检查当前凭证状态（自动续期）")
    parser.add_argument("--refresh", action="store_true", help="强制用 refreshToken 续期一次")
    parser.add_argument("--profile", type=str, default=None, help="配置文件名称 (默认: 自动解析)")

    args = parser.parse_args()

    if args.get_url:
        return do_get_url(args)
    elif args.code:
        return do_login_with_code(args)
    elif args.refresh:
        args.status = True
        return do_status(args)
    elif args.status:
        return do_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
