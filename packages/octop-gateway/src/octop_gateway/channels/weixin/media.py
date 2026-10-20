"""WeChat iLink media helpers.

The iLink Bot API sends media through an encrypted CDN flow:
1. ask iLink for an upload URL;
2. AES-128-ECB encrypt the bytes and POST them to that URL;
3. send the returned encrypted query param as an image/file/video item.

Inbound media follows the same scheme in reverse.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
from typing import Any
from urllib.parse import quote

import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

logger = logging.getLogger(__name__)

CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

_AES_BLOCK_BITS = 128
_MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024

_MAGIC_TABLE: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"%PDF", ".pdf"),
    (b"PK\x03\x04", ".zip"),
    (b"\x1aE\xdf\xa3", ".webm"),
    (b"ID3", ".mp3"),
    (b"\xff\xfb", ".mp3"),
    (b"\xff\xf3", ".mp3"),
    (b"\xff\xf2", ".mp3"),
    (b"#!AMR\n", ".amr"),
    (b"#!SILK_V3", ".silk"),
]


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    padder = PKCS7(_AES_BLOCK_BITS).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    padded = decryptor.update(data) + decryptor.finalize()
    unpadder = PKCS7(_AES_BLOCK_BITS).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def generate_aes_key() -> bytes:
    return os.urandom(16)


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def encrypted_size(raw_size: int) -> int:
    return raw_size + (16 - raw_size % 16)


def detect_extension(data: bytes) -> str:
    header = data[:32] if len(data) >= 32 else data
    for magic, ext in _MAGIC_TABLE:
        if header.startswith(magic):
            return ext
    if len(data) >= 12:
        if header.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        if header.startswith(b"RIFF") and data[8:12] == b"WAVE":
            return ".wav"
        if b"ftyp" in data[:12]:
            return ".mp4"
    return ".bin"


async def encrypt_and_upload(
    session: aiohttp.ClientSession,
    upload_url: str,
    data: bytes,
    key: bytes,
) -> str | None:
    try:
        encrypted = aes_ecb_encrypt(data, key)
    except (TypeError, ValueError):
        logger.exception("Weixin media encrypt failed")
        return None

    try:
        async with session.post(
            upload_url, data=encrypted, headers={"Content-Type": "application/octet-stream"}
        ) as resp:
            if resp.status not in (200, 201, 204):
                body = await resp.text()
                logger.warning("Weixin CDN upload failed: http=%s body=%.200s", resp.status, body)
                return None
            encrypted_param = resp.headers.get("x-encrypted-param", "")
            if not encrypted_param:
                logger.warning("Weixin CDN upload response missing x-encrypted-param")
                return None
            return encrypted_param
    except (aiohttp.ClientError, TimeoutError):
        logger.exception("Weixin CDN upload error")
        return None


def build_upload_url(upload_param: str, filekey: str) -> str:
    return (
        f"{CDN_BASE_URL}/upload?encrypted_query_param={quote(upload_param, safe='')}&filekey={quote(filekey, safe='')}"
    )


def build_download_url(encrypt_query_param: str) -> str:
    if not encrypt_query_param:
        return ""
    return f"{CDN_BASE_URL}/download?encrypted_query_param={quote(encrypt_query_param, safe='')}"


def decode_aes_key(value: str) -> bytes | None:
    if not value:
        return None
    try:
        raw = bytes.fromhex(value)
        return raw[:16] if len(raw) >= 16 else raw.ljust(16, b"\x00")
    except (TypeError, ValueError):
        pass
    try:
        decoded = base64.b64decode(value).decode("ascii")
        raw = bytes.fromhex(decoded)
        return raw[:16] if len(raw) >= 16 else raw.ljust(16, b"\x00")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


async def download_and_decrypt(
    session: aiohttp.ClientSession,
    cdn_media: dict[str, Any],
    extra_key: str = "",
) -> bytes | None:
    encrypt_param = str(cdn_media.get("encrypt_query_param") or cdn_media.get("encryptQueryParam") or "")
    if not encrypt_param:
        return None

    url = build_download_url(encrypt_param)
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.warning("Weixin CDN download failed: http=%s", resp.status)
                return None
            raw = await resp.read()
    except (aiohttp.ClientError, TimeoutError):
        logger.exception("Weixin CDN download error")
        return None

    if len(raw) > _MAX_DOWNLOAD_SIZE:
        logger.warning("Weixin CDN download too large: %d bytes", len(raw))
        return None

    key = decode_aes_key(extra_key) or decode_aes_key(str(cdn_media.get("aes_key") or cdn_media.get("aesKey") or ""))
    if not key or len(raw) % 16 != 0:
        return raw
    try:
        return aes_ecb_decrypt(raw, key)
    except (TypeError, ValueError):
        logger.warning("Weixin CDN decrypt failed; using raw bytes", exc_info=True)
        return raw
