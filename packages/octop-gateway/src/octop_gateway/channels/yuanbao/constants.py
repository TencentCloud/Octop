"""Constants for the Tencent Yuanbao channel."""

from __future__ import annotations

from datetime import timedelta, timezone

DEFAULT_API_DOMAIN = "https://bot.yuanbao.tencent.com"
DEFAULT_WS_URL = "wss://bot-wss.yuanbao.tencent.com/wss/connection"
SIGN_TOKEN_PATH = "/api/v5/robotLogic/sign-token"

MODULE_CONN_ACCESS = "conn_access"
MODULE_BIZ = "yuanbao_openclaw_proxy"

CMD_AUTH_BIND = "auth-bind"
CMD_PING = "ping"
CMD_KICKOUT = "kickout"
CMD_UPDATE_META = "update-meta"
CMD_INBOUND_MESSAGE = "inbound_message"
CMD_SEND_C2C_MESSAGE = "send_c2c_message"
CMD_SEND_GROUP_MESSAGE = "send_group_message"
CMD_SEND_PRIVATE_HEARTBEAT = "send_private_heartbeat"
CMD_SEND_GROUP_HEARTBEAT = "send_group_heartbeat"

CALLBACK_C2C_SEND_MSG = "C2C.CallbackAfterSendMsg"
CALLBACK_GROUP_SEND_MSG = "Group.CallbackAfterSendMsg"

MSG_TYPE_TEXT = "TIMTextElem"
MSG_TYPE_IMAGE = "TIMImageElem"
MSG_TYPE_FILE = "TIMFileElem"
MSG_TYPE_SOUND = "TIMSoundElem"
MSG_TYPE_VIDEO = "TIMVideoFileElem"

CMD_TYPE_REQUEST = 0
CMD_TYPE_RESPONSE = 1
CMD_TYPE_PUSH = 2
CMD_TYPE_PUSH_ACK = 3

RET_SUCCESS = 0
RET_ALREADY_AUTH = 41101
TOKEN_EXPIRED_CODES = {41103, 41104, 41108}

HEARTBEAT_RUNNING = 1
HEARTBEAT_FINISH = 2
HERMES_INSTANCE_ID = 17

WT_VARINT = 0
WT_LEN = 2

_MIME_TO_IMAGE_FORMAT = {
    "image/jpeg": 1,
    "image/jpg": 1,
    "image/gif": 2,
    "image/png": 3,
    "image/bmp": 4,
}
_CST = timezone(timedelta(hours=8), name="CST")
_TOKEN_REFRESH_MARGIN_SECONDS = 300
_INBOUND_DEDUPE_TTL_SECONDS = 300.0
_UPLOAD_INFO_PATH = "/api/resource/genUploadInfo"
_RESOURCE_DOWNLOAD_PATH = "/api/resource/v1/download"
_MAX_MEDIA_SIZE_BYTES = 50 * 1024 * 1024
