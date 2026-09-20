"""通道凭据：从配置文件收集（原 ybb_gates.py 的裁剪版）。

删掉的部分是 octop 专属：jwt 签发、面板开关查询、从 octop.db 的 channels 表读凭据、
OctopApi 停用内置通道——octop 已定调永不再装（2026-09-15）。

留下的是凭据本身与三种给法：config.json 的 credentials[]（多套）、单套 appKey/appSecret、
环境变量（只给 key，secret 必须进配置文件）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import logging


YUANBAO_KIND = "yuanbao"
KIMI_KIND = "kimi"
SUPPORTED_KINDS = (YUANBAO_KIND, KIMI_KIND)


@dataclass
class ChannelCred:
    """一条通道的凭据与寻址信息（原样承载，不做策略判断）。"""

    name: str
    agent_id: str
    app_key: str = ""
    app_secret: str = ""
    bot_names: list[str] = field(default_factory=list)
    api_domain: str = ""
    ws_url: str = ""
    enabled: bool = True
    channel_id: str = ""       # ULID，停内置通道时要用
    source: str = ""           # 凭据来自哪：config / credentials[] / env
    kind: str = YUANBAO_KIND   # 通道类型：yuanbao | kimi
    token: str = ""            # kimi 的 bot token（yuanbao 不用）
    state_dir: str = ""        # kimi 的独占状态目录（游标/订阅锁；yuanbao 不用）

    def masked(self) -> str:
        if self.kind == KIMI_KIND:
            return (f"{self.name} kind=kimi agent={self.agent_id} "
                    f"token={self.token[:6]}…（长度 {len(self.token)}）state={self.state_dir}")
        return (f"{self.name} kind=yuanbao agent={self.agent_id} key={self.app_key[:6]}… "
                f"bot_names={self.bot_names}")



def creds_from_config(app_key: str, app_secret: str, agent_id: str,
                      bot_names: list[str] | None = None,
                      api_domain: str = "", ws_url: str = "") -> ChannelCred:
    """config.json 手填的单套凭据（appKey/appSecret）。"""
    return ChannelCred(
        name="config", agent_id=agent_id, app_key=app_key, app_secret=app_secret,
        bot_names=bot_names or [], api_domain=api_domain, ws_url=ws_url,
        enabled=False, source="config")



def creds_from_list(items: list, log: Callable[[str], None] = lambda m: None
                    ) -> list[ChannelCred]:
    """config.json 的 `credentials` 段：一个机器人一条（多机器人协作必须走它）。

    为什么要这一段：单个 appKey/appSecret 只能接一个机器人，而"群里两个机器人各管一段"
    是真实用法（各有一套 agentId 与人格）。多套凭据只能走这里。

    一条凭据的 kind 决定它是哪个通道：
      * kind 缺省/yuanbao：要 appKey + appSecret
      * kind=kimi：要 token（bot token），stateDir 建议显式给（缺省按 agent 派生）
    半条凭据是配置错误而不是"还没配"：必须点名说清是哪一条、缺什么，绝不静默少一个机器人。
    """
    out: list[ChannelCred] = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            log(f"警告：credentials[{i}] 不是对象，跳过（应为 {{agentId, appKey, appSecret}} "
                f"或 {{kind: kimi, agentId, token}}）")
            continue
        kind = str(item.get("kind") or YUANBAO_KIND).strip().lower()
        where = f"credentials[{i}]（agentId={item.get('agentId') or '未写'}）"
        if kind not in SUPPORTED_KINDS:
            log(f"警告：{where} 的 kind={kind!r} 不认识（只支持 {'/'.join(SUPPORTED_KINDS)}），跳过")
            continue
        if kind == KIMI_KIND:
            token = str(item.get("token") or item.get("botToken") or "")
            if not token:
                log(f"警告：{where} 是 kimi 通道但缺 token，跳过这一条")
                continue
            names = token_names = item.get("botNames") or []
            if isinstance(names, str):
                names = [x.strip() for x in names.split(",") if x.strip()]
            out.append(ChannelCred(
                name=str(item.get("name") or f"kimi[{i}]"),
                agent_id=str(item.get("agentId") or ""),
                bot_names=[str(x).strip() for x in names if str(x).strip()],
                kind=KIMI_KIND, token=token,
                state_dir=str(item.get("stateDir") or ""),
                enabled=False, source=f"config.credentials[{i}]"))
            continue
        key = str(item.get("appKey") or "")
        secret = str(item.get("appSecret") or "")
        if not key or not secret:
            log(f"警告：{where} 缺 appKey 或 appSecret，跳过这一条")
            continue
        names = item.get("botNames") or item.get("botNames".lower()) or []
        if isinstance(names, str):
            names = [x.strip() for x in names.split(",") if x.strip()]
        out.append(ChannelCred(
            name=str(item.get("name") or f"config[{i}]"),
            agent_id=str(item.get("agentId") or ""),
            kind=YUANBAO_KIND,
            app_key=key, app_secret=secret,
            bot_names=[str(x).strip() for x in names if str(x).strip()],
            api_domain=str(item.get("apiDomain") or ""),
            ws_url=str(item.get("wsUrl") or ""),
            enabled=False, source=f"config.credentials[{i}]"))
    return out



def collect_credentials(cfg, log: Callable[[str], None] = lambda m: None) -> list[ChannelCred]:
    """把两路来源（config 手填一对 + credentials[]）合成不重复清单，不做 agent 过滤。

    过滤交给 select_credentials：体检需要「配置里有但都被过滤掉了」这个事实来说话，
    在这一步就筛掉会让报错文案只能写「没有凭据」。
    """
    out: list[ChannelCred] = []
    if cfg.app_key and cfg.app_secret:
        out.append(creds_from_config(
            cfg.app_key, cfg.app_secret, cfg.agent_id, cfg.bot_names(),
            cfg.api_domain, cfg.ws_url))
    for c in creds_from_list(getattr(cfg, "credentials", None), log):
        if not any(x.app_key == c.app_key for x in out):       # 同一机器人写两处只算一次
            out.append(c)
    return out
