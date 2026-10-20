"""Type definitions for WeChat iLink Bot API messages.

Wire format mirrors the working reference implementation: requests use
snake_case keys, responses come back camelCase. Pydantic models use
``populate_by_name=True`` with camelCase aliases so both shapes parse.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TextItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    text: str = ""


class CDNMedia(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    encrypt_query_param: str = Field(default="", alias="encryptQueryParam")
    aes_key: str = Field(default="", alias="aesKey")
    encrypt_type: int | None = Field(default=None, alias="encryptType")


class ImageItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    media: CDNMedia | None = None
    aeskey: str = ""
    url: str = ""


class VoiceItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    media: CDNMedia | None = None
    text: str = ""  # voice-to-text content


class FileItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    media: CDNMedia | None = None
    file_name: str = Field(default="", alias="fileName")
    url: str = ""


class VideoItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    media: CDNMedia | None = None
    url: str = ""


class MessageItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: int = 0
    text_item: TextItem | None = Field(default=None, alias="textItem")
    image_item: ImageItem | None = Field(default=None, alias="imageItem")
    voice_item: VoiceItem | None = Field(default=None, alias="voiceItem")
    file_item: FileItem | None = Field(default=None, alias="fileItem")
    video_item: VideoItem | None = Field(default=None, alias="videoItem")


class WeixinMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    seq: int | None = None
    message_id: int | None = Field(default=None, alias="messageId")
    from_user_id: str | None = Field(default=None, alias="fromUserId")
    to_user_id: str | None = Field(default=None, alias="toUserId")
    create_time_ms: int | None = Field(default=None, alias="createTimeMs")
    session_id: str | None = Field(default=None, alias="sessionId")
    message_type: int | None = Field(default=None, alias="messageType")
    message_state: int | None = Field(default=None, alias="messageState")
    item_list: list[MessageItem] | None = Field(default=None, alias="itemList")
    context_token: str | None = Field(default=None, alias="contextToken")


class GetUpdatesResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ret: int | None = None
    errcode: int | None = None
    errmsg: str | None = None
    msgs: list[WeixinMessage] = Field(default_factory=list)
    get_updates_buf: str = Field(default="", alias="getUpdatesBuf")
    longpolling_timeout_ms: int | None = Field(default=35000, alias="longpollingTimeoutMs")


class SendMessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ret: int | None = None
    message_id: int | None = Field(default=None, alias="messageId")
    context_token: str | None = Field(default=None, alias="contextToken")
    data: dict[str, Any] = Field(default_factory=dict)
    errcode: int | None = None
    errmsg: str | None = None


class GetConfigResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ret: int | None = None
    typing_ticket: str | None = Field(default=None, alias="typingTicket")
    errcode: int | None = None
    errmsg: str | None = None


class WeixinAPIError(Exception):
    """Raised when the WeChat iLink API returns a non-success code."""

    def __init__(self, ret: int, errcode: int | None = None, errmsg: str | None = None) -> None:
        self.ret = ret
        self.errcode = errcode
        self.errmsg = errmsg
        msg = f"WeChat API error: ret={ret}"
        if errcode is not None:
            msg += f", errcode={errcode}"
        if errmsg:
            msg += f", errmsg={errmsg}"
        super().__init__(msg)
