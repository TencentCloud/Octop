"""nong-gateway 插件壳：把 N 个桥跑在 Octop 进程里。

设计要点（对应 skill 里踩过的坑，逐条有对策）：
1. 启动门：setup() 在 CLI 装包/重载进程里也会被执行——非 server 进程一概不起桥
   （判定依据写日志）。四档：NONGGW_FORCE_START > OCTOP_PLUGIN_HOST=server >
   模块表启发式 > 不起。
2. 看门狗：官方停用/卸载不通知插件（无 teardown）——每 5s 查 PluginRegistry，
   连续两次不在册即收线退出；带 20s 宽限期（加载器先 setup 后 register）；
   看门狗收 stop_event（wait 不是 sleep），热重载旧一代可退出，不泄漏。
3. 模块名全部 nonggw_ 前缀（全进程共享 sys.path，裸名撞车会先把邻居弄坏）。
4. 配置/状态放 ~/.nong-gateway（持久），绝不放插件目录（重装覆盖已丢过一次）。
5. 不调 ctx.tool()/ctx.middleware()/ctx.skills() —— 模型上下文零占用。
"""

from __future__ import annotations

import builtins as _b
import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger("nonggw.plugin")

PERSIST_HOME = Path(os.environ.get("NONGGW_HOME", str(Path.home() / ".nong-gateway")))
HERE = Path(__file__).resolve().parent
GENERATION = {"n": 0}


def _server_process() -> tuple[bool, str]:
    """是否 Octop server 进程（启动门，四档）。返回 (判定, 依据)。"""
    if os.environ.get("NONGGW_FORCE_START") == "1":
        return True, "NONGGW_FORCE_START=1"
    if os.environ.get("OCTOP_PLUGIN_HOST") == "server":
        return True, "OCTOP_PLUGIN_HOST=server"
    mods = sys.modules
    if "octop.infra.server" in mods or "uvicorn" in mods:
        return True, "模块表有 octop.infra.server/uvicorn"
    return False, "非 server 进程（CLI 装包/重载），不起桥"


def _add_src_to_path() -> None:
    """把包内 src/ 挂到 sys.path（进程级共享，前缀防撞）。

    同时清掉属于本插件目录的兄弟模块缓存：重装/重载后 sys.modules 里若还留着旧路径的
    nong_gateway.*，import 会命中缓存 → 磁盘新代码不生效（skill 文档第四节，实测踩过）。
    判定用 __file__ 是否在插件目录下，不写死模块名清单。
    """
    src = HERE / "src"
    s = str(src)
    roots = ("nong_gateway", "nonggw_kimi", "octop_host")
    for m in list(sys.modules):
        # 裸名与前缀都清：只清 "x.y" 前缀会漏掉裸 import（octop_host 本身），实测踩过——
        # 裸名不清 = 重载后宿主还是旧类，defer/帧协议全走旧代码，配置看着新行为却是旧的
        if m in roots or m.split(".")[0] in roots:
            sys.modules.pop(m, None)
    if s not in sys.path:
        sys.path.insert(0, s)


def _self_heal() -> list[str]:
    """升级自愈（octop pip 升级/重装后，setup 随服务启动自动跑，无需手工脚本）。

    三件修复，全部幂等：
    1. kimi 通道回植：pip 升级会覆盖 venv 的 harness_gateway（kimi 通道没了）——
       把插件 vendor 的 kimi 拷回去 + channels/__init__.py 三处注册表补上。
    2. 内置通道残留检测：channels 表 enabled=1 的 yuanbao/kimi 行 = 双消费者
       （昨天互答死循环的根）——自动置 0 并留痕（这是我们自己定义的策略，分发默认关）。
    3. 备份在位检查：venv-backup 若缺失则先备份官方包（回滚参照）。
    """
    done: list[str] = []
    import shutil
    import sqlite3

    vsp = Path("/data/wwlst/octop/venv/lib/python3.12/site-packages")
    hg = vsp / "harness_gateway"
    try:
        # ---- 1) kimi 通道回植 ----
        init_py = hg / "channels" / "__init__.py"
        if hg.is_dir() and init_py.is_file() and '"kimi"' not in init_py.read_text(encoding="utf-8"):
            src_kimi = HERE / "src" / "nonggw_kimi"
            dst_kimi = hg / "channels" / "kimi"
            if src_kimi.is_dir():
                if dst_kimi.exists():
                    shutil.rmtree(dst_kimi)
                shutil.copytree(src_kimi, dst_kimi)
                reg = init_py.read_text(encoding="utf-8")
                reg = reg.replace(
                    '_CHANNEL_MAP: dict[str, str] = {',
                    '_CHANNEL_MAP: dict[str, str] = {\n    "kimi": "harness_gateway.channels.kimi",')
                reg = reg.replace(
                    '    FEISHU = "feishu"',
                    '    KIMI = "kimi"\n    FEISHU = "feishu"')
                reg = reg.replace(
                    '    "feishu": "FeishuChannel",',
                    '    "kimi": "KimiChannel",\n    "feishu": "FeishuChannel",')
                init_py.write_text(reg, encoding="utf-8")
                done.append("kimi 通道已回植（venv 被升级覆盖过）")
    except Exception as exc:                                   # noqa: BLE001
        done.append(f"kimi 回植失败（不影响元宝）: {exc}")
    try:
        # ---- 2) 内置通道：劫持（hijackBuiltin=true）或自动停用（缺省）----
        # 劫持：UI 通道页"启用"= 官方通道连接平台，但消息处理被桥接管（processor 替换 + 出站编码绑定）
        #      ——扫码绑定/启用全走官方 UI，双消费者消失（单连接）。
        # 停用（分发缺省）：enabled=1 的 yuanbao/kimi 行自动置 0（防双消费者）。
        import json as _json
        cfg_path = PERSIST_HOME / "config.json"
        hijack = False
        try:
            hijack = bool((_json.loads(cfg_path.read_text(encoding="utf-8"))
                           .get("hijackBuiltin")))
        except Exception:                                      # noqa: BLE001
            pass
        db = Path(os.environ.get("OCTOP_HOME", "/data/wwlst/octop")) / "octop.db"
        con = sqlite3.connect(db, timeout=5)
        try:
            rows = con.execute(
                "SELECT channel_id, agent_id, kind FROM channels WHERE enabled=1").fetchall()
            for cid, agent, kind in rows:
                if kind not in ("yuanbao", "kimi"):
                    continue
                if hijack:
                    # 不停用，交给后台劫持线程（等通道注册完成后接管）
                    done.append(f"内置 {kind} 通道（agent={agent}）待劫持（后台接管）")
                    _spawn_hijack(cid, agent)
                else:
                    con.execute("UPDATE channels SET enabled=0 WHERE channel_id=?", (cid,))
                    done.append(f"内置 {kind} 通道残留已自动停用（agent={agent}，防双消费者）")
            con.commit()
        finally:
            con.close()
    except Exception as exc:                                   # noqa: BLE001
        done.append(f"内置通道检查失败: {exc}")
    try:
        # ---- 3) 官方包备份在位 ----
        bdir = Path("/data/wwlst/venv-backup")
        if hg.is_dir() and not any(bdir.glob("harness-gateway-official-*.tgz")):
            bdir.mkdir(parents=True, exist_ok=True)
            import subprocess
            subprocess.run(["tar", "czf", str(bdir / "harness-gateway-official-auto.tgz"),
                            "-C", str(vsp), "harness_gateway", "harness_gateway-0.9.7.dist-info"],
                           check=False)
            done.append("官方 harness_gateway 已自动备份")
    except Exception as exc:                                   # noqa: BLE001
        done.append(f"备份失败: {exc}")
    return done


def _spawn_hijack(channel_id: str, agent_id: str) -> None:
    """后台劫持线程：等 gateway 注册该通道实例，然后接管消息处理。

    接管动作（全部运行时绑定，不落盘、升级安全）：
    1. ch._processor = 桥的 process（四道闸/群策略/别名/白名单全生效）
    2. ch._send_text = 出站编码版（@名字 → 结构化 at 元素）
    3. 桥侧该凭据跳过自建 WS（config hijackedAgents 告诉 BridgeRunner）
    UI 通道页"停用"= unload 该通道 → 桥需要恢复自建连接（此处从简：重启服务/reload 插件即可，
    看门狗会重启桥线程；劫持线程发现通道消失则退出）。
    """
    import types as _types
    import time as _time

    def _find_octop_server():
        """进程内找 OctopServer 实例（app.state 不可达，走 gc 扫描；一次性，结果缓存）。

        缓存到 builtins：热重载后重新扫描（对象可能是新实例）。
        """
        cached = getattr(_b, "nonggw_octop_server", None)
        if cached is not None:
            return cached
        import gc
        for o in gc.get_objects():
            if type(o).__name__ == "OctopServer":
                rt = getattr(o, "app_runtime", None)
                if rt is not None and getattr(rt, "gateway", None) is not None:
                    _b.nonggw_octop_server = o
                    return o
        return None

    def _run(stop_evt: "threading.Event") -> None:
        import json as _json_mod
        # 桥线程先起（BridgeRunner 在 setup 里启动）——从 builtins 拿到 runner
        for _ in range(60):
            if stop_evt.is_set():
                log.info("[nong-gateway] 劫持线程收到退出信号（换新代），放弃")
                return
            r = getattr(_b, "nonggw_runner_ref", None)
            if r is not None:
                break
            _time.sleep(1)
        runner = getattr(_b, "nonggw_runner_ref", None)
        if runner is None:
            log.warning("[nong-gateway] 劫持失败：runner 不可用（%s/%s）", agent_id, channel_id)
            return
        # 通道注册在 **octop gateway 的 ChannelManager**（不是桥自己的 runner._manager——
        # 劫持形态下桥的 manager 是空的，首轮实测找错对象 60s 超时）
        ch = None
        for _ in range(60):
            if stop_evt.is_set():
                log.info("[nong-gateway] 劫持线程收到退出信号（换新代），放弃")
                return
            srv = _find_octop_server()
            m = None
            if srv is not None:
                rt = getattr(srv, "app_runtime", None)
                gw = getattr(rt, "gateway", None) if rt is not None else None
                m = getattr(gw, "channel_manager", None) if gw is not None else None
            if m is not None:
                try:
                    ch = m.get_channel(channel_id)
                except Exception:
                    ch = None
                if ch is not None:
                    break
            _time.sleep(1)
        if ch is None:
            log.warning("[nong-gateway] 劫持失败：通道 %s 未注册（60s，octop gateway）", channel_id)
            return
        # 桥的 process（该 agent 的 Bridge 实例）——runner.bridges 在 prepare() 里才填，
        # 劫持线程可能先跑到这（实测："桥不存在"竞态）→ 等一会儿再查
        bridge = None
        for _ in range(30):
            if stop_evt.is_set():
                return
            bridge = next((x for x in (runner.bridges or []) if x.policy.agent_id == agent_id), None)
            if bridge is not None:
                break
            _time.sleep(1)
        if bridge is None:
            log.warning("[nong-gateway] 劫持失败：agent %s 的桥不存在（30s；检查 hijackedAgents 与 credentials）", agent_id)
            return
        # 0) bot_mentioned 标记（照 QQ 通道语义，见 channels/qq/channel.py:1055）——
        #    官方 GroupContextManager 依据它做 mention 过滤（channel.py:204），
        #    元宝原生 parse 没设这个标记，导致 group_context 对元宝不生效（QQ 有、元宝无）。
        #    在原生 _parse_yuanbao_message 外包一层：结构化 at 的 user_id 精确比对 own bot_id。
        orig_parse = ch._parse_yuanbao_message

        def _parse_with_mention(data):
            msg = orig_parse(data)
            try:
                raw_at = []
                for body_el in (data.get("msg_body") or []):
                    if str(body_el.get("msg_type")) == "TIMCustomElem":
                        cdata = (body_el.get("msg_content") or {}).get("data")
                        try:
                            elem = _json_mod.loads(cdata) if isinstance(cdata, str) else None
                        except Exception:
                            elem = None
                        if isinstance(elem, dict) and elem.get("elem_type") == 1002:
                            raw_at.append(elem)
                own = str(getattr(ch, "_bot_id", "") or "")
                if raw_at:
                    # 学名字+id：出站 at 编码的 targets 需要**当前群里真实 bot 的完整 id**
                    # （mentionTargets 旧 id 在 bot 重建后失效——动态学习覆盖）
                    for e in raw_at:
                        nm = str(e.get("text") or "").lstrip("@").strip()
                        uid = str(e.get("user_id") or "")
                        if nm and uid:
                            try:
                                bridge._learned_mentions[nm] = uid
                            except Exception:
                                pass
                    log.info("[nong-gateway] at 帧学习: %s", [(str(e.get('text')), str(e.get('user_id'))[:24]) for e in raw_at])
                    # 把 at 条目补进 metadata（字段名与 ProbeChannel/桥自建连接形态对齐）：
                    # process 里的 at 判定读 meta["kcb_at_bots"]，劫持形态下官方通道不填它，
                    # 不补就会退到名字兜底——名字表里只有平台助手名，@本机器人 被误判为“未被 at”。
                    msg.metadata["kcb_at_bots"] = raw_at
                if any(str(e.get("user_id") or "") == own for e in raw_at):
                    msg.metadata["bot_mentioned"] = True
            except Exception as exc:                            # noqa: BLE001
                log.warning("[nong-gateway] bot_mentioned 标记失败: %s", exc)
            # 群消息落盘（可检索）在 parse 层做：这里能看到**所有**入站消息——
            # 包括后面被 GroupContext 吞掉的非 @ 消息（process 收不到它们，账本不能漏）
            try:
                import json as _j2
                from nong_gateway.outbound_mentions import build_targets
                subj = msg.channel_subject
                subject_id = (subj.subject_id if subj else "") or "unknown"
                meta = msg.metadata or {}
                fa = str(meta.get("from_account") or "")
                nick = str(subj.display_name or meta.get("sender_nickname") or fa) if subj else fa
                own = str(getattr(ch, "_bot_id", "") or "")
                botish = fa.startswith("bot_") or (own and fa == own) \
                    or fa in set(build_targets(getattr(bridge.cfg, "mention_targets", None) or {},
                                              lambda: getattr(bridge, "_learned_mentions", {}) or {}).values())
                # 落盘范围（per-agent groupLogScope）：human=只记人；all=人+机器人
                scope = str(getattr(bridge.policy, "group_log_scope", "human") or "human").lower()
                if botish and scope != "all":
                    return msg          # 机器人消息不入账本（只记人）
                if str(getattr(bridge.policy, "group_log_mode", "off") or "off").lower() != "md":
                    return msg          # 该 agent 未开启落盘
                items = [m if isinstance(m, dict) else {} for m in (msg.content or [])]
                medias = [x for x in items if x.get("url")]
                import inspect as _insp
                try:
                    sigp = _insp.signature(bridge.group_log_append)
                    if "is_bot" in sigp.parameters:
                        bridge.group_log_append(subject_id, nick,
                                                str(getattr(msg, "text", "") or ""),
                                                str(meta.get("msg_id") or ""), medias,
                                                is_bot=botish)
                    else:
                        bridge.group_log_append(subject_id, nick,
                                                str(getattr(msg, "text", "") or ""),
                                                str(meta.get("msg_id") or ""), medias)
                except (ValueError, TypeError):
                    # 参数不匹配时降级为不带 is_bot（账本照记，标注可能缺）
                    bridge.group_log_append(subject_id, nick,
                                            str(getattr(msg, "text", "") or ""),
                                            str(meta.get("msg_id") or ""), medias)
            except Exception as exc:                            # noqa: BLE001
                import inspect as _insp
                log.warning("[nong-gateway] 群消息落盘失败: %s | bridge=%s 方法=%s 闭包bridge_id=%s",
                            exc, type(bridge).__name__,
                            _insp.signature(bridge.group_log_append) if hasattr(bridge, "group_log_append") else "N/A",
                            id(bridge))
            return msg

        ch._parse_yuanbao_message = _parse_with_mention
        # -1) 动态修正出站 targets：通道自己的 bot_id 是**当前真实 id**（bot 重建后 auth-bind 返回），
        #     覆盖 mentionTargets 里的旧 id（昵称取 config.credentials 的 botNames——这里用 agent 名映射）。
        try:
            own = str(getattr(ch, "_bot_id", "") or "")
            if own:
                bridge._learned_mentions[str(bridge.policy.agent_id)] = own
                bridge._learned_mentions["主理人" if agent_id == "main" else "分身助手"] = own
        except Exception:                                       # noqa: BLE001
            pass
        # 0.5) 群聊策略（照 QQ 渠道的 UI 组）：
        #   可见范围=仅 @ 消息（mention_only）、触发=仅被 @ 回复（mention）、
        #   上下文条数=0、回复后清空临时上下文（clear_after_reply）
        #   ——prompt 极简化的通道层落地：非 @ 消息在 _prepare_inbound 就被吞（不进 processor/不进 prompt）
        try:
            from harness_gateway.group_context import GroupContextConfig, GroupContextManager
            gc_cfg = GroupContextConfig(
                enabled=True,
                visibility="mention_only",
                activation="mention",
                history="none",
                history_limit=0,
                clear_after_reply=True,
            )
            ch._config.group_context = gc_cfg
            ch._group_context = GroupContextManager(gc_cfg)
            log.info("[nong-gateway] 群聊策略已应用（channel=%s）：mention_only/mention/history=none",
                     channel_id[:12])
        except Exception as exc:                                # noqa: BLE001
            log.warning("[nong-gateway] 群聊策略应用失败（继续）: %s", exc)
        # 0.8) typing 气泡劫持：元宝原生 _handle_text_frame 对**每条**入站消息无条件发
        #      HEARTBEAT_RUNNING（channels/yuanbao/channel.py:762-765），且发生在 GroupContext
        #      吞消息之前——表现就是"没 @ 也看到机器人在打字"（2026-09-18 用户实测）。
        #      接管：只在该消息**会被处理**时才亮气泡（bot_mentioned 判定同源）。
        async def _typing_only_when_triggered(self, subject, _bridge=bridge):
            try:
                sid = getattr(subject, "subject_id", "") or ""
                meta = dict(getattr(subject, "metadata", None) or {})
                # 私聊一律亮；群里仅当被 @ 且本桥服务该会话
                is_group = bool(meta.get("group_code")) or str(getattr(subject, "chat_type", "")) == "group"
                if not is_group:
                    await self._send_reply_heartbeat(subject, 1)      # HEARTBEAT_RUNNING=1
                    return
                if not meta.get("bot_mentioned"):
                    return
                if not _bridge.will_answer(sid):
                    return
                await self._send_reply_heartbeat(subject, 1)
            except Exception as exc:                            # noqa: BLE001
                log.warning("[nong-gateway] typing 门控失败（放行）: %s", exc)
                try:
                    await self._send_reply_heartbeat(subject, 1)
                except Exception:                               # noqa: BLE001
                    pass

        if stop_evt.is_set():
            log.info("[nong-gateway] 劫持线程在绑定期收到退出信号，放弃本次绑定")
            return
        ch._send_typing_indicator = _types.MethodType(_typing_only_when_triggered, ch)
        # 1) processor 劫持
        ch._processor = bridge.process
        # 2) 出站编码绑定（instance-level，覆盖原生 _send_text）
        async def _send_text_encoded(self, subject, text, _bridge=bridge):
            try:
                from nong_gateway.outbound_mentions import encode_text_with_mentions, build_targets
                static = getattr(_bridge.cfg, "mention_targets", None) or {}
                targets = build_targets(static, lambda: getattr(_bridge, "_learned_mentions", {}) or {})
                body = encode_text_with_mentions(text, targets)
            except Exception as exc:                            # noqa: BLE001
                log.warning("[nong-gateway] 出站编码失败（退纯文本）: %s", exc)
                body = [{"msg_type": "TIMTextElem", "msg_content": {"text": text}}]
            await self._send_msg_body(subject, body)
        ch._send_text = _types.MethodType(_send_text_encoded, ch)
        # 3) 学名字的入站钩子（劫持后 _parse_yuanbao_message 是原生的，出站编码的动态学映射断供——
        #    在 process 外层包一层学映射）
        orig_process = bridge.process
        async def _process_learn(msg):
            try:
                meta = getattr(msg, "metadata", {}) or {}
                for a in (meta.get("kcb_at_bots") or []):
                    nm = str(a.get("text") or "").lstrip("@").strip()
                    uid = str(a.get("user_id") or "")
                    if nm and uid:
                        bridge._learned_mentions[nm] = uid
            except Exception:                                   # noqa: BLE001
                pass
            async for ev in orig_process(msg):
                yield ev
        ch._processor = _process_learn
        log.info("[nong-gateway] 劫持完成：channel=%s agent=%s（processor=桥 process，出站编码已绑）",
                 channel_id[:12], agent_id)

    # 单通道单劫持线程：多代 setup 重复 spawn 会让同一条消息被处理 N 次
    # （实测 ×7：账本重复 7 行、日志刷 7 遍、宿主被调 7 次）。用 builtins 记代数 +
    # stop_event 让旧代退出——**不是**简单跳过（跳过会让新代码永远绑不上）。
    prev = getattr(_b, "nonggw_hijack_threads", None)
    if prev is None:
        prev = {}
        _b.nonggw_hijack_threads = prev
    old_stop = prev.get(channel_id)
    if old_stop is not None:
        old_stop.set()                       # 通知旧代退出（_run 的等待循环里检查）
        log.info("[nong-gateway] 通道 %s 旧劫持线程已通知退出（换新代）", channel_id[:12])
    stop_evt = threading.Event()
    prev[channel_id] = stop_evt
    _th = threading.Thread(target=_run, args=(stop_evt,), name=f"nonggw-hijack-{agent_id}", daemon=True)
    _th.start()


def setup(ctx) -> None:
    is_server, why = _server_process()
    log.info("[nong-gateway] setup: 启动门判定=%s（%s）", is_server, why)
    if not is_server:
        return

    for note in _self_heal():
        log.info("[nong-gateway] 自愈: %s", note)

    _add_src_to_path()
    GENERATION["n"] += 1
    gen = GENERATION["n"]
    stop = threading.Event()

    # 旧一代还在跑的话先收线（reload 时 setup 会被再次执行）。
    # 注意：只 set 外层 Event 不够——runner.start() 阻塞循环看的是它自己的 _stop，
    # 必须调 runner.stop() 才会让它真正收线（锁/WS/线程全清）。
    # 跨代状态挂 builtins：unload_plugin 会 pop 本插件模块，函数对象上的属性随模块一起丢
    # （实测 18:39 那轮：新 setup 读不到旧 _current，旧桥一直握锁，新一代 30s 后弃权退出）。
    import builtins as _b
    old = getattr(_b, "nonggw_current", None)
    if old is not None:
        old[1].set()
        old_runner = old[2].get("runner") if len(old) > 2 else None
        if old_runner is not None:
            try:
                old_runner.stop()
                log.info("[nong-gateway] 已调第 %d 代 runner.stop()", old[0])
            except Exception as exc:              # noqa: BLE001
                log.warning("[nong-gateway] 第 %d 代 stop 异常: %s", old[0], exc)
        log.info("[nong-gateway] 已通知第 %d 代收线", old[0])

    runner_holder: dict = {}

    def _run_bridge() -> None:
        try:
            from nong_gateway.core import BridgeRunner, make_logger, Config
            cfg = Config.load(config_file=str(PERSIST_HOME / "config.json"))
            logger = make_logger(str(PERSIST_HOME / "bridge.log"), echo=False)
            runner = BridgeRunner(cfg, log=logger)
            runner_holder["runner"] = runner
            _b.nonggw_current = (gen, stop, runner_holder)
            _b.nonggw_runner_ref = runner
            runner.start()                      # 阻塞直到 stop() 或启动失败
            if not stop.is_set() and not runner.bridges:
                log.info("[nong-gateway] 未配置允许列表/凭据，不服务任何 agent；"
                         "配置见 %s/config.json（credentials[].agentId + agents 段点名）",
                         PERSIST_HOME)
        except Exception as exc:                  # noqa: BLE001
            log.warning("[nong-gateway] 桥线程退出: %s: %s", type(exc).__name__, exc)
        finally:
            log.info("[nong-gateway] 第 %d 代桥线程已退出", gen)

    t = threading.Thread(target=_run_bridge, name=f"nonggw-bridge-{gen}", daemon=True)
    t.start()

    def _watchdog() -> None:
        """20s 宽限后开始查注册表；不在册连续两次 → 通知桥收线。"""
        from harness_agent.plugins.registry import PluginRegistry
        if not stop.wait(20):
            misses = 0
            while not stop.wait(5):
                in_registry = PluginRegistry().get("nong-gateway") is not None
                misses = 0 if in_registry else misses + 1
                if misses >= 2:
                    log.info("[nong-gateway] 插件已不在注册表（面板停用/卸载/重载），收线")
                    r = runner_holder.get("runner")
                    if r is not None:
                        try:
                            r.stop()
                        except Exception:             # noqa: BLE001
                            pass
                    stop.set()
                    return
                if misses == 1:
                    log.info("[nong-gateway] 注册表未命中（1/2），继续观察")

    wt = threading.Thread(target=_watchdog, name=f"nonggw-watchdog-{gen}", daemon=True)
    wt.start()
