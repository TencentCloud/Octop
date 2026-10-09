"""宿主接缝：一轮对话交给谁跑（pi / Octop / 任意 CLI）。

为什么单开一层：**通道**（元宝协议、at 判定、引用、白名单、媒体、分块）与**谁来思考**
是两件不同的事。0.2.x 把两者焊在一起（`Bridge.ask` 里直接连 Octop 的 WS），代价是
换宿主等于改桥。现在 `Bridge.ask` 只是一个派发口，每个宿主一个实现：

1. `octop` —— 官方 WS 会话接口（原实现原样，默认值，老部署不受影响）。
2. `pi`    —— `pi --mode rpc`（官方 RPC 模式：stdin/stdout 严格 LF 分帧 JSONL）。
   比 WS 形态多两样东西：`images` 能真正把图**当图**喂给模型（不是给它一个路径），
   `abort` 能真取消。事件流用 `message_update.text_delta` 增量、`agent_settled` 收尾。
3. `cli`   —— 任意命令行 agent（Claude Code / Codex / 别的），命令模板 + 输出解析器 + 会话续接。

三个宿主共享同一条纪律：**一个会话一次只跑一轮**（新消息排队），所以「同会话串行」
在适配层就成立，不靠上层自觉。取消、超时、子进程死掉都收敛成可读文本交给通道，
不让异常穿到 IM 那边变成沉默。

刻意留的边界（写清而不是假装支持）：
1. pi 的 `steer`/`followUp`（运行中插话）没有接——v1 一律排队（`deliver` 字段已在
   TurnRequest 里，接的时候不用改签名）。per-agent 键 `busyPolicy` 预留。
2. 音频/视频/文件不进多模态（pi 的 prompt 只收 `images`）：路径仍由通道写进正文，
   适配层只对图片附 base64。
3. `cli` 形态的解析器只实现 `plain` 与 `claude-json`（本机没装 claude/codex，
   没法实测它们的事件帧；不实测不写解析器，codex 走 plain）。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shlex
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_KEEP_SESSION_FRAMES = 200        # 每个进程记多少帧给 --doctor / 排障看


def _safe_name(s: str, limit: int = 48) -> str:
    """会话键 → 目录名。中文留着（pi 自己也会用中文名），只换掉路径分隔与危险字符。"""
    out = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", s)
    return (out or "session")[:limit]


@dataclass
class TurnRequest:
    session: str                        # 会话键（每个 chat 一个，pi 形态即 session-dir 名）
    title: str = ""                     # 新建会话时的显示名
    text: str = ""
    media: list[str] = field(default_factory=list)   # 本机路径（能当图附的才附）
    deliver: str = "followUp"           # 预留：queue / steer（v1 只排队）


@dataclass
class TurnOutcome:
    text: str
    ok: bool = True
    error: str = ""
    session_id: str = ""                # 宿主侧会话 id（cli 形态用来续接）


class HostError(RuntimeError):
    """宿主层可读失败。通道把它当「本轮没有输出 + 原因」交给用户，不抛穿。"""


# --------------------------------------------------------------------------- #
# pi --mode rpc
# --------------------------------------------------------------------------- #
def 读env文件(env: dict, 路径: str, log: Callable[..., None] | None = None) -> int:
    """把 KEY=VALUE 逐行读进 env，返回读进去几条。**不做 shell 展开**。

    为什么不用 `source`：那等于让一个文件的能力变成任意代码执行，而这份文件里装的是
    技能要用的密钥；只认 `KEY=VALUE` 既够用又好审。读不动时必须留痕。
    """
    进 = 0
    try:
        行们 = Path(路径).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        if log:
            log(f"环境文件读不动 {路径}：{type(exc).__name__}: {exc}（子进程少这些变量）")
        return 0
    for 行 in 行们:
        文 = 行.strip()
        if not 文 or 文.startswith("#") or "=" not in 文:
            continue
        if 文.startswith("export "):
            文 = 文[len("export "):].strip()
        键, 值 = 文.split("=", 1)
        键 = 键.strip()
        if not 键.replace("_", "").isalnum():
            continue
        值 = 值.strip().strip('"').strip("'")
        env[键] = 值
        进 += 1
    return 进


class _PiProc:
    """一个 pi RPC 子进程 + 一轮在跑的对话。

    `settled` 是「本轮的结束信号」：pi 的事件里 `agent_end` 之后可能还有自动重试、
    压缩、排队的续跑，只有 `agent_settled` 才是真的停下来了（官方文档 Events 一节）。
    按 `agent_end` 收尾会把重试前的半截文本当最终答案发出去。
    """

    def __init__(self, proc: asyncio.subprocess.Process, key: str) -> None:
        self.proc = proc
        self.key = key
        self.buf = bytearray()
        self.reader: asyncio.Task | None = None
        self.settled: asyncio.Future | None = None
        self.out: list[str] = []
        self.stderr: list[str] = []
        self.frames: list[str] = []      # 帧类型序列（排障用：卡在哪一步一眼可见）
        self.on_delta: Callable[[str], None] | None = None
        self.on_event: Callable[[str, Any], None] | None = None
        self.last_active = time.time()
        self.last_error = ""
        self.busy = False
        self.ui_notes: list[str] = []      # 本轮里被自动应答的界面请求（要告诉用户）

    def note(self, typ: str) -> None:
        self.frames.append(typ)
        del self.frames[:-MAX_KEEP_SESSION_FRAMES]
        self.last_active = time.time()


class PiRpcHost:
    """`pi --mode rpc` 适配。一个会话一个常驻进程，空闲回收，总量封顶。"""

    name = "pi"

    def __init__(self, cfg, log: Callable[..., None],
                 session_dir_base: Path | str | None = None) -> None:
        self.cfg = cfg
        self.log = log
        self.session_dir_base = Path(session_dir_base) if session_dir_base else None
        self.procs: dict[str, _PiProc] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self._reaper: asyncio.Task | None = None

    # ---- 进程管理 ---------------------------------------------------------- #
    def _base_dir(self) -> Path:
        base = Path(self.cfg.host_session_dir or self.session_dir_base
                    or (Path(self.cfg.state_dir) / "host-sessions"))
        d = base / "pi"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _session_dir(self, key: str) -> Path:
        d = self._base_dir() / _safe_name(key)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _argv(self, req: TurnRequest, sdir: Path) -> list[str]:
        if self.cfg.host_command:
            # 用户给了模板就照模板走（{dir} {title} 两个占位），便于换解释器/加参数。
            cmd = (self.cfg.host_command
                   .replace("{dir}", shlex.quote(str(sdir)))
                   .replace("{title}", shlex.quote(req.title or req.session)))
            return shlex.split(cmd)
        pi_bin = shutil.which("pi") or "pi"
        argv = [pi_bin, "--mode", "rpc", "--session-dir", str(sdir),
                "--name", req.title or f"元宝-{req.session[:24]}"]
        if getattr(self.cfg, "host_tools", ""):
            # 工具白名单：不给 bash 时它只能在自己工作区里读写文件——
            # IM 通道是"外部能打进来的入口"，能力边界必须在这一层收窄
            argv += ["--tools", str(self.cfg.host_tools)]
        if getattr(self.cfg, "host_model", ""):
            argv += ["--model", str(self.cfg.host_model)]
        for 扩展 in (getattr(self.cfg, "host_extensions", None) or []):
            argv += ["-e", str(扩展)]           # 沙箱扩展等：pi 的 -e 只在本次加载
        if getattr(self.cfg, "host_user", ""):
            # 降权运行：桥本身可以是 root（它要读凭据），但**子进程不该是 root**。
            # setpriv 就地降权（不需要 sudo），--clear-groups 顺手丢掉附加组。
            argv = ["setpriv", "--reuid", str(self.cfg.host_user),
                    "--regid", str(self.cfg.host_user), "--clear-groups", "--"] + argv
        # 目录里已有会话文件才续接：空目录上带 -c，pi 会去找「最近一个会话」而找不到。
        if any(sdir.glob("*.jsonl")):
            argv.append("-c")
        return argv

    async def _ensure(self, req: TurnRequest) -> _PiProc:
        key = req.session
        p = self.procs.get(key)
        if p is not None and p.proc.returncode is None:
            return p
        sdir = self._session_dir(key)
        if self.cfg.host_cwd and not Path(self.cfg.host_cwd).is_dir():
            # 工作目录不存在时 create_subprocess_exec 报的是 "拉起 … 失败：FileNotFoundError"，
            # 那句话不告诉人"是 hostCwd 写错了"。这里提前给一句能直接照做的。
            raise HostError(f"hostCwd 不存在：{self.cfg.host_cwd}"
                            f"（--set hostCwd=<存在的目录>，或留空用桥自己的 cwd）")
        argv = self._argv(req, sdir)
        if not shutil.which(argv[0]) and not Path(argv[0]).exists():
            raise HostError(f"没找到 {argv[0]} 命令（--set hostCwd/hostCommand 或把它放进 PATH）")
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=self.cfg.host_cwd or None,
                env=self._child_env())
        except OSError as exc:
            raise HostError(f"拉起 {argv[0]} 失败：{type(exc).__name__}: {exc}") from exc
        p = _PiProc(proc, key)
        p.reader = asyncio.create_task(self._read_loop(p))
        asyncio.create_task(self._read_stderr(p))
        self.procs[key] = p
        self.log(f"[pi] 起进程 session={key} pid={proc.pid} argv={' '.join(argv[1:])}")
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap_loop())
        return p

    def _child_env(self) -> dict:
        """给子进程的环境：沙箱参数 + 降权后的 HOME。

        为什么 HOME 要显式给：以另一个用户跑 pi 时，它会去读那个用户的 ~/.pi（模型与凭据）。
        不换 HOME 的话它会去读 root 的配置——降权就白做了（而且会读到不该读的密钥）。
        """
        env = dict(os.environ)
        根们 = getattr(self.cfg, "sandbox_roots", None)
        if 根们:
            env["PI_SANDBOX_ROOTS"] = ":".join(str(x) for x in 根们)
            env["PI_SANDBOX_ALLOW_BASH"] = ("1" if getattr(self.cfg, "sandbox_allow_bash", False)
                                            else "0")
            env["PI_SANDBOX_STRICT"] = "1" if getattr(self.cfg, "sandbox_strict", False) else "0"
        if 根们:
            # 拦下事件落盘：print 模式看不到扩展日志，"是沙箱拦的还是模型自己拒绝的"分不清。
            # 落在**沙箱根里**而不是 state 目录：降权后子进程写不进 /root（750），
            # 而"审计写不进去"正是最不该静默的事（本机实测：审计文件一直没生成才发现）
            env.setdefault("PI_SANDBOX_LOG", str(Path(根们[0]) / "sandbox-blocks.log"))
        # 环境文件（如 imagent 家的 .agent-env.sh）：把技能需要的密钥、NONG_DATA_DIR、
        # ZVEC_GREP_HOME 等注入子进程。**只注入键值，不 source shell**——读文件比跑 shell 可控。
        家文件 = getattr(self.cfg, "host_env_files", None) or []
        for 文件 in 家文件:
            读env文件(env, str(文件), self.log)
        用户 = str(getattr(self.cfg, "host_user", "") or "")
        if 用户:
            家 = str(getattr(self.cfg, "host_user_home", "") or f"/home/{用户}")
            env["HOME"] = 家
            env["USER"] = 用户
        return env

    async def _read_stderr(self, p: _PiProc) -> None:
        assert p.proc.stderr is not None
        while True:
            line = await p.proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                p.stderr.append(text)
                del p.stderr[:-40]
                self.log(f"[pi] stderr {text[:200]}", force=False)

    async def _read_loop(self, p: _PiProc) -> None:
        """严格 LF 分帧（官方要求：不能用会按 U+2028/U+2029 切行的通用行读取器）。"""
        assert p.proc.stdout is not None
        while True:
            chunk = await p.proc.stdout.read(65536)
            if not chunk:
                break
            p.buf += chunk
            while True:
                nl = p.buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(p.buf[:nl])
                del p.buf[:nl + 1]
                if line.endswith(b"\r"):
                    line = line[:-1]
                if not line.strip():
                    continue
                try:
                    frame = json.loads(line.decode("utf-8", "replace"))
                except Exception as exc:  # noqa: BLE001
                    # 坏帧不静默：写一条留痕（本机踩过「解析器丢字段，看起来像平台不发」）
                    self.log(f"[pi] 坏帧（{type(exc).__name__}）：{line[:160]!r}")
                    continue
                if isinstance(frame, dict):
                    self._dispatch(p, frame)
        # 进程没了：先等它被 reap 到（returncode 才有值，否则报错里只剩 code=None），
        # 再把还在等的那一轮放掉——别让它干等到超时
        try:
            await asyncio.wait_for(p.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        self._finish(p, ok=False, error=self._exit_reason(p))

    def _exit_reason(self, p: _PiProc) -> str:
        tail = "；".join(p.stderr[-3:])
        code = p.proc.returncode
        return (f"pi 进程退出（code={code}）" + (f"：{tail[:300]}" if tail else ""))

    def _dispatch(self, p: _PiProc, frame: dict) -> None:
        typ = frame.get("type") or ""
        p.note(typ)
        if self.cfg.verbose:
            self.log(f"[pi] 帧 {typ} {str(frame)[:110]}", force=False)
        if typ == "message_update":
            ev = frame.get("assistantMessageEvent") or {}
            et = ev.get("type")
            if et == "text_delta":
                piece = ev.get("delta") or ""
                if piece:
                    p.out.append(piece)
                    if p.on_delta:
                        p.on_delta(piece)
            elif et == "thinking_delta" and p.on_event:
                piece = ev.get("delta") or ""
                if piece:
                    p.on_event("think", piece)
            elif et == "toolcall_start" and p.on_event:
                p.on_event("tool", {"name": ev.get("toolName") or "", "phase": "start"})
        elif typ == "tool_execution_start" and p.on_event:
            p.on_event("tool", {"name": frame.get("toolName") or "", "phase": "start"})
        elif typ == "tool_execution_end" and p.on_event:
            p.on_event("tool", {"name": frame.get("toolName") or "", "phase": "end"})
        elif typ == "extension_ui_request":
            self._answer_ui_request(p, frame)
        elif typ == "extension_error":
            self.log(f"[pi] 扩展报错：{str(frame)[:240]}")
        elif typ == "agent_settled":
            self._finish(p, ok=True)
        elif typ == "response" and frame.get("success") is False:
            cmd = frame.get("command") or ""
            err = str(frame.get("error") or frame)[:240]
            p.last_error = f"{cmd}: {err}"
            self.log(f"[pi] 命令失败 {cmd}: {err}")
            if cmd in ("prompt", "steer", "follow_up"):
                self._finish(p, ok=False, error=f"pi 拒绝了这一轮：{err}")

    # 真的会等回答的四种；其余（notify/setStatus/setWidget/setTitle）是单向通知。
    # 真机实测踩到的：把 setStatus 也当弹窗回包，结果每轮回复末尾多一句"已自动取消 setStatus"。
    DIALOG_METHODS = {"select", "confirm", "input", "editor"}

    def _answer_ui_request(self, p: _PiProc, frame: dict) -> None:
        """pi 扩展想弹窗问人（允许危险命令、清会话…）。IM 通道里没人点按钮，
        必须当场给明确回答：不给的话这一轮就停在等确认上，用户只看到「没反应」。

        策略一律保守：`confirm` 拒绝、其它取消——**不替用户说"允许"**。
        代价是可能少干一件事，所以把这条写进本轮正文，用户才知道为什么没干。
        """
        rid = str(frame.get("id") or "")
        method = str(frame.get("method") or "")
        title = str(frame.get("title") or frame.get("message") or "")[:120]
        if method not in self.DIALOG_METHODS:
            # 单向通知：不回包。warning/error 值得让用户看见，info 只进日志。
            if method == "notify":
                kind = str(frame.get("notifyType") or "info")
                self.log(f"[pi] 扩展通知[{kind}]：{title}")
                if kind in ("warning", "error"):
                    p.ui_notes.append(f"（宿主扩展通知[{kind}]：{title}）")
            elif self.cfg.verbose:
                self.log(f"[pi] 界面指令 {method}（单向，不回答）", force=False)
            return
        ans: dict[str, Any] = {"type": "extension_ui_response", "id": rid}
        if method == "confirm":
            ans["confirmed"] = False
        else:
            ans["cancelled"] = True
        try:
            p.proc.stdin.write((json.dumps(ans, ensure_ascii=False) + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError) as exc:
            self.log(f"[pi] 界面请求答不出去：{exc}")
            return
        动作 = "拒绝" if method == "confirm" else "取消"
        self.log(f"[pi] 自动{动作}界面请求 {method}：{title}")
        p.ui_notes.append(f"（宿主弹窗已自动{动作}：{method} {title}）")

    def _finish(self, p: _PiProc, *, ok: bool, error: str = "") -> None:
        fut = p.settled
        p.busy = False
        p.on_delta = None
        p.on_event = None
        文本 = "".join(p.out)
        if p.ui_notes:
            文本 += ("\n\n" if 文本 else "") + "\n".join(p.ui_notes)
        if fut is not None and not fut.done():
            fut.set_result(TurnOutcome(text=文本, ok=ok,
                                      error=error or p.last_error, session_id=p.key))

    # ---- 取图 -------------------------------------------------------------- #
    def images_for(self, media: list[str]) -> tuple[list[dict], list[str]]:
        """能当图附的转 base64；不能附的**说明原因**返回（不静默丢）。"""
        out: list[dict] = []
        skipped: list[str] = []
        cap = int(self.cfg.host_image_max_mb * 1024 * 1024)
        for path in media or []:
            f = Path(path)
            suf = f.suffix.lower()
            if suf not in IMAGE_SUFFIXES:
                skipped.append(f"{f.name}（{suf or '无后缀'} 不是图片，pi 只收 image 块）")
                continue
            try:
                if f.stat().st_size > cap:
                    skipped.append(f"{f.name}（{f.stat().st_size // 1024}KB 超过 hostImageMaxMB）")
                    continue
                data = base64.b64encode(f.read_bytes()).decode("ascii")
            except OSError as exc:
                skipped.append(f"{f.name}（读不到：{exc}）")
                continue
            mime = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
                    ".bmp": "image/bmp"}.get(suf, "image/jpeg")
            out.append({"type": "image", "data": data, "mimeType": mime})
        return out, skipped

    async def _bind_loop(self) -> None:
        """记下第一次用的 loop；发现换了就把旧会话进程丢掉（宁可重起，也不要挂到超时）。

        子进程的 transport 绑在创建它的 loop 上：换 loop 后再写 stdin，数据进不去、
        收尾帧也读不回来，表现是「发出去没反应」——这类卡死查起来最费时间，所以在这里
        显式断开并留痕，而不是让它静静挂着。
        """
        loop = asyncio.get_running_loop()
        old = getattr(self, "_loop", None)
        if old is None:
            self._loop = loop
            return
        if old is not loop:
            if self.procs:
                self.log(f"[pi] 事件循环换了，丢弃 {len(self.procs)} 个旧会话进程（重起更可靠）")
            await self._drop_all()
            self._loop = loop
            self.locks.clear()

    async def _drop_all(self) -> None:
        for key in list(self.procs):
            try:
                await self._stop(key)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[pi] 丢弃会话 {key} 时出错：{type(exc).__name__}: {exc}")

    # ---- 会话串行 + 一轮对话 ----------------------------------------------- #
    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self.locks:
            self.locks[key] = asyncio.Lock()
        return self.locks[key]

    async def _late(self, p: _PiProc, req: TurnRequest, on_late, 锁) -> None:
        """后台等这一轮收尾，然后补发。异常自己吞掉并留痕（后台任务抛出去没人接）。"""
        try:
            outcome = await p.settled
            try:
                on_late(outcome)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[pi] 补发回调失败：{type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.log(f"[pi] 后台收尾等不到结果：{type(exc).__name__}: {exc}")
        finally:
            锁.release()

    async def ask(self, req: TurnRequest, on_delta=None, timeout: int = 900,
                  on_event=None, on_late=None, defer_on_timeout: bool = False) -> TurnOutcome:
        """跑一轮。同会话自动串行（锁），新消息不会插进正在跑的那轮里。

        `defer_on_timeout=True`：超时**不杀这一轮**，交给后台继续跑，跑完调 `on_late(outcome)`
        补发结果（长任务不该以"超时失败"结束——dsh-im 的 deferred delivery 就是这个语义）。
        此时会话锁**保持到后台那轮结束**，否则新消息会插进同一个 pi 会话、两轮交错。
        """
        # 换 loop 的清理必须在**取锁之前**：锁对象也是绑 loop 的，拿一个绑在已关闭 loop 上的
        # 锁去 acquire 就是永久等待（本机踩到：守卫用例第二次 ask 挂死，faulthandler 才定位到）
        await self._bind_loop()
        if defer_on_timeout and on_late is not None:
            锁 = self._lock(req.session)
            await 锁.acquire()
            状态: dict = {"转后台": False}
            try:
                outcome = await self._ask_locked(req, on_delta, timeout, on_event,
                                                on_late=on_late, defer=True, 锁=锁, 状态=状态)
            except BaseException:
                锁.release()
                raise
            # **成功路径也必须放锁**：只有"转后台"那条把锁交给 _late（它跑完才放）。
            # 忘了这一步的表现是"这个会话从此再也不回话"——本机踩到，卡在自检里才发现
            if not 状态["转后台"]:
                锁.release()
            return outcome
        async with self._lock(req.session):
            return await self._ask_locked(req, on_delta, timeout, on_event,
                                          on_late=on_late, defer=False, 锁=None)

    async def _ask_locked(self, req: TurnRequest, on_delta, timeout: int, on_event,
                          *, on_late=None, defer: bool = False, 锁=None,
                          状态: dict | None = None) -> TurnOutcome:
        try:
            p = await self._ensure(req)
        except HostError as exc:
            return TurnOutcome(text="", ok=False, error=str(exc))
        if p.proc.returncode is not None:
            self.procs.pop(req.session, None)
            try:
                p = await self._ensure(req)
            except HostError as exc:
                return TurnOutcome(text="", ok=False, error=str(exc))
        images, skipped = self.images_for(req.media)
        if skipped:
            self.log(f"[pi] 这些媒体没进多模态：{'；'.join(skipped)}")
        p.out = []
        p.last_error = ""
        p.ui_notes = []
        p.on_delta = on_delta
        p.on_event = on_event
        p.settled = asyncio.get_running_loop().create_future()
        p.busy = True
        msg = {"type": "prompt", "message": req.text}
        if images:
            msg["images"] = images
        p.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await p.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            self._finish(p, ok=False, error=f"写不进 pi 的 stdin：{exc}")
        try:
            return await asyncio.wait_for(asyncio.shield(p.settled), timeout=timeout)
        except asyncio.TimeoutError:
            if defer and on_late is not None:
                # 后台等它收尾，收完补发；锁留到那时才放（并告诉调用方"别放锁"）
                if 状态 is not None:
                    状态["转后台"] = True
                asyncio.create_task(self._late(p, req, on_late, 锁))
                self.log(f"[{self.__class__.__name__}] {timeout}s 未收尾，转入后台继续跑"
                         f"（完成后补发）session={req.session}")
                return TurnOutcome(text="".join(p.out), ok=False,
                                   error=f"本轮超过 {timeout}s，已转入后台继续跑，"
                                         f"完成后会把结果补发给你")
            await self.cancel(req.session)
            return TurnOutcome(text="".join(p.out), ok=False,
                               error=f"{timeout}s 内 pi 没有收尾（已 abort），把上表已收到的内容发给你")

    async def rotate(self, session: str) -> bool:
        """换一条新会话（旧会话文件留在磁盘可查）。

        为什么用 pi 自己的 new_session 而不是"换个 session-dir"：换目录会丢掉
        「重启后接着上次」的续接语义（`-c` 找的是目录里最近那条），也会让磁盘上的历史
        散成一堆目录。new_session 既断了上下文，又让旧会话仍是可 resume 的一条。
        """
        p = self.procs.get(session)
        if p is None or p.proc.returncode is not None:
            return False
        try:
            p.proc.stdin.write(b'{"type":"new_session"}\n')
            await p.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            self.log(f"[pi] 轮换发不出去：{exc}")
            return False
        self.log(f"[pi] 已请求新会话 session={session}（旧会话留在磁盘）")
        return True

    async def cancel(self, session: str) -> bool:
        p = self.procs.get(session)
        if p is None or p.proc.returncode is not None:
            return False
        if p.busy:
            try:
                p.proc.stdin.write(b'{"type":"abort"}\n')
                await p.proc.stdin.drain()
                self.log(f"[pi] 已发 abort session={session}")
            except (BrokenPipeError, ConnectionResetError) as exc:
                self.log(f"[pi] abort 发不出去：{exc}")
            self._finish(p, ok=False, error="已被用户取消")
        return True

    # ---- 回收 -------------------------------------------------------------- #
    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.reap_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.log(f"[pi] 回收循环出错（不影响对话）：{type(exc).__name__}: {exc}")

    async def reap_once(self) -> list[str]:
        """空闲回收 + 总量封顶。返回被停掉的会话键（可测）。

        为什么必须有：一个 chat 一个 pi 进程，群里多几个会话就是几百 MB 常驻。
        只回收**空闲的**（不在跑、队列空），正在跑的绝不动。
        """
        now = time.time()
        killed: list[str] = []
        for key, p in list(self.procs.items()):
            idle = now - p.last_active
            if not p.busy and idle > self.cfg.host_idle_sec:
                await self._stop(key)
                killed.append(key)
        cap = int(self.cfg.host_max_procs)
        if cap > 0:
            alive = [(k, p) for k, p in self.procs.items() if not p.busy]
            while len(self.procs) > cap and alive:
                k, _ = min(alive, key=lambda kv: kv[1].last_active)
                alive = [(kk, pp) for kk, pp in alive if kk != k]
                await self._stop(k)
                killed.append(k)
        if killed:
            self.log(f"[pi] 回收会话进程：{', '.join(killed)}")
        return killed

    async def _stop(self, key: str) -> None:
        p = self.procs.pop(key, None)
        if p is None:
            return
        try:
            p.proc.terminate()
            await asyncio.wait_for(p.proc.wait(), timeout=5)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                p.proc.kill()
            except ProcessLookupError:
                pass
        except Exception as exc:  # noqa: BLE001
            # 跨事件循环时 p.proc.wait() 会报 "attached to a different loop"：
            # SIGTERM 已经发了、进程会死，这里只留痕（报成"收尾出错"是噪音）
            self.log(f"[{self.__class__.__name__}] 等待子进程退出失败（信号已发）："
                     f"{type(exc).__name__}")
        if p.reader:
            p.reader.cancel()

    async def stop(self) -> None:
        if self._reaper:
            self._reaper.cancel()
        for key in list(self.procs):
            await self._stop(key)

    def describe(self) -> str:
        live = [f"{k}({'忙' if p.busy else '闲'}{len(p.frames)}帧)" for k, p in self.procs.items()]
        return f"pi RPC，在跑 {len(self.procs)} 个会话" + (f"：{', '.join(live)}" if live else "")


# --------------------------------------------------------------------------- #
# 任意命令行 agent（Claude Code / Codex / …）
# --------------------------------------------------------------------------- #
class CliHost:
    """一次一轮的子进程宿主，用命令模板 + 输出解析器适配不同 CLI。

    模板占位符（都可选）：
      {prompt}   —— 正文（自动 shell 引用；不写就改用 stdin 喂）
      {media}    —— 媒体本机路径（空格分隔，已引用）
      {session}  —— 宿主侧会话 id（没有时是空串）
      {resume}   —— 会话续接片段（hostResumeTemplate 展开；没有 id 时空串）
      {sessiondir} / {title} —— 会话目录 / 显示名

    解析器（`hostParseMode`）：
      plain       —— stdout 整段就是回答（去掉 ANSI 转义）
      claude-json —— 逐行 JSON：assistant 消息取文本，result 帧取最终文本与 session_id

    本机没装 claude/codex，所以**只实现能验证的两种**；codex 走 plain 就够
    （`codex exec` 把答案打到 stdout），等真机上抓到它的事件帧再补解析器。
    """

    name = "cli"
    ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

    def __init__(self, cfg, log: Callable[..., None],
                 session_dir_base: Path | str | None = None) -> None:
        self.cfg = cfg
        self.log = log
        self.session_dir_base = Path(session_dir_base) if session_dir_base else None
        self.locks: dict[str, asyncio.Lock] = {}
        self.session_ids: dict[str, str] = {}
        self._load()

    def _base(self) -> Path:
        return Path(self.cfg.host_session_dir or self.session_dir_base
                    or (Path(self.cfg.state_dir) / "host-sessions"))

    def _map_path(self) -> Path:
        return self._base() / "cli-sessions.json"

    def _load(self) -> None:
        try:
            self.session_ids = json.loads(self._map_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.session_ids = {}

    def _save(self) -> None:
        p = self._map_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.session_ids, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)          # 原子写：读一半的 JSON 比丢一次映射更烦

    def _expand(self, req: TurnRequest) -> str:
        sid = self.session_ids.get(req.session, "")
        resume = ""
        if sid and self.cfg.host_resume_template:
            resume = self.cfg.host_resume_template.replace("{session}", shlex.quote(sid))
        sdir = self._base() / "cli" / _safe_name(req.session)
        sdir.mkdir(parents=True, exist_ok=True)
        out = (self.cfg.host_command
               .replace("{prompt}", shlex.quote(req.text))
               .replace("{media}", " ".join(shlex.quote(m) for m in req.media or []))
               .replace("{session}", shlex.quote(sid))
               .replace("{resume}", resume)
               .replace("{sessiondir}", shlex.quote(str(sdir)))
               .replace("{title}", shlex.quote(req.title or req.session)))
        return out

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self.locks:
            self.locks[key] = asyncio.Lock()
        return self.locks[key]

    async def ask(self, req: TurnRequest, on_delta=None, timeout: int = 900,
                  on_event=None, on_late=None, defer_on_timeout: bool = False) -> TurnOutcome:
        if not self.cfg.host_command:
            return TurnOutcome(text="", ok=False,
                               error="host=cli 需要 hostCommand 模板（--set hostCommand='...'）")
        async with self._lock(req.session):
            if self.cfg.host_cwd and not Path(self.cfg.host_cwd).is_dir():
                return TurnOutcome(text="", ok=False,
                                   error=f"hostCwd 不存在：{self.cfg.host_cwd}")
            cmd = self._expand(req)
            use_stdin = "{prompt}" not in self.cfg.host_command
            self.log(f"[cli] 跑：{cmd[:200]}")
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdin=asyncio.subprocess.PIPE if use_stdin else asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=self.cfg.host_cwd or None)
            except OSError as exc:
                return TurnOutcome(text="", ok=False, error=f"起不了子进程：{exc}")
            if use_stdin and proc.stdin is not None:
                proc.stdin.write(req.text.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()
            out, err = await self._collect(proc, on_delta, None if defer_on_timeout else timeout,
                                          req.session)
            if defer_on_timeout and on_late is not None and proc.returncode is None:
                # 超时没杀它：后台等它跑完，完成后补发（和 pi 形态同一语义）
                async def _late():
                    try:
                        await proc.wait()
                        if on_delta is None:
                            pass
                        if on_late:
                            on_late(TurnOutcome(text="".join(out), ok=proc.returncode == 0))
                    except Exception as exc:  # noqa: BLE001
                        self.log(f"[cli] 后台收尾出错：{type(exc).__name__}: {exc}")
                asyncio.create_task(_late())
            if proc.returncode not in (0, None):
                tail = "\n".join(err[-5:])[:400]
                return TurnOutcome(text=out, ok=False,
                                   error=f"{self.cfg.host_command.split()[0]} 退出码 {proc.returncode}"
                                         + (f"：{tail}" if tail else ""))
            if self.cfg.host_parse_mode == "claude-json":
                text, sid = self._parse_claude(out, on_delta)
                if sid:
                    self.session_ids[req.session] = sid
                    self._save()
                return TurnOutcome(text=text, ok=True, session_id=sid)
            text = self.ANSI.sub("", "".join(out)).strip()
            if on_delta:
                on_delta(text)
            return TurnOutcome(text=text, ok=True)

    async def _collect(self, proc, on_delta, timeout: int, session: str) -> tuple[list[str], list[str]]:
        out: list[str] = []
        err: list[str] = []

        async def pump(stream, sink, delta: bool) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace")
                sink.append(text)
                if delta and on_delta and self.cfg.host_parse_mode != "plain":
                    piece = self._claude_line_delta(text.rstrip("\n"))
                    if piece:
                        on_delta(piece)

        tasks = [asyncio.create_task(pump(proc.stdout, out, True)),
                 asyncio.create_task(pump(proc.stderr, err, False))]
        try:
            if timeout is None:
                await proc.wait()          # defer 模式：不设上限，交给后台
            else:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await asyncio.gather(*tasks, return_exceptions=True)
            return out, err + [f"超过 {timeout}s 未结束，已杀掉"]
        await asyncio.gather(*tasks, return_exceptions=True)
        return out, err

    def _claude_line_delta(self, line: str) -> str:
        try:
            frame = json.loads(line)
        except ValueError:
            return ""
        if frame.get("type") == "assistant":
            parts = [c.get("text") or "" for c in ((frame.get("message") or {}).get("content") or [])
                     if c.get("type") == "text"]
            return "".join(parts)
        return ""

    def _parse_claude(self, lines: list[str], on_delta) -> tuple[str, str]:
        final = ""
        sid = ""
        for line in lines:
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            if frame.get("session_id"):
                sid = str(frame["session_id"])
            if frame.get("type") == "result":
                final = str(frame.get("result") or frame.get("text") or final)
            elif frame.get("type") == "assistant" and frame.get("subtype") == "success":
                final = final or str(frame.get("result") or "")
        return final, sid

    async def rotate(self, session: str) -> bool:
        """cli 形态的"轮换"= 忘掉续接用的会话 id（下一轮起新会话）。"""
        had = self.session_ids.pop(session, "")
        if had:
            self._save()
        self.log(f"[cli] 已丢弃会话 id（{'有' if had else '本来就没有'}）session={session}")
        return True

    async def cancel(self, session: str) -> bool:
        return False       # 一次性子进程：没有可中断的常驻会话（文档写明）

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def describe(self) -> str:
        return f"cli（模板 {self.cfg.host_command[:60] or '未配'}，解析 {self.cfg.host_parse_mode}）"


class EkkoHost:
    """E3：把一轮交给 Ekko Studio 的同步 run 接口（POST /api/studio/chat-run/runs）。

    会话键映射按 thread 维护（rotate 丢映射即换会话）。凭据：binding 的
    ekko_token（或环境变量 EKKO_GATEWAY_TOKEN），不入 git。
    """

    name = "ekko"

    def __init__(self, cfg, log: Callable[..., None], session_dir_base: Path | str | None = None) -> None:
        self.cfg = cfg
        self.log = log
        self.base_url = str(getattr(cfg, "ekko_base_url", "") or "http://127.0.0.1:8648").rstrip("/")
        self.token = str(getattr(cfg, "ekko_token", "") or "")
        self.agent_id = str(getattr(cfg, "ekko_agent_id", "") or "ekko-agent")
        self._sessions: dict[str, str] = {}
        self._provider = str(getattr(cfg, "ekko_provider", "") or "")
        self._model = str(getattr(cfg, "ekko_model", "") or "")
        self._api_mode = str(getattr(cfg, "ekko_api_mode", "") or "")

    def _model_defaults(self) -> tuple[str, str, str]:
        """binding 显式配置优先；否则读 Ekko 配置的默认 provider/model。"""
        if self._provider and self._model:
            return self._provider, self._model, (self._api_mode or "chat_completions")
        import json as _json, os as _os
        home = _os.environ.get("EKKO_STUDIO_HOME", "/root/.ekko-studio")
        try:
            model = _json.load(open(_os.path.join(home, ".ekko/config/config.json"), encoding="utf-8")).get("model", {})
            provider = self._provider or str(model.get("defaultProvider") or "")
            model_id = self._model or str(model.get("defaultModel") or "")
            api_mode = self._api_mode or str(model.get("defaultApiMode") or "chat_completions")
            return provider, model_id, api_mode
        except Exception:
            return "", "", "chat_completions"

    async def ask(self, req: TurnRequest, timeout: int | None = None,
                  on_delta=None, on_event=None, on_late=None, **kwargs) -> TurnOutcome:
        # on_delta/on_event：群聊路径的流式回调；同步 run 接口一次性返回全文，
        # 这里收下参数但不用（结尾一次性 on_delta 也省——通道自己有兜底文案）。
        import os as _os
        if not self.token:
            self.token = _os.environ.get("EKKO_GATEWAY_TOKEN", "")
        if not self.token:
            return TurnOutcome(text="", ok=False,
                               error="ekko host 未配置 token（binding 的 ekko_token 或环境变量 EKKO_GATEWAY_TOKEN）")
        import aiohttp
        provider, model, api_mode = self._model_defaults()
        if not provider or not model:
            return TurnOutcome(text="", ok=False,
                               error="ekko host 未配置模型：请在 Ekko 供应商页设置默认 provider/model，"
                                     "或在 binding 配 ekko_provider/ekko_model/ekko_api_mode")
        payload: dict = {
            "input": req.text,
            "source": "coding_agent",
            "agent_id": self.agent_id,
            "provider": provider,
            "model": model,
            "apiMode": api_mode,
            "timeout_ms": int((timeout or 900) * 1000),
        }
        session_id = self._sessions.get(req.session)
        if session_id:
            payload["session_id"] = session_id
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{self.base_url}/api/studio/chat-run/runs",
                    json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=(timeout or 900) + 30),
                ) as resp:
                    data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            return TurnOutcome(text="", ok=False,
                               error=f"ekko 请求失败：{type(exc).__name__}: {exc}")
        if not isinstance(data, dict) or not data.get("ok"):
            error = str((data or {}).get("error") or f"HTTP {resp.status}") if isinstance(data, dict) else "空响应"
            return TurnOutcome(text="", ok=False, error=f"ekko 拒绝（{resp.status}）：{error}")
        sid = str(data.get("session_id") or "")
        if sid:
            self._sessions[req.session] = sid
        return TurnOutcome(text=str(data.get("output") or ""), ok=True, session_id=sid)

    async def rotate(self, session: str) -> bool:
        self._sessions.pop(session, None)
        return True

    async def close(self) -> None:
        return None

def make_host(name: str, cfg, log: Callable[..., None],
              session_dir_base: Path | str | None = None):
    """按名字造宿主。未知值直接报错——静默回落 octop 会让「我明明配了 pi」查不出来。"""
    host = (name or "octop").strip().lower()
    if host == "pi":
        return PiRpcHost(cfg, log, session_dir_base=session_dir_base)
    if host == "cli":
        return CliHost(cfg, log, session_dir_base=session_dir_base)
    if host == "ekko":
        return EkkoHost(cfg, log, session_dir_base=session_dir_base)
    if host == "octop":
        return None        # None = 用 Bridge 自带的 WS 实现（原路径，零改动）
    raise HostError(f"未知宿主 host={host!r}（可选：octop / pi / cli / ekko）")
