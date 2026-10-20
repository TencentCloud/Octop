"""Yuanbao ConnMsg and TIM message protocol helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from octop_gateway.channels.yuanbao.constants import (
    _MIME_TO_IMAGE_FORMAT,
    CALLBACK_C2C_SEND_MSG,
    CALLBACK_GROUP_SEND_MSG,
    CMD_AUTH_BIND,
    CMD_INBOUND_MESSAGE,
    CMD_KICKOUT,
    CMD_PING,
    CMD_SEND_C2C_MESSAGE,
    CMD_SEND_GROUP_HEARTBEAT,
    CMD_SEND_GROUP_MESSAGE,
    CMD_SEND_PRIVATE_HEARTBEAT,
    CMD_TYPE_PUSH,
    CMD_TYPE_PUSH_ACK,
    CMD_TYPE_REQUEST,
    CMD_TYPE_RESPONSE,
    CMD_UPDATE_META,
    DEFAULT_API_DOMAIN,
    DEFAULT_WS_URL,
    HEARTBEAT_FINISH,
    HEARTBEAT_RUNNING,
    HERMES_INSTANCE_ID,
    MODULE_BIZ,
    MODULE_CONN_ACCESS,
    MSG_TYPE_FILE,
    MSG_TYPE_IMAGE,
    MSG_TYPE_SOUND,
    MSG_TYPE_TEXT,
    MSG_TYPE_VIDEO,
    RET_ALREADY_AUTH,
    RET_SUCCESS,
    SIGN_TOKEN_PATH,
    TOKEN_EXPIRED_CODES,
    WT_LEN,
    WT_VARINT,
)

# Yuanbao TIM message elements are vendor-defined dynamic maps: each
# ``msg_type`` owns a different nested content shape, and new keys can appear
# without a gateway release. ``Any`` is intentionally confined to these aliases
# at the protocol boundary; channel code normalizes values before use.
type YuanbaoProtocolValue = Any
type YuanbaoMapping = Mapping[str, YuanbaoProtocolValue]
type YuanbaoDict = dict[str, YuanbaoProtocolValue]
type YuanbaoMessageElement = YuanbaoDict
type YuanbaoMessageBody = list[YuanbaoMessageElement]

__all__ = [
    "CALLBACK_C2C_SEND_MSG",
    "CALLBACK_GROUP_SEND_MSG",
    "CMD_AUTH_BIND",
    "CMD_INBOUND_MESSAGE",
    "CMD_KICKOUT",
    "CMD_PING",
    "CMD_SEND_C2C_MESSAGE",
    "CMD_SEND_GROUP_HEARTBEAT",
    "CMD_SEND_GROUP_MESSAGE",
    "CMD_SEND_PRIVATE_HEARTBEAT",
    "CMD_TYPE_PUSH",
    "CMD_TYPE_PUSH_ACK",
    "CMD_TYPE_REQUEST",
    "CMD_TYPE_RESPONSE",
    "CMD_UPDATE_META",
    "DEFAULT_API_DOMAIN",
    "DEFAULT_WS_URL",
    "HEARTBEAT_FINISH",
    "HEARTBEAT_RUNNING",
    "HERMES_INSTANCE_ID",
    "MODULE_BIZ",
    "MODULE_CONN_ACCESS",
    "MSG_TYPE_FILE",
    "MSG_TYPE_IMAGE",
    "MSG_TYPE_SOUND",
    "MSG_TYPE_TEXT",
    "MSG_TYPE_VIDEO",
    "RET_ALREADY_AUTH",
    "RET_SUCCESS",
    "SIGN_TOKEN_PATH",
    "TOKEN_EXPIRED_CODES",
    "WT_LEN",
    "WT_VARINT",
    "_bytes",
    "_field",
    "_fields_to_dict",
    "_get_bytes",
    "_get_string",
    "_get_varint",
    "_message",
    "_parse_fields",
    "_string",
    "_varint",
    "build_file_msg_body",
    "build_image_msg_body",
    "decode_conn_msg",
    "decode_status_response",
    "encode_auth_bind_payload",
    "encode_c2c_message_payload",
    "encode_group_heartbeat_payload",
    "encode_group_message_payload",
    "encode_private_heartbeat_payload",
    "encode_push_ack",
    "encode_request",
    "encode_text_body",
]


def encode_request(cmd: str, module: str, msg_id: str, seq_no: int, payload: bytes = b"") -> bytes:
    """Encode a Yuanbao ConnMsg request."""
    return _encode_conn_msg(
        cmd_type=CMD_TYPE_REQUEST,
        cmd=cmd,
        seq_no=seq_no,
        msg_id=msg_id,
        module=module,
        payload=payload,
    )


def encode_push_ack(head: YuanbaoMapping, seq_no: int) -> bytes:
    """Acknowledge a pushed ConnMsg when the server asks for an ACK."""
    return _encode_conn_msg(
        cmd_type=CMD_TYPE_PUSH_ACK,
        cmd=str(head.get("cmd") or ""),
        seq_no=seq_no,
        msg_id=str(head.get("msg_id") or ""),
        module=str(head.get("module") or ""),
    )


def decode_conn_msg(frame: bytes) -> YuanbaoDict:
    """Decode a binary WebSocket frame into a ConnMsg dict."""
    fields = _fields_to_dict(_parse_fields(frame))
    head_bytes = _get_bytes(fields, 1)
    data = _get_bytes(fields, 2)
    head = _decode_head(head_bytes) if head_bytes else {}
    return {"head": head, "data": data}


def encode_auth_bind_payload(
    *,
    bot_id: str,
    source: str,
    token: str,
    route_env: str = "",
    app_version: str = "1.0.0",
    app_operation_system: str = "",
    operation_system: str = "linux",
    bot_version: str = "1.0.0",
    instance_id: str = str(HERMES_INSTANCE_ID),
) -> bytes:
    """Encode AuthBindReq payload."""
    selected_operation_system = app_operation_system or operation_system
    auth_info = (
        _field(1, WT_LEN, _string(bot_id)) + _field(2, WT_LEN, _string(source)) + _field(3, WT_LEN, _string(token))
    )

    device_info = b""
    if app_version:
        device_info += _field(1, WT_LEN, _string(app_version))
    if selected_operation_system:
        device_info += _field(2, WT_LEN, _string(selected_operation_system))
    if instance_id:
        device_info += _field(10, WT_LEN, _string(instance_id))
    if bot_version:
        device_info += _field(24, WT_LEN, _string(bot_version))

    payload = (
        _field(1, WT_LEN, _string("ybBot"))
        + _field(2, WT_LEN, _message(auth_info))
        + _field(3, WT_LEN, _message(device_info))
    )
    if route_env:
        payload += _field(5, WT_LEN, _string(route_env))
    return payload


def decode_status_response(payload: bytes) -> tuple[int, str]:
    """Decode simple Yuanbao response payloads that expose code/message."""
    if not payload:
        return RET_SUCCESS, ""
    fields = _fields_to_dict(_parse_fields(payload))
    return _get_varint(fields, 1), _get_string(fields, 2)


def encode_text_body(text: str) -> YuanbaoMessageBody:
    return [{"msg_type": MSG_TYPE_TEXT, "msg_content": {"text": text}}]


def build_image_msg_body(
    *,
    url: str,
    uuid: str = "",
    filename: str = "",
    size: int = 0,
    width: int = 0,
    height: int = 0,
    mime_type: str = "",
) -> YuanbaoMessageBody:
    """Build a Yuanbao TIMImageElem body from an uploaded public URL."""
    image_uuid = uuid or filename or "image"
    image_format = _MIME_TO_IMAGE_FORMAT.get(mime_type.lower(), 255) if mime_type else 255
    return [
        {
            "msg_type": MSG_TYPE_IMAGE,
            "msg_content": {
                "uuid": image_uuid,
                "image_format": image_format,
                "image_info_array": [
                    {
                        "type": 1,
                        "size": size,
                        "width": width,
                        "height": height,
                        "url": url,
                    }
                ],
            },
        }
    ]


def build_file_msg_body(
    *,
    url: str,
    filename: str,
    uuid: str = "",
    size: int = 0,
) -> YuanbaoMessageBody:
    """Build a Yuanbao TIMFileElem body from an uploaded public URL."""
    return [
        {
            "msg_type": MSG_TYPE_FILE,
            "msg_content": {
                "uuid": uuid or filename,
                "file_name": filename,
                "file_size": size,
                "url": url,
            },
        }
    ]


def encode_c2c_message_payload(
    *,
    to_account: str,
    from_account: str,
    msg_body: YuanbaoMessageBody,
    msg_id: str = "",
    msg_random: int = 0,
    msg_seq: int | None = None,
    group_code: str = "",
    trace_id: str = "",
) -> bytes:
    """Encode SendC2CMessageReq payload."""
    payload = b""
    if msg_id:
        payload += _field(1, WT_LEN, _string(msg_id))
    payload += _field(2, WT_LEN, _string(to_account))
    if from_account:
        payload += _field(3, WT_LEN, _string(from_account))
    if msg_random:
        payload += _field(4, WT_VARINT, _varint(msg_random))
    for element in msg_body:
        payload += _field(5, WT_LEN, _message(_encode_msg_body_element(element)))
    if group_code:
        payload += _field(6, WT_LEN, _string(group_code))
    if msg_seq is not None:
        payload += _field(7, WT_VARINT, _varint(msg_seq))
    if trace_id:
        payload += _field(8, WT_LEN, _message(_encode_log_ext(trace_id)))
    return payload


def encode_group_message_payload(
    *,
    group_code: str,
    from_account: str,
    msg_body: YuanbaoMessageBody,
    msg_id: str = "",
    to_account: str = "",
    random: str = "",
    msg_seq: int | None = None,
    ref_msg_id: str = "",
    trace_id: str = "",
) -> bytes:
    """Encode SendGroupMessageReq payload."""
    payload = b""
    if msg_id:
        payload += _field(1, WT_LEN, _string(msg_id))
    payload += _field(2, WT_LEN, _string(group_code))
    if from_account:
        payload += _field(3, WT_LEN, _string(from_account))
    if to_account:
        payload += _field(4, WT_LEN, _string(to_account))
    if random:
        payload += _field(5, WT_LEN, _string(random))
    for element in msg_body:
        payload += _field(6, WT_LEN, _message(_encode_msg_body_element(element)))
    if ref_msg_id:
        payload += _field(7, WT_LEN, _string(ref_msg_id))
    if msg_seq is not None:
        payload += _field(8, WT_VARINT, _varint(msg_seq))
    if trace_id:
        payload += _field(9, WT_LEN, _message(_encode_log_ext(trace_id)))
    return payload


def encode_private_heartbeat_payload(from_account: str, to_account: str, heartbeat: int = HEARTBEAT_RUNNING) -> bytes:
    return (
        _field(1, WT_LEN, _string(from_account))
        + _field(2, WT_LEN, _string(to_account))
        + _field(3, WT_VARINT, _varint(heartbeat))
    )


def encode_group_heartbeat_payload(
    from_account: str,
    group_code: str,
    *,
    send_time: int,
    heartbeat: int = HEARTBEAT_RUNNING,
) -> bytes:
    return (
        _field(1, WT_LEN, _string(from_account))
        + _field(2, WT_LEN, _string(""))
        + _field(3, WT_LEN, _string(group_code))
        + _field(4, WT_VARINT, _varint(send_time))
        + _field(5, WT_VARINT, _varint(heartbeat))
    )


def _encode_msg_body_element(element: YuanbaoMapping) -> bytes:
    payload = b""
    msg_type = str(element.get("msg_type") or "")
    if msg_type:
        payload += _field(1, WT_LEN, _string(msg_type))
    content = element.get("msg_content")
    if isinstance(content, Mapping):
        payload += _field(2, WT_LEN, _message(_encode_msg_content(content)))
    return payload


def _encode_msg_content(content: YuanbaoMapping) -> bytes:
    payload = b""
    for field_no, key in (
        (1, "text"),
        (2, "uuid"),
        (4, "data"),
        (5, "desc"),
        (6, "ext"),
        (7, "sound"),
        (10, "url"),
        (12, "file_name"),
    ):
        value = content.get(key)
        if value:
            payload += _field(field_no, WT_LEN, _string(str(value)))
    for field_no, key in ((3, "image_format"), (9, "index"), (11, "file_size")):
        value = content.get(key)
        if value:
            payload += _field(field_no, WT_VARINT, _varint(int(value)))
    for image_info in content.get("image_info_array") or []:
        if not isinstance(image_info, Mapping):
            continue
        image_payload = b""
        for field_no, key in ((1, "type"), (2, "size"), (3, "width"), (4, "height")):
            value = image_info.get(key)
            if value:
                image_payload += _field(field_no, WT_VARINT, _varint(int(value)))
        url = image_info.get("url")
        if url:
            image_payload += _field(5, WT_LEN, _string(str(url)))
        if image_payload:
            payload += _field(8, WT_LEN, _message(image_payload))
    ext_map = content.get("ext_map")
    if isinstance(ext_map, Mapping):
        for key, value in ext_map.items():
            entry = _field(1, WT_LEN, _string(str(key))) + _field(2, WT_LEN, _string(str(value)))
            payload += _field(999, WT_LEN, _message(entry))
    return payload


def _encode_log_ext(trace_id: str) -> bytes:
    return _field(1, WT_LEN, _string(trace_id)) if trace_id else b""


def _encode_conn_msg(
    *,
    cmd_type: int,
    cmd: str,
    seq_no: int,
    msg_id: str,
    module: str,
    payload: bytes = b"",
) -> bytes:
    head = b""
    if cmd_type:
        head += _field(1, WT_VARINT, _varint(cmd_type))
    if cmd:
        head += _field(2, WT_LEN, _string(cmd))
    if seq_no:
        head += _field(3, WT_VARINT, _varint(seq_no))
    if msg_id:
        head += _field(4, WT_LEN, _string(msg_id))
    if module:
        head += _field(5, WT_LEN, _string(module))

    conn_msg = _field(1, WT_LEN, _message(head))
    if payload:
        conn_msg += _field(2, WT_LEN, _bytes(payload))
    return conn_msg


def _decode_head(payload: bytes) -> YuanbaoDict:
    fields = _fields_to_dict(_parse_fields(payload))
    return {
        "cmd_type": _get_varint(fields, 1),
        "cmd": _get_string(fields, 2),
        "seq_no": _get_varint(fields, 3),
        "msg_id": _get_string(fields, 4),
        "module": _get_string(fields, 5),
        "need_ack": bool(_get_varint(fields, 6)),
        "status": _get_varint(fields, 10),
    }


def _field(field_number: int, wire_type: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | wire_type) + value


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _varint(len(encoded)) + encoded


def _bytes(value: bytes) -> bytes:
    return _varint(len(value)) + value


def _message(value: bytes) -> bytes:
    return _bytes(value)


def _varint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift >= 64:
            raise ValueError("protobuf varint too long")
    raise ValueError("truncated protobuf varint")


def _parse_fields(data: bytes) -> list[tuple[int, int, bytes | int]]:
    fields: list[tuple[int, int, bytes | int]] = []
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == WT_VARINT:
            varint_value, pos = _read_varint(data, pos)
            fields.append((field_number, wire_type, varint_value))
        elif wire_type == WT_LEN:
            length, pos = _read_varint(data, pos)
            bytes_value = data[pos : pos + length]
            pos += length
            fields.append((field_number, wire_type, bytes_value))
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
    return fields


def _fields_to_dict(fields: list[tuple[int, int, bytes | int]]) -> dict[int, list[tuple[int, bytes | int]]]:
    out: dict[int, list[tuple[int, bytes | int]]] = {}
    for field_number, wire_type, value in fields:
        out.setdefault(field_number, []).append((wire_type, value))
    return out


def _get_string(fields: dict[int, list[tuple[int, bytes | int]]], field_number: int) -> str:
    entries = fields.get(field_number)
    if not entries:
        return ""
    wire_type, value = entries[0]
    if wire_type == WT_LEN and isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return ""


def _get_varint(fields: dict[int, list[tuple[int, bytes | int]]], field_number: int) -> int:
    entries = fields.get(field_number)
    if not entries:
        return 0
    wire_type, value = entries[0]
    if wire_type == WT_VARINT and isinstance(value, int):
        return value
    return 0


def _get_bytes(fields: dict[int, list[tuple[int, bytes | int]]], field_number: int) -> bytes:
    entries = fields.get(field_number)
    if not entries:
        return b""
    wire_type, value = entries[0]
    if wire_type == WT_LEN and isinstance(value, bytes):
        return value
    return b""
