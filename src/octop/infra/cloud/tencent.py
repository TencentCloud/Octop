"""Tencent Cloud CVM access for the Workbench cloud tab.

Uses the same browser OAuth flow as ``tccli`` (the one the Cluster Doctor
expert relies on) so operators never paste long-term AK/SK pairs. SQLite
keeps the login in encrypted files under ``~/.octop/secrets/cloud/``.
PostgreSQL stores it in the shared ``secrets`` table so any instance can
serve the user, and imports those files once on first use. Tokens refresh
automatically while the refresh token is still valid.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from tencentcloud.common.credential import Credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cvm.v20170312 import cvm_client
from tencentcloud.cvm.v20170312 import models as cvm_models
from tencentcloud.monitor.v20180724 import models as monitor_models
from tencentcloud.monitor.v20180724 import monitor_client

logger = logging.getLogger(__name__)


def _write_private(path: Path, data: bytes) -> None:
    """Write bytes as 0600. ``umask`` would otherwise leave secrets readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


_AUTH_URL = "https://cloud.tencent.com/open/authorize"
_REDIRECT_URL = "https://cli.cloud.tencent.com/oauth"
_API_ENDPOINT = "https://cli.cloud.tencent.com"
_APP_ID = 100038427476
_SITE = "cn"
_LANG = "zh-CN"

_LOGGER = logging.getLogger(__name__)

STATE_TTL_S = 600.0
CRED_REFRESH_SAFE_S = 300.0
ACCESS_REFRESH_SAFE_S = 300.0

_CST = timezone(timedelta(hours=8))

_METRICS = {
    "cpu": "CpuUsage",
    "mem": "MemUsage",
    # Tencent names the load average "CpuLoadavg" (1 min); "CpuLoad" does not exist.
    "load": "CpuLoadavg",
    # Requires the cloud monitor agent; empty series when absent.
    "disk_usage": "CvmDiskUsage",
    "net_in": "LanIntraffic",
    "net_out": "LanOuttraffic",
}


class CloudError(RuntimeError):
    """Raised when a Tencent Cloud call cannot complete."""


def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(body).encode()
    request = urllib.request.Request(
        _API_ENDPOINT + path,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read().decode() or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise CloudError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001 - surface any transport failure
        raise CloudError(f"腾讯云 OAuth 网关不可达: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CloudError("腾讯云 OAuth 网关返回了无法解析的内容") from exc
    if not isinstance(parsed, dict):
        raise CloudError("腾讯云 OAuth 网关返回了意外的内容")
    if "Error" in parsed:
        raise CloudError(json.dumps(parsed["Error"], ensure_ascii=False))
    return parsed


def build_authorization(state: str) -> str:
    redirect = _REDIRECT_URL + "?" + urlencode({"browser": "no", "lang": _LANG, "site": _SITE})
    query = urlencode(
        {
            "scope": "login",
            "app_id": _APP_ID,
            "redirect_url": redirect,
            "state": state,
        }
    )
    return f"{_AUTH_URL}?{query}".replace("_", "%5F")


def decode_ticket(code: str) -> dict[str, Any]:
    cleaned = "".join(code.split())
    if not cleaned:
        raise CloudError("验证码为空")
    padded = cleaned + "=" * (-len(cleaned) % 4)
    try:
        payload = json.loads(base64.b64decode(padded, validate=False))
    except Exception as exc:  # noqa: BLE001 - any decode failure is user input
        raise CloudError("验证码不是有效的 base64 票据") from exc
    if not isinstance(payload, dict) or not payload.get("accessToken"):
        raise CloudError("验证码缺少 accessToken")
    return payload


def fetch_sts(access_token: str, site: str = _SITE) -> dict[str, Any]:
    payload = _post_json(
        "/get_temp_cred",
        {"TraceId": str(uuid.uuid4()), "AccessToken": access_token, "Site": site},
    )
    try:
        return {
            "secret_id": str(payload["SecretId"]),
            "secret_key": str(payload["SecretKey"]),
            "token": str(payload.get("Token") or ""),
            "expires_at": float(payload["ExpiresAt"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise CloudError("临时凭证响应缺少字段") from exc


def refresh_access_token(refresh_token: str, open_id: str, site: str = _SITE) -> dict[str, Any]:
    payload = _post_json(
        "/refresh_user_token",
        {
            "TraceId": str(uuid.uuid4()),
            "RefreshToken": refresh_token,
            "OpenId": open_id,
            "Site": site,
        },
    )
    try:
        return {
            "access_token": str(payload["AccessToken"]),
            "access_expires_at": float(payload["ExpiresAt"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise CloudError("刷新响应缺少字段") from exc


@dataclass(frozen=True)
class CloudCredential:
    secret_id: str
    secret_key: str
    token: str
    expires_at: float
    access_token: str
    access_expires_at: float
    refresh_token: str
    open_id: str
    site: str = _SITE

    def to_dict(self) -> dict[str, Any]:
        return {
            "secret_id": self.secret_id,
            "secret_key": self.secret_key,
            "token": self.token,
            "expires_at": self.expires_at,
            "access_token": self.access_token,
            "access_expires_at": self.access_expires_at,
            "refresh_token": self.refresh_token,
            "open_id": self.open_id,
            "site": self.site,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CloudCredential:
        return cls(
            secret_id=str(raw.get("secret_id") or ""),
            secret_key=str(raw.get("secret_key") or ""),
            token=str(raw.get("token") or ""),
            expires_at=float(raw.get("expires_at") or 0),
            access_token=str(raw.get("access_token") or ""),
            access_expires_at=float(raw.get("access_expires_at") or 0),
            refresh_token=str(raw.get("refresh_token") or ""),
            open_id=str(raw.get("open_id") or ""),
            site=str(raw.get("site") or _SITE),
        )

    def remaining(self, *, now: float | None = None) -> float:
        return self.expires_at - (time.time() if now is None else now)

    def can_refresh(self) -> bool:
        return bool(self.refresh_token and self.open_id)


def credential_from_ticket(ticket: dict[str, Any]) -> CloudCredential:
    access_token = str(ticket.get("accessToken") or "")
    site = str(ticket.get("site") or _SITE)
    sts = fetch_sts(access_token, site)
    return CloudCredential(
        secret_id=sts["secret_id"],
        secret_key=sts["secret_key"],
        token=sts["token"],
        expires_at=sts["expires_at"],
        access_token=access_token,
        access_expires_at=float(ticket.get("expiresAt") or 0),
        refresh_token=str(ticket.get("refreshToken") or ""),
        open_id=str(ticket.get("openId") or ""),
        site=site,
    )


def refresh_credential(credential: CloudCredential) -> CloudCredential:
    access_token = credential.access_token
    access_expires_at = credential.access_expires_at
    if access_expires_at - time.time() < ACCESS_REFRESH_SAFE_S:
        if not credential.can_refresh():
            raise CloudError("访问令牌已过期且无法续期，请重新授权")
        renewed = refresh_access_token(
            credential.refresh_token, credential.open_id, credential.site
        )
        access_token = renewed["access_token"]
        access_expires_at = renewed["access_expires_at"]
    sts = fetch_sts(access_token, credential.site)
    return CloudCredential(
        secret_id=sts["secret_id"],
        secret_key=sts["secret_key"],
        token=sts["token"],
        expires_at=sts["expires_at"],
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=credential.refresh_token,
        open_id=credential.open_id,
        site=credential.site,
    )


class _SecretBytes(Protocol):
    def get(self, k: str) -> bytes | None: ...

    def put(self, k: str, value: bytes) -> None: ...

    def put_if_absent(self, k: str, value: bytes) -> bool: ...

    def delete(self, k: str) -> bool: ...


def _cred_key(user_id: int) -> str:
    return f"cloud.cred.{int(user_id)}"


def _state_key(user_id: int) -> str:
    return f"cloud.state.{int(user_id)}"


def _user_id_from_blob(path: Path) -> int | None:
    name = path.name
    prefix = "tencent-"
    suffix = ".enc"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    raw = name[len(prefix) : -len(suffix)]
    if not raw.isdigit():
        return None
    return int(raw)


class CloudCredentialStore:
    """Per-user Tencent Cloud login for the Workbench.

    ``secrets`` is set only for PostgreSQL. The table is then the source of
    truth, shared by every instance. SQLite keeps the encrypted files.
    """

    def __init__(self, root: Path, secrets: _SecretBytes | None = None) -> None:
        self._dir = root / "secrets" / "cloud"
        self._key_path = root / "secrets" / "cloud.key"
        self._secrets = secrets

    @property
    def shared(self) -> bool:
        return self._secrets is not None

    def _fernet(self) -> Fernet:
        if not self._key_path.exists():
            _write_private(self._key_path, Fernet.generate_key())
        return Fernet(self._key_path.read_bytes().strip())

    def _path(self, user_id: int) -> Path:
        return self._dir / f"tencent-{int(user_id)}.enc"

    def _state_path(self, user_id: int) -> Path:
        return self._dir / f"state-{int(user_id)}.json"

    def load(self, user_id: int) -> CloudCredential | None:
        if self._secrets is not None:
            return self._load_shared(user_id)
        path = self._path(user_id)
        if not path.is_file():
            return None
        try:
            raw = json.loads(self._fernet().decrypt(path.read_bytes()))
        except Exception:  # noqa: BLE001 - corrupted blob must not crash callers
            return None
        return self._credential_or_none(raw)

    def save(self, user_id: int, credential: CloudCredential) -> None:
        if self._secrets is not None:
            self._secrets.put(_cred_key(user_id), _dump_credential(credential))
            self._path(user_id).unlink(missing_ok=True)
            return
        path = self._path(user_id)
        _write_private(path, self._fernet().encrypt(json.dumps(credential.to_dict()).encode()))

    def clear(self, user_id: int) -> bool:
        removed = False
        if self._secrets is not None:
            removed = self._secrets.delete(_cred_key(user_id)) or removed
            removed = self._secrets.delete(_state_key(user_id)) or removed
        for path in (self._path(user_id), self._state_path(user_id)):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
        return removed

    def new_state(self, user_id: int) -> str:
        value = secrets.token_urlsafe(16)
        payload = json.dumps({"state": value, "created_at": time.time()}).encode()
        if self._secrets is not None:
            self._secrets.put(_state_key(user_id), payload)
            self._state_path(user_id).unlink(missing_ok=True)
            return value
        _write_private(self._state_path(user_id), payload)
        return value

    def consume_state(self, user_id: int, state: str) -> bool | None:
        if self._secrets is not None:
            raw = self._secrets.get(_state_key(user_id))
            if raw is None:
                return None
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            result = self._match_state(payload, state)
            if result is True:
                self._secrets.delete(_state_key(user_id))
            return result
        path = self._state_path(user_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        result = self._match_state(payload, state)
        if result is True:
            path.unlink(missing_ok=True)
        return result

    def adopt_local(self) -> int:
        """Copy local ciphertext into the shared table when that user has no row yet.

        A row already in the database wins. Imported files are removed so a
        later logout cannot be restored from this machine's disk.
        """
        secrets_repo = self._secrets
        if secrets_repo is None or not self._dir.is_dir() or not self._key_path.is_file():
            return 0
        try:
            fernet = Fernet(self._key_path.read_bytes().strip())
        except Exception:  # noqa: BLE001 - a bad key must not block startup
            return 0
        imported = 0
        for path in sorted(self._dir.glob("tencent-*.enc")):
            user_id = _user_id_from_blob(path)
            if user_id is None:
                continue
            try:
                raw = json.loads(fernet.decrypt(path.read_bytes()))
            except Exception:  # noqa: BLE001 - skip a blob this key cannot read
                continue
            credential = self._credential_or_none(raw)
            if credential is None:
                continue
            if secrets_repo.put_if_absent(_cred_key(user_id), _dump_credential(credential)):
                imported += 1
            if secrets_repo.get(_cred_key(user_id)) is not None:
                path.unlink(missing_ok=True)
        if imported:
            logger.info(
                "imported %d Tencent Cloud login(s) into the control-plane database",
                imported,
            )
        return imported

    def _load_shared(self, user_id: int) -> CloudCredential | None:
        secrets_repo = self._secrets
        if secrets_repo is None:
            return None
        raw = secrets_repo.get(_cred_key(user_id))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return self._credential_or_none(payload)

    @staticmethod
    def _credential_or_none(raw: Any) -> CloudCredential | None:
        if not isinstance(raw, dict):
            return None
        credential = CloudCredential.from_dict(raw)
        if not credential.secret_id or not credential.secret_key:
            return None
        return credential

    @staticmethod
    def _match_state(payload: Any, state: str) -> bool | None:
        if not isinstance(payload, dict):
            return None
        expected = str(payload.get("state") or "")
        created = float(payload.get("created_at") or 0)
        if not expected or time.time() - created > STATE_TTL_S:
            return None
        return secrets.compare_digest(expected, state.strip())


def _dump_credential(credential: CloudCredential) -> bytes:
    return json.dumps(credential.to_dict()).encode()


def open_cloud_credential_store(
    root: Path, config: Any, secrets: _SecretBytes
) -> CloudCredentialStore:
    """File store on SQLite; shared ``secrets`` rows on PostgreSQL.

    Opening the shared store also imports leftover local files for users
    the database does not know yet.
    """
    database = getattr(config, "database", None)
    if database is not None and getattr(database, "is_postgresql", False):
        store = CloudCredentialStore(root, secrets)
        store.adopt_local()
        return store
    return CloudCredentialStore(root)


def require_credential(store: CloudCredentialStore, user_id: int) -> CloudCredential:
    credential = store.load(user_id)
    if credential is None:
        raise CloudError("尚未授权腾讯云")
    if credential.remaining() > CRED_REFRESH_SAFE_S:
        return credential
    renewed = refresh_credential(credential)
    store.save(user_id, renewed)
    return renewed


def _profile(timeout_seconds: int = 20) -> ClientProfile:
    http = HttpProfile()
    http.reqTimeout = timeout_seconds
    return ClientProfile(httpProfile=http)


def _credential_of(credential: CloudCredential) -> Credential:
    return Credential(credential.secret_id, credential.secret_key, credential.token)


REGION_CACHE_TTL_S = 300.0
INSTANCE_CACHE_TTL_S = 30.0
_REGION_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_INSTANCE_CACHE: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
_CATALOG_LOCK = threading.Lock()

# 默认"全部地域"时一次性打 20+ 个地域的 DescribeInstances，串行要 4~6s。
# 并发后 ~0.6s，再加 30s 短缓存，用户反复进出工作台基本是瞬开。
REGION_CONCURRENCY = 16


def list_regions(credential: CloudCredential, *, nocache: bool = False) -> list[dict[str, str]]:
    key = credential.secret_id
    if not nocache:
        with _CATALOG_LOCK:
            hit = _REGION_CACHE.get(key)
            if hit and time.time() - hit[0] <= REGION_CACHE_TTL_S:
                return hit[1]
    client = cvm_client.CvmClient(_credential_of(credential), "ap-guangzhou", _profile())
    response = client.DescribeRegions(cvm_models.DescribeRegionsRequest())
    regions = [
        {"id": str(item.Region), "name": str(item.RegionName or item.Region)}
        for item in (response.RegionSet or [])
        if item.Region and str(item.RegionState or "") != "UNAVAILABLE"
    ]
    with _CATALOG_LOCK:
        _REGION_CACHE[key] = (time.time(), regions)
    return regions


def _list_region_instances(
    credential: CloudCredential,
    region: str,
    *,
    attempts: int = 2,
) -> list[dict[str, Any]]:
    """One region's instances. 单地域失败只丢这一个地域，不拖垮整页。

    并发 16 个地域时偶发 RequestLimitExceeded / 单请求超时，重试一次基本都能过。
    """
    for attempt in range(attempts):
        try:
            return _list_region_instances_once(credential, region)
        except TencentCloudSDKException as exc:
            if attempt + 1 >= attempts:
                _LOGGER.warning("DescribeInstances failed in %s: %s", region, exc)
                return []
            time.sleep(0.25)
        except Exception as exc:  # noqa: BLE001 - 网络抖动同样降级
            _LOGGER.warning("DescribeInstances crashed in %s: %s", region, exc)
            return []
    return []


def _list_region_instances_once(credential: CloudCredential, region: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    client = cvm_client.CvmClient(_credential_of(credential), region, _profile())
    offset = 0
    while True:
        request = cvm_models.DescribeInstancesRequest()
        request.Offset = offset
        request.Limit = 100
        response = client.DescribeInstances(request)
        batch = list(response.InstanceSet or [])
        for item in batch:
            if not item.InstanceId:
                continue
            public_ips = [str(ip) for ip in (item.PublicIpAddresses or [])]
            private_ips = [str(ip) for ip in (item.PrivateIpAddresses or [])]
            out.append(
                {
                    "instance_id": str(item.InstanceId),
                    "name": str(item.InstanceName or item.InstanceId),
                    "region": region,
                    "zone": str(item.Placement.Zone if item.Placement else ""),
                    "state": str(item.InstanceState or ""),
                    "os_name": str(item.OsName or ""),
                    "private_ips": private_ips,
                    "public_ips": public_ips,
                    "created_at": str(item.CreatedTime or ""),
                    "cpu": int(item.CPU or 0),
                    "memory_gb": int(item.Memory or 0),
                }
            )
        offset += len(batch)
        if not batch or offset >= int(response.TotalCount or 0):
            break
    return out


def list_instances(
    credential: CloudCredential,
    regions: list[str],
    *,
    nocache: bool = False,
) -> dict[str, Any]:
    """All instances across regions, fetched concurrently and cached for 30s."""
    if not regions:
        return {"instances": [], "fetched_at": int(time.time()), "cached": False}

    key = (credential.secret_id, tuple(sorted(regions)))
    if not nocache:
        with _CATALOG_LOCK:
            hit = _INSTANCE_CACHE.get(key)
            if hit and time.time() - hit[0] <= INSTANCE_CACHE_TTL_S:
                return {"instances": hit[1], "fetched_at": int(hit[0]), "cached": True}

    workers = max(1, min(REGION_CONCURRENCY, len(regions)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        chunks = list(pool.map(lambda region: _list_region_instances(credential, region), regions))
    instances = [item for chunk in chunks for item in chunk]

    with _CATALOG_LOCK:
        _INSTANCE_CACHE[key] = (time.time(), instances)
        if len(_INSTANCE_CACHE) > 64:
            oldest = min(_INSTANCE_CACHE, key=lambda item: _INSTANCE_CACHE[item][0])
            _INSTANCE_CACHE.pop(oldest, None)
    return {"instances": instances, "fetched_at": int(time.time()), "cached": False}


# CloudMonitor 在 1 分钟粒度下通常延迟 1~2 分钟才可查到点。窗口末端不补偿的话，
# "最新值"永远是两分钟前的，且末点常常查不到（看起来像数据卡住）。
METRIC_LAG_S = 120
# 快速来回切节点时命中短缓存，秒开；超过该 TTL 视为过期，下一次点击/刷新会重新拉。
METRIC_CACHE_TTL_S = 15.0
METRIC_CACHE_MAX = 256
_METRIC_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_METRIC_CACHE_LOCK = threading.Lock()


def _cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    now = time.time()
    with _METRIC_CACHE_LOCK:
        hit = _METRIC_CACHE.get(key)
        if hit is None:
            return None
        stamp, payload = hit
        if now - stamp > METRIC_CACHE_TTL_S:
            _METRIC_CACHE.pop(key, None)
            return None
    return {**payload, "cached": True}


def _cache_put(key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    with _METRIC_CACHE_LOCK:
        if len(_METRIC_CACHE) >= METRIC_CACHE_MAX:
            oldest = min(_METRIC_CACHE, key=lambda item: _METRIC_CACHE[item][0])
            _METRIC_CACHE.pop(oldest, None)
        _METRIC_CACHE[key] = (time.time(), payload)


def _monitor_pairs(timestamps: list[Any], values: list[Any]) -> list[tuple[int, float]]:
    """Pair Cloud Monitor stamps with values, dropping nulls.

    The last minutes of a series are often null while the point is still
    settling. One null used to raise and blank the whole chart.
    """
    pairs: list[tuple[int, float]] = []
    for stamp, value in zip(timestamps or [], values or [], strict=False):
        if stamp is None or value is None:
            continue
        try:
            pairs.append((int(float(stamp)), float(value)))
        except (TypeError, ValueError):
            continue
    return pairs


def _time_window(minutes: int, lag_seconds: int = 0) -> tuple[str, str]:
    end = datetime.now(_CST) - timedelta(seconds=lag_seconds)
    start = end - timedelta(minutes=minutes)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        end.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    )


def _fetch_metric_series(
    credential: CloudCredential,
    *,
    region: str,
    instance_id: str,
    start: str,
    end: str,
    period: int,
    key: str,
    metric: str,
) -> tuple[str, list[dict[str, float]]]:
    client = monitor_client.MonitorClient(_credential_of(credential), region, _profile())
    request = monitor_models.GetMonitorDataRequest()
    request.Namespace = "QCE/CVM"
    request.MetricName = metric
    request.Period = period
    request.StartTime = start
    request.EndTime = end
    request.Instances = [{"Dimensions": [{"Name": "InstanceId", "Value": instance_id}]}]
    try:
        response = client.GetMonitorData(request)
    except TencentCloudSDKException as exc:
        # A wrong metric name used to fail silently and render as "no data".
        _LOGGER.warning("cloud metric %s (%s) failed: %s", key, metric, exc)
        return key, []
    except Exception as exc:  # noqa: BLE001 - 网络异常不该拖垮整页
        _LOGGER.warning("cloud metric %s (%s) crashed: %s", key, metric, exc)
        return key, []
    points = list(response.DataPoints or [])
    if not points:
        return key, []
    first = points[0]
    return key, [
        {"t": stamp, "v": value}
        for stamp, value in _monitor_pairs(first.Timestamps or [], first.Values or [])
    ]


def query_metrics(
    credential: CloudCredential,
    *,
    region: str,
    instance_id: str,
    minutes: int = 60,
    period: int = 60,
    nocache: bool = False,
) -> dict[str, Any]:
    """Return CloudMonitor series for one instance (CPU / memory / disk / net).

    6 个指标走线程池并发请求（原来串行 6 个 RTT），并带 15s 短缓存：
    前端先用缓存出图再后台刷新，来回切节点不会反复打云监控。
    """
    cache_key = (credential.secret_id, region, instance_id, minutes, period)
    if not nocache:
        hit = _cache_get(cache_key)
        if hit is not None:
            return hit

    start, end = _time_window(minutes, METRIC_LAG_S)
    series: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(_METRICS)) as pool:
        for key, points in pool.map(
            lambda item: _fetch_metric_series(
                credential,
                region=region,
                instance_id=instance_id,
                start=start,
                end=end,
                period=period,
                key=item[0],
                metric=item[1],
            ),
            list(_METRICS.items()),
        ):
            series[key] = points

    payload = {
        "instance_id": instance_id,
        "region": region,
        "series": series,
        "fetched_at": int(time.time()),
        "cached": False,
    }
    _cache_put(cache_key, payload)
    return payload


# GetMonitorData 一次最多 50 个实例（文档 product/248/31014）。超出会整批失败。
BATCH_INSTANCE_LIMIT = 50
# 指标 × 地域 的组合并发上限（云监控按地域限频，单个地域内仍是一条请求一批）
BATCH_CONCURRENCY = 8


def _get_monitor_series(
    credential: CloudCredential,
    *,
    region: str,
    instance_ids: list[str],
    metric: str,
    start: str,
    end: str,
    period: int,
    client: Any | None = None,
    depth: int = 0,
) -> dict[str, list[tuple[int, float]]]:
    """批量取一个指标的序列。

    ``GetMonitorData`` 只要批里有一台实例非法（已销毁 / 无权限），整批都会
    报 ``InvalidParameterValue``，导致另外几百台一起变成"无采样"。这里按二分
    递归降级，最终只丢掉真正出问题的那几台。
    """
    if not instance_ids:
        return {}
    if client is None:
        client = monitor_client.MonitorClient(_credential_of(credential), region, _profile())
    request = monitor_models.GetMonitorDataRequest()
    request.Namespace = "QCE/CVM"
    request.MetricName = metric
    request.Period = period
    request.StartTime = start
    request.EndTime = end
    request.Instances = [
        {"Dimensions": [{"Name": "InstanceId", "Value": instance_id}]}
        for instance_id in instance_ids
    ]
    try:
        response = client.GetMonitorData(request)
    except TencentCloudSDKException as exc:
        if len(instance_ids) == 1 or depth >= 6:
            _LOGGER.debug("monitor %s %s skipped: %s", metric, instance_ids[0], exc)
            return {}
        _LOGGER.info(
            "monitor %s batch of %d failed (%s), downgrading to per-instance",
            metric,
            len(instance_ids),
            exc,
        )
        middle = len(instance_ids) // 2
        merged = _get_monitor_series(
            credential,
            region=region,
            instance_ids=instance_ids[:middle],
            metric=metric,
            start=start,
            end=end,
            period=period,
            client=client,
            depth=depth + 1,
        )
        merged.update(
            _get_monitor_series(
                credential,
                region=region,
                instance_ids=instance_ids[middle:],
                metric=metric,
                start=start,
                end=end,
                period=period,
                client=client,
                depth=depth + 1,
            )
        )
        return merged

    out: dict[str, list[tuple[int, float]]] = {}
    for points in response.DataPoints or []:
        instance_id = ""
        for dimension in points.Dimensions or []:
            if dimension.Name == "InstanceId":
                instance_id = dimension.Value or ""
                break
        if not instance_id:
            continue
        pairs = _monitor_pairs(points.Timestamps or [], points.Values or [])
        if pairs:
            out[instance_id] = pairs
    return out


def query_latest_metrics(
    credential: CloudCredential,
    *,
    targets: list[dict[str, str]],
    period: int = 60,
) -> dict[str, Any]:
    """Latest value per instance for every metric, batched across instances.

    ``GetMonitorData`` accepts many instance dimensions per call, so a 500 node
    fleet costs a handful of requests instead of one per instance.
    """
    sampled_at = int(time.time())
    if not targets:
        return {"sampled_at": sampled_at, "items": {}}

    # 只需要最新值：60s 粒度下取 6 分钟窗口即可覆盖 CloudMonitor 的 1~2 分钟延迟，
    # 窗口再大只会让每次批量响应多传几倍数据点。
    start, end = _time_window(6)
    items: dict[str, dict[str, float]] = {}

    by_region: dict[str, list[str]] = {}
    for target in targets:
        region = target.get("region") or ""
        instance_id = target.get("instance_id") or ""
        if not region or not instance_id:
            continue
        by_region.setdefault(region, []).append(instance_id)

    tasks: list[tuple[str, str, list[str]]] = []
    for key, _metric in _METRICS.items():
        for region, instance_ids in by_region.items():
            for offset in range(0, len(instance_ids), BATCH_INSTANCE_LIMIT):
                tasks.append((key, region, instance_ids[offset : offset + BATCH_INSTANCE_LIMIT]))

    def fetch(task: tuple[str, str, list[str]]) -> tuple[str, dict[str, list[tuple[int, float]]]]:
        key, region, chunk = task
        series = _get_monitor_series(
            credential,
            region=region,
            instance_ids=chunk,
            metric=_METRICS[key],
            start=start,
            end=end,
            period=period,
        )
        return key, series

    # 指标 × 地域 本来是一串串行请求（跨 40 个地域能跑到十几秒），并发后压到 1~2s
    with ThreadPoolExecutor(max_workers=min(BATCH_CONCURRENCY, len(tasks) or 1)) as pool:
        for key, series in pool.map(fetch, tasks):
            for instance_id, pairs in series.items():
                items.setdefault(instance_id, {})[key] = pairs[-1][1]
    return {"sampled_at": sampled_at, "items": items}


CLUSTER_TREND_LIMIT = 12
TREND_KEYS = ("cpu", "mem", "net_in", "net_out")
# 首轮抽样全都没数据时（列表头部常常是刚创建/已销毁的实例），换下一批继续试。
TREND_ROUNDS = 5
TREND_CANDIDATE_LIMIT = 60


def _ordered_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """Round-robin across regions so one big region cannot dominate the sample."""
    by_region: dict[str, list[dict[str, str]]] = {}
    for target in targets:
        region = (target.get("region") or "").strip()
        instance_id = (target.get("instance_id") or "").strip()
        if region and instance_id:
            by_region.setdefault(region, []).append({"region": region, "instance_id": instance_id})

    ordered: list[dict[str, str]] = []
    depth = 0
    while True:
        added = False
        for bucket in by_region.values():
            if depth < len(bucket):
                ordered.append(bucket[depth])
                added = True
        if not added:
            break
        depth += 1
    return ordered


def _sample_targets(targets: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    return _ordered_targets(targets)[:limit]


def query_cluster_trend(
    credential: CloudCredential,
    *,
    targets: list[dict[str, str]],
    minutes: int = 60,
    period: int = 60,
    max_instances: int = CLUSTER_TREND_LIMIT,
) -> dict[str, Any]:
    """Average CPU / memory / network over time across a sampled subset.

    ``GetMonitorData`` caps a response at roughly 1440 points and the fleet is
    large, so the trend samples a round-robin subset of instances and averages
    them per timestamp. The payload reports how many instances actually
    contributed points so the UI can label the curve honestly.
    """
    sampled_at = int(time.time())
    candidates = _ordered_targets(targets)[:TREND_CANDIDATE_LIMIT]
    if not candidates:
        return {
            "sampled_at": sampled_at,
            "sampled": 0,
            "total": 0,
            "period": period,
            "points": [],
        }

    start, end = _time_window(minutes, METRIC_LAG_S)
    step = max(1, max_instances)
    buckets: dict[int, dict[str, list[float]]] = {}
    contributing: set[str] = set()
    tried = 0
    # 只拿到两三个点画不出趋势（常见于刚创建的实例），按时间窗覆盖度判定够不够
    expected = max(1, minutes * 60 // max(1, period))
    min_buckets = max(4, expected // 6)

    for round_index in range(TREND_ROUNDS):
        chunk = candidates[round_index * step : (round_index + 1) * step]
        if not chunk:
            break
        tried += len(chunk)

        by_region: dict[str, list[str]] = {}
        for target in chunk:
            by_region.setdefault(target["region"], []).append(target["instance_id"])

        tasks = [
            (key, region, instance_ids)
            for key in TREND_KEYS
            for region, instance_ids in by_region.items()
        ]

        def fetch(
            task: tuple[str, str, list[str]],
        ) -> tuple[str, dict[str, list[tuple[int, float]]]]:
            key, region, instance_ids = task
            series = _get_monitor_series(
                credential,
                region=region,
                instance_ids=instance_ids,
                metric=_METRICS[key],
                start=start,
                end=end,
                period=period,
            )
            return key, series

        with ThreadPoolExecutor(max_workers=min(BATCH_CONCURRENCY, len(tasks) or 1)) as pool:
            for key, series in pool.map(fetch, tasks):
                for instance_id, pairs in series.items():
                    contributing.add(instance_id)
                    for stamp, value in pairs:
                        bucket = stamp - stamp % max(1, period)
                        buckets.setdefault(bucket, {}).setdefault(key, []).append(value)

        # 覆盖度够了才停；只捞到零星几个点就继续换下一批，把点合并起来
        if len(buckets) >= min_buckets:
            break

    points: list[dict[str, Any]] = []
    for stamp in sorted(buckets):
        row: dict[str, Any] = {"t": stamp}
        for key in TREND_KEYS:
            values = buckets[stamp].get(key) or []
            if values:
                row[key] = round(sum(values) / len(values), 2)
        points.append(row)

    return {
        "sampled_at": sampled_at,
        "sampled": len(contributing) or tried,
        "total": len(targets),
        "period": period,
        "points": points,
    }


_ACTIONS = {
    "start": (cvm_models.StartInstancesRequest, "StartInstances"),
    "stop": (cvm_models.StopInstancesRequest, "StopInstances"),
    "reboot": (cvm_models.RebootInstancesRequest, "RebootInstances"),
}


def instance_action(
    credential: CloudCredential,
    *,
    region: str,
    instance_id: str,
    action: str,
) -> dict[str, Any]:
    spec = _ACTIONS.get(action)
    if spec is None:
        raise CloudError(f"不支持的操作: {action}")
    request_cls, _name = spec
    client = cvm_client.CvmClient(_credential_of(credential), region, _profile())
    request = request_cls()
    request.InstanceIds = [instance_id]
    if action == "stop":
        request.StoppedMode = "STOP_CHARGING"
    client.call(_name, request.to_json_string())
    return {"instance_id": instance_id, "action": action, "accepted": True}


_TCCLI_PROFILE_POINTER = ".octop-profile"
_TCCLI_ISOLATION_ENV = "OCTOP_TCCLI_PROFILE_ISOLATION"


def tccli_profile_for_user(uid: int | None) -> str:
    """tccli profile the mirror writes to.

    Multi-user isolation (``octop-<uid>``) stops two Octop accounts from
    overwriting each other's machine-wide ``~/.tccli`` login. It stays opt-in
    (``OCTOP_TCCLI_PROFILE_ISOLATION=1``) because plain ``tccli`` without
    ``--profile`` always reads ``default``.
    """
    if uid is None:
        return "default"
    enabled = os.environ.get(_TCCLI_ISOLATION_ENV, "").strip().lower()
    if enabled not in ("1", "true", "yes", "on"):
        return "default"
    return f"octop-{int(uid)}"


def mirror_to_tccli(
    credential: CloudCredential,
    *,
    profile: str | None = None,
    uid: int | None = None,
) -> str:
    """Mirror the OAuth login into tccli's own credential file.

    The Workbench keeps an encrypted per-user copy, while the ops expert's skill
    drives ``tccli`` off ``~/.tccli/<profile>.credential``. Without this bridge
    the user has to authorize twice and the tccli copy silently rots (~2h TTL),
    which shows up as "I just authorized, why is the credential still expired?".

    Returns ``ok`` / ``skipped`` (no ``~/.tccli``) / ``failed`` (IO error, logged
    so the caller can surface it instead of failing silently).
    """
    name = profile or tccli_profile_for_user(uid)
    tccli_dir = Path.home() / ".tccli"
    if not tccli_dir.is_dir():
        return "skipped"
    payload = {
        "type": "oauth",
        "secretId": credential.secret_id,
        "secretKey": credential.secret_key,
        "token": credential.token,
        "expiresAt": credential.expires_at,
        "oauth": {
            "openId": credential.open_id,
            "accessToken": credential.access_token,
            "expiresAt": credential.access_expires_at,
            "refreshToken": credential.refresh_token,
            "site": credential.site,
        },
    }
    path = tccli_dir / f"{name}.credential"
    tmp = path.with_name(f".{path.name}.tmp")
    pointer = tccli_dir / _TCCLI_PROFILE_POINTER
    try:
        _write_private(tmp, json.dumps(payload, indent=4).encode())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        _write_private(pointer, (name + "\n").encode())
    except OSError:
        tmp.unlink(missing_ok=True)
        logger.warning("failed to mirror cloud credential into %s", path, exc_info=True)
        return "failed"
    logger.info("mirrored cloud credential into %s", path)
    return "ok"


def credential_from_tccli(path: Path) -> CloudCredential:
    """Read a tccli ``*.credential`` file into a :class:`CloudCredential`."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CloudError(f"tccli 凭证无法读取: {exc}") from exc
    if not isinstance(raw, dict) or str(raw.get("type") or "") != "oauth":
        raise CloudError("tccli 凭证不是 OAuth 类型")
    oauth = raw.get("oauth") or {}
    credential = CloudCredential(
        secret_id=str(raw.get("secretId") or ""),
        secret_key=str(raw.get("secretKey") or ""),
        token=str(raw.get("token") or ""),
        expires_at=float(raw.get("expiresAt") or 0),
        access_token=str(oauth.get("accessToken") or ""),
        access_expires_at=float(oauth.get("expiresAt") or 0),
        refresh_token=str(oauth.get("refreshToken") or ""),
        open_id=str(oauth.get("openId") or ""),
        site=str(oauth.get("site") or "cn"),
    )
    if not credential.secret_id or not credential.secret_key:
        raise CloudError("tccli 凭证缺少 SecretId/SecretKey")
    return credential
