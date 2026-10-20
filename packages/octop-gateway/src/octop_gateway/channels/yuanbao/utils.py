"""Utility helpers for Yuanbao channel media, URLs, and signatures."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import mimetypes
import posixpath
import struct
import urllib.parse
from collections.abc import Mapping
from typing import Any

from octop_gateway.channels.yuanbao.constants import DEFAULT_API_DOMAIN, DEFAULT_WS_URL, MSG_TYPE_TEXT
from octop_gateway.models import AudioContent, ContentPart, FileContent, ImageContent, VideoContent


def _compute_signature(app_secret: str, nonce: str, timestamp: str, app_key: str) -> str:
    plain = nonce + timestamp + app_key + app_secret
    digest = hmac.new(app_secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def _normalize_http_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return DEFAULT_API_DOMAIN
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


def _normalize_ws_url(value: str) -> str:
    value = value.strip()
    if not value:
        return DEFAULT_WS_URL
    if value.startswith("https://"):
        return "wss://" + value.removeprefix("https://")
    if value.startswith("http://"):
        return "ws://" + value.removeprefix("http://")
    if not value.startswith(("ws://", "wss://")):
        return f"wss://{value}"
    return value


def _first_media_url(content: Mapping[str, Any], *, api_domain: str) -> str:
    url = _normalize_media_url(str(content.get("url") or ""), api_domain=api_domain)
    if url:
        return url
    images = content.get("image_info_array")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, Mapping) and item.get("url"):
                return _normalize_media_url(str(item["url"]), api_domain=api_domain)
    sound = _normalize_media_url(str(content.get("sound") or ""), api_domain=api_domain)
    if sound:
        return sound
    return ""


def _first_image_info(content: Mapping[str, Any]) -> Mapping[str, Any]:
    images = content.get("image_info_array")
    if not isinstance(images, list):
        return {}
    if len(images) > 1 and isinstance(images[1], Mapping):
        return images[1]
    if images and isinstance(images[0], Mapping):
        return images[0]
    return {}


def _content_filename(content: Mapping[str, Any]) -> str:
    return str(content.get("file_name") or content.get("fileName") or content.get("filename") or "")


def _normalize_media_url(value: str, *, api_domain: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("//"):
        return f"https:{value}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme:
        return value
    if value.startswith("/"):
        return f"{api_domain.rstrip('/')}{value}"
    return f"https://{value}"


def _resource_id_from_url(url: str) -> str:
    with contextlib.suppress(ValueError):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        resource_ids = query.get("resourceId") or query.get("resourceid") or []
        return str(resource_ids[0]).strip() if resource_ids else ""
    return ""


def _resolve_media_filename(part: ContentPart, mime_type: str) -> str:
    if isinstance(part, FileContent) and part.filename:
        return part.filename
    if isinstance(part, ImageContent):
        basename = _basename_from_url(part.url) if part.url else ""
        return basename or f"image{_mime_to_extension(mime_type, '.jpg')}"
    if isinstance(part, VideoContent):
        basename = _basename_from_url(part.url) if part.url else ""
        return basename or f"video{_mime_to_extension(mime_type, '.mp4')}"
    if isinstance(part, AudioContent):
        basename = _basename_from_url(part.url) if part.url else ""
        return basename or f"audio{_mime_to_extension(mime_type, '.mp3')}"
    basename = _basename_from_url(getattr(part, "url", "")) if getattr(part, "url", "") else ""
    return basename or f"file{_mime_to_extension(mime_type, '.bin')}"


def _basename_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    basename = posixpath.basename(path)
    return urllib.parse.unquote(basename)


def _guess_mime_type(filename_or_url: str) -> str:
    guessed, _ = mimetypes.guess_type(filename_or_url)
    return guessed or "application/octet-stream"


def _mime_to_extension(mime_type: str, default: str) -> str:
    if not mime_type:
        return default
    return mimetypes.guess_extension(mime_type) or default


def _parse_image_size(data: bytes) -> tuple[int, int]:
    return _parse_png_size(data) or _parse_gif_size(data) or _parse_jpeg_size(data) or _parse_webp_size(data) or (0, 0)


def _parse_png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


def _parse_gif_size(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 10 and data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    return None


def _parse_jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos < len(data) - 9:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xC0, 0xC2):
            height = struct.unpack(">H", data[pos + 5 : pos + 7])[0]
            width = struct.unpack(">H", data[pos + 7 : pos + 9])[0]
            return width, height
        if pos + 4 > len(data):
            return None
        pos += 2 + struct.unpack(">H", data[pos + 2 : pos + 4])[0]
    return None


def _parse_webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = struct.unpack("<I", data[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        width = data[24] | (data[25] << 8) | (data[26] << 16)
        height = data[27] | (data[28] << 8) | (data[29] << 16)
        return width + 1, height + 1
    return None


def _cos_sign(
    *,
    method: str,
    path: str,
    params: Mapping[str, str],
    headers: Mapping[str, str],
    secret_id: str,
    secret_key: str,
    start_time: int,
    expire_seconds: int,
) -> str:
    sign_time = f"{start_time};{start_time + expire_seconds}"
    sign_key = hmac.new(secret_key.encode("utf-8"), sign_time.encode("utf-8"), hashlib.sha1).hexdigest()
    sorted_params = sorted((key.lower(), urllib.parse.quote(str(value), safe="")) for key, value in params.items())
    sorted_headers = sorted((key.lower(), urllib.parse.quote(str(value), safe="")) for key, value in headers.items())
    param_keys = ";".join(key for key, _ in sorted_params)
    param_string = "&".join(f"{key}={value}" for key, value in sorted_params)
    header_keys = ";".join(key for key, _ in sorted_headers)
    header_string = "&".join(f"{key}={value}" for key, value in sorted_headers)
    http_string = "\n".join([method.lower(), path, param_string, header_string, ""])
    string_to_sign = "\n".join(["sha1", sign_time, hashlib.sha1(http_string.encode("utf-8")).hexdigest(), ""])
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()
    return (
        "q-sign-algorithm=sha1"
        f"&q-ak={secret_id}"
        f"&q-sign-time={sign_time}"
        f"&q-key-time={sign_time}"
        f"&q-header-list={header_keys}"
        f"&q-url-param-list={param_keys}"
        f"&q-signature={signature}"
    )


def _single_text_body_text(msg_body: list[dict[str, Any]]) -> str | None:
    if len(msg_body) != 1:
        return None
    element = msg_body[0]
    if element.get("msg_type") != MSG_TYPE_TEXT:
        return None
    content = element.get("msg_content")
    if not isinstance(content, Mapping):
        return None
    text = content.get("text")
    return str(text) if text is not None else None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    with contextlib.suppress(TypeError, ValueError):
        return int(value)
    return None


def _redact_account(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"
