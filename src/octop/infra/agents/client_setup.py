"""Bootstrap a local terminal so it talks to this memory service.

``GET /mcp/memory/setup`` streams the interactive installer this module renders — no
authentication, because it only hands out a script: the credential is a **user-level MCP
token** (``omcp_…``, created in Octop under ``/api/memory-mcp/tokens``) typed by the
person running it, never fetched::

    curl -fsSL "https://<octop>/mcp/memory/setup" | sh
    #   → 检测到：1) Claude Code  2) Kiro  3) DSH  4) Codex  5) Cursor
    #   → 要配置哪些？   MCP token: ****（不回显）

Windows uses a native PowerShell installer (no Git Bash, no ``.cmd`` shim)::

    irm "https://<octop>/mcp/memory/setup?os=windows" | iex

Both accept ``?project=<dir>`` to register into one project instead of the user profile.
It only *pre-fills* the interactive prompt; non-interactive runs read
``OCTOP_PROJECT_DIR`` (an explicitly empty value means "global").

``GET /mcp/memory/uninstall`` is the counterpart — removes hooks / MCP entries / the DSH
native plugin this installer wrote (does not delete server-side memory)::

    curl -fsSL "https://<octop>/mcp/memory/uninstall" | OCTOP_TERMINALS=cursor sh

Nothing is assumed about where an installer runs. The script detects which terminals
exist, asks which to configure, prompts for the MCP token and the expert id (reading
``/dev/tty`` — a piped script must not consume its own stdin), then installs a copy of
the hook scripts next to *each* terminal, in the directory that terminal uses, and
registers them in that terminal's own hook config:

=========================  =========================================  =============================
terminal                   hook scripts / plugin                      config
=========================  =========================================  =============================
Claude Code                ``~/.claude/hooks-events/``                ``~/.claude/settings.json``
Kiro                       ``~/.kiro/hooks/``                         ``~/.kiro/hooks/*.json``
DSH                        ``~/.dsh/bundles/octop-memory-native/``    ``~/.dsh/profiles/<name>/``
Codex                      ``~/.codex/hooks/``                        ``~/.codex/config.toml``
Cursor                     ``~/.cursor/hooks/``                       ``~/.cursor/hooks.json``
=========================  =========================================  =============================

DSH is wired through the **native plugin** ``octop-memory-native`` (recall/report run
in the DSH process), not through hook bridging: the installer copies the vendored
plugin, links it into the selected profile's ``node_modules``, registers the
``dependencies`` entry + ``dsh.profile.bundles`` name, and writes the
``cordis.patch.yml`` config block by row id (idempotent). Install *and* uninstall clean
up the legacy ``dsh-memory-share`` preset and the ``~/.dsh/hooks`` bridge so the two
wirings never trigger twice.

Each hook copy carries its own ``config.json`` (endpoint, token). The token is a user-level
MCP token that is **bound to exactly one expert**, and it is the only credential: entries and
hooks send ``Authorization: Bearer <token>`` and nothing else — no expert id header, because
the token already says which expert the memory belongs to. The hook roles are fixed: **UserPromptSubmit / beforeSubmitPrompt → memory_search** (pull background in)
and **Stop / stop → memory_capture** (ship the session transcript).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

_HOOKS_SRC = Path(__file__).with_name("hook_scripts")
# Every host gets the host-agnostic transport module next to its own entry scripts.
_LIB_FILES = ("lib/octop-memory-client.mjs",)

HOST_FILES: dict[str, tuple[str, ...]] = {
    "claude-code": ("claude-code/stop-capture.mjs", "claude-code/user-prompt-recall.mjs"),
    "kiro": ("kiro/stop-capture.mjs",),
    "codex": ("codex/stop-capture.mjs", "codex/user-prompt-recall.mjs"),
    "cursor": ("cursor/stop-capture.mjs", "cursor/user-prompt-recall.mjs"),
}
"""Which hook scripts a terminal gets. Each host has its own entry script — no
runtime host detection — so changing one host cannot affect another; the only
shared file is the host-agnostic transport module.

DSH is deliberately absent: it goes through the native plugin below, so it needs no
hook scripts and no hook config."""

_DSH_NATIVE_SRC = Path(__file__).with_name("dsh_native_plugin")
_DSH_NATIVE_FILES: tuple[str, ...] = (
    "package.json",
    "index.js",
    "lib/text.js",
    "cordis.patch.yml",
    "locale/zh.json",
    "locale/en.json",
    "icon.svg",
    "README.md",
)
"""DSH 原生记忆插件 ``octop-memory-native`` 的源码副本（vendored）。

来自插件仓 v0.1.2，逐字节复制、不在这里改动：插件的召回/上报逻辑与 DSH 版本无关，跟着插件仓
升级即可。安装器只做「抄进 ``~/.dsh/bundles/octop-memory-native`` + 登记 profile + 写配置块」。

升级方式：``cp`` 插件仓的对应文件到这个目录（``tests/`` / ``.git`` 不要带），同步本清单与
``package.json`` 的版本号，再跑 ``tests/unit/agents/test_client_setup.py``。

为什么不装 git URL：``/mcp/memory/setup`` 是 curl | sh 的无鉴权脚本，装 git 依赖要求目标机器
能访问 git 仓（私有源/代理/凭据各不相同）；vendored 副本跟着 octop 一起发版，安装只需要目录
（``link:``），离线也能装完整。代价是插件升级要发一次 octop 版本。"""

_DSH_NATIVE_NAME = "octop-memory-native"
"""插件目录名、package.json 包名、cordis.patch.yml 行 id、dsh.profile.bundles 名（同一个）。"""

TERMINALS: tuple[str, ...] = ("claude-code", "kiro", "dsh", "codex", "cursor")
"""Terminals this installer knows how to configure."""

# Owned by each terminal, so no cross-terminal directory is invented.
# ``dsh`` 这一项只用于「拆掉旧 hooks 桥接」与卸载，原生插件模式不再往里写脚本。
HOOKS_DIRS: dict[str, str] = {
    "claude-code": "~/.claude/hooks-events",
    "kiro": "~/.kiro/hooks",
    "dsh": "~/.dsh/hooks",
    "codex": "~/.codex/hooks",
    "cursor": "~/.cursor/hooks",
}

_SELECT_PY = r"""
import sys

# 交互式终端清单：↑/↓ 移动 · 空格 选择 · a 全选 · 回车 确认。
# 键位与绘制都走 /dev/tty，stdout 只用来回传结果（shell 捕获）。
# 任何一步不可用（无 tty / 无 termios / 空选择）就返回非 0，让 shell 回退到数字输入。

def main() -> int:
    items = [item.split("|", 1) for item in sys.argv[1:] if "|" in item]
    if not items:
        return 3
    try:
        import termios
        import tty as ttymod

        tty_in = open("/dev/tty", "rb", buffering=0)
        tty_out = open("/dev/tty", "w")
        fd = tty_in.fileno()
        saved = termios.tcgetattr(fd)
    except Exception:
        return 3

    chosen = [False] * len(items)
    cursor = 0

    def render(first: bool = False) -> None:
        if not first:
            tty_out.write("\033[%dA" % (len(items) + 1))
        for index, (_, label) in enumerate(items):
            box = "◉" if chosen[index] else "◯"
            pointer = "❯" if index == cursor else " "
            tty_out.write("\033[2K%s %s %s\r\n" % (pointer, box, label))
        hint = "  ↑/↓ 移动 · 空格 选择 · a 全选 · 回车 确认"
        if not any(chosen):
            hint = "  ↑/↓ 移动 · 空格 选择 · a 全选 · 回车 确认（还没选）"
        tty_out.write("\033[2K%s\r\n" % hint)
        tty_out.flush()

    def read_key() -> str:
        key = tty_in.read(1)
        if key == b"\x1b":
            rest = tty_in.read(2)
            return {b"[A": "up", b"[B": "down"}.get(rest, "other")
        if key in (b"\r", b"\n"):
            return "enter"
        if key == b" ":
            return "space"
        if key in (b"a", b"A"):
            return "all"
        if key == b"\x03":
            return "abort"
        if key in (b"k", b"j"):
            return "up" if key == b"k" else "down"
        return "other"

    try:
        ttymod.setraw(fd)
        tty_out.write("要配置哪些终端？（可多选）\r\n")
        render(first=True)
        while True:
            key = read_key()
            if key == "up":
                cursor = (cursor - 1) % len(items)
            elif key == "down":
                cursor = (cursor + 1) % len(items)
            elif key == "space":
                chosen[cursor] = not chosen[cursor]
            elif key == "all":
                turn_on = not all(chosen)
                chosen = [turn_on] * len(items)
            elif key == "enter":
                if not any(chosen):
                    continue  # 一个都没选时不确认，提示留在屏幕上
                break
            elif key == "abort":
                return 130
            render()
    except Exception:
        return 3
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        except Exception:
            pass
        tty_out.write("\r\n")

    print(",".join(value for (value, _), on in zip(items, chosen) if on))
    return 0


sys.exit(main())
""".strip()

_MERGE_PY = '''
import base64
import json
import os
import pathlib
import shlex
import shutil
import subprocess


# Windows 的安装器把整份配置写进一个临时 JSON（命令行/环境块长度有限，manifest 很大），
# 这里把它补进 os.environ（真实环境变量优先），之后照旧按环境变量读。
_ENV_FILE = os.environ.get("OCTOP_ENV_FILE", "")
if _ENV_FILE:
    with open(_ENV_FILE, encoding="utf-8") as _env_handle:
        for _key, _value in json.load(_env_handle).items():
            os.environ.setdefault(str(_key), str(_value))


# hook 包装脚本按平台生成：POSIX 用 ``.sh``（sh 执行），Windows 用 ``.cmd``（系统 shell
# 执行）。安装器用 OCTOP_HOOK_WRAPPER 明确指定（PS 安装器=cmd，sh 安装器=sh）；单独跑本
# 脚本时按平台猜。
HOOK_WRAPPER = os.environ.get("OCTOP_HOOK_WRAPPER", "").strip().lower()
if HOOK_WRAPPER not in ("sh", "cmd"):
    HOOK_WRAPPER = "cmd" if os.name == "nt" else "sh"


SEARCH_PROMPT = (
    "回答前，先用 memory_search 检索与本轮相关的记忆（query 用用户本次输入，corpus=atom，"
    "max_results=5），把命中内容当作背景；与本次工作无关就忽略，不要重复检索同一个查询。"
)
"""Kiro 的召回提示词——Kiro 不会把 runCommand 的 stdout 注进上下文，只能让模型自己调工具。

上报**没有**对应的提示词：让模型"总结这段会话"只会把复述写进 L0，原始会话要由 hook 脚本
（整段 ``messages.jsonl``）提交，见 ``do_kiro``。
"""


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 - a broken config must not break setup
        print(f"  ! {path} 不是合法 JSON（{exc}）；跳过该文件")
        return None


def _dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")


def _strings(value):
    """递归取出 JSON 结构里的所有字符串（判断「这条是不是我们写的」用）。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _mentions_dir(value, directory):
    """JSON / TOML 文本里是否引用了这个目录（统一成正斜杠再比，Windows 反斜杠也认）。"""
    needle = str(directory).replace("\\\\", "/")
    return any(needle in text.replace("\\\\", "/") for text in _strings(value))


def _install_hooks(target, host):
    """把共享传输模块 + 该宿主的入口脚本写进这个终端自己的 hooks 目录。

    脚本与 ``config.json`` 始终留在用户目录（项目级安装也一样）：项目里只写「注册」，
    凭据不会出现在仓库里。``config.json`` 的形状就是连接配置本身
    （``url`` / ``token`` / ``tokenHeader``），DSH 原生插件也用它当兜底。
    """
    target.mkdir(parents=True, exist_ok=True)
    for rel, blob in HOOK_FILES[host].items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(blob))
    config = {"url": HOOK_URL, "token": TOKEN, "tokenHeader": TOKEN_HEADER}
    _dump(target / "config.json", config)
    print(f"  ✓ hook 脚本（{host} 专用，含共享传输模块）+ config.json → {target}")
    scratch = "%TEMP%" if os.name == "nt" else "$TMPDIR"
    print(
        f"      · 日志/增量状态：{target}/octop-hook.log、{target}/octop-transcript-state.json"
        f"（该目录不可写时退到 {scratch}/octop-hooks 并打印告警）"
    )


def _entry(transport=None):
    # 用户级 MCP token 是唯一凭据：``Authorization: Bearer <token>``。
    # token 绑定一个专家，「谁问的 / 落到哪个专家」全由它表达，不再有第二个身份头。
    headers = {
        "Authorization": f"Bearer {TOKEN}",
    }
    entry = {"type": transport or "http", "url": ENTRY_URL, "headers": headers}
    return entry


def _octop_servers(servers):
    """配置里已有的 octop memory 服务名——``local`` / ``prod`` / ``test`` 这类后缀都算。"""
    return [name for name in servers if str(name).replace("_", "-").startswith("octop-memory")]


def _merge_mcp(path, transport=None):
    """登记 MCP 服务：端点一致就复用已有条目，已有别的 octop 条目就不重复添加。

    服务名由客户端的配置说了算（同一个 ``octop-memory`` 可以带不同环境后缀、也可以被改名），
    这里只按端点判断；召回/上报 hook 调的地址来自 ``config.json``，与名字无关。
    """
    entry = _entry(transport)
    cfg = _load(path)
    if cfg is None:
        return
    servers = cfg.setdefault("mcpServers", {})
    ours = _octop_servers(servers)
    reused = next(
        (name for name in ours if (servers.get(name) or {}).get("url") == entry["url"]), ""
    )
    if reused:
        print(f"  ✓ MCP 服务 {reused}（已存在且端点一致，复用）→ {path}")
        return
    if ours:
        print(f"  · {path} 已有 octop 服务：{', '.join(ours)}（端点与本次 {URL} 不同，保持原样）")
        print("      · 模型侧用哪个服务由你决定；召回/上报 hook 用 config.json 里的地址")
        return
    servers[NAME] = entry
    _dump(path, cfg)
    print(f"  ✓ MCP 服务 {NAME} → {path}")


def _claude_hooks(hooks_dir):
    """Claude Code 的两条 command hook。

    - ``UserPromptSubmit`` → 召回脚本：**该事件不支持 ``mcp_tool``**（实测 2.1.263 静默跳过），
      所以用 command hook 跑脚本，脚本直接调 MCP ``memory_search``，stdout 被注入上下文。
    - ``Stop`` → 上报脚本：``Stop`` 触发时本轮还没落盘，脚本会**后台脱离**、等几秒再读
      transcript（见脚本头注释），hook 本身立即返回，不给每轮加延迟。
      ``SessionEnd`` 不能用：那里没有 MCP 客户端上下文（``mcp_tool hooks are not available
      for the 'SessionEnd' hook event``）。
    """
    search = {"type": "command", "command": hook_command(f"{hooks_dir}/claude-code/user-prompt-recall.mjs")}
    stop = {"type": "command", "command": hook_command(f"{hooks_dir}/claude-code/stop-capture.mjs")}
    # Claude Code 的 settings 校验要求事件下是 **matcher 组**，每组再套 ``hooks`` 数组
    # （``claude doctor`` 对「事件直接挂 handler」的简写形态报
    # `Hook matcher "hooks" must be an array of hook entries` 并静默忽略）。
    # 我们的 hook 对所有调用都生效，matcher 省略即可。
    return {
        "UserPromptSubmit": [{"hooks": [search]}],
        "Stop": [{"hooks": [stop]}],
    }


_OUR_SCRIPTS = (
    "user-prompt-recall.mjs",
    "stop-capture.mjs",
    # 包装脚本（配置里引用的是 .sh / Windows 的 .cmd）
    "user-prompt-recall.sh",
    "stop-capture.sh",
    "user-prompt-recall.cmd",
    "stop-capture.cmd",
    # 早期版本的文件名，重装时一并替换掉
    "octop-user-prompt-recall.mjs",
    "octop-stop-capture.mjs",
)

_OUR_MCP_TOOLS = ("memory_search", "memory_capture")
"""旧版 mcp_tool hook 用的工具名——按工具认，不按 MCP 服务名认。"""


def _is_our_handler(handler):
    """认我们自己留下的 hook：command 形态按脚本名，旧版 mcp_tool 按工具名。

    同一个 ``octop-memory`` 条目可以带不同环境后缀、也可能被用户改名，所以不能拿服务名
    当判据；工具名才是这段接入的契约。
    """
    handler = handler or {}
    if handler.get("type") == "mcp_tool":
        return handler.get("tool") in _OUR_MCP_TOOLS
    command = handler.get("command") or ""
    return any(script in command for script in _OUR_SCRIPTS)


def _handlers_of(entry):
    """一个条目里的 handler 列表：可能是 matcher 组（``{"hooks": [...]}``）或简写形态的单条。

    两种都认 —— 简写是我们自己写的（某些终端的 SDK 侧不保证 ``hooks`` 数组按顺序执行，见
    ``_claude_hooks``），嵌套形态是别人或早期版本写的。
    """
    entry = entry or {}
    nested = entry.get("hooks")
    if isinstance(nested, list):
        return nested
    return [entry]


def _is_our_group(entry):
    """这个 hook 条目是不是我们写的（任一 handler 命中就算）。"""
    return any(_is_our_handler(handler) for handler in _handlers_of(entry))


def _upsert_groups(settings, event, groups):
    """Drop earlier entries that are ours (either形态), keep every other hook, add ours."""
    hooks = settings.setdefault("hooks", {})
    kept = [entry for entry in (hooks.get(event) or []) if not _is_our_group(entry)]
    hooks[event] = kept + list(groups)


def do_claude_code():
    # 两条 hook 都是 command 脚本（召回 / 上报），任何模式都要装脚本 + config.json
    _install_hooks(CC_DIR, "claude-code")
    if IN_PROJECT:
        # MCP 走 Claude 的 local scope（~/.claude.json 里按项目路径存，不进仓库）；
        # hooks 写 settings.local.json（本机私有，不提交），避免没装 octop 的同事
        # 每次提交都被一条指向不存在脚本的 hook 打扰。
        _merge_mcp_local(PROJECT_DIR)
        settings = _project(".claude", "settings.local.json")
        print("  ✓ Claude Code MCP 走 local scope（本机私有、按项目）；hooks → settings.local.json")
        print("      · settings.local.json 需要先信任该工作区，Claude Code 才会读取")
        _warn_global_also_installed("claude-code")
    else:
        _merge_mcp(home / ".claude.json")
        settings = home / ".claude" / "settings.json"
    st = _load(settings)
    if st is not None:
        for event, groups in _claude_hooks(CC_DIR).items():
            _upsert_groups(st, event, groups)
        # 早期版本挂过 SessionEnd（mcp_tool 在那里不可用，会持续报错）：清掉我们留下的那条
        _upsert_groups(st, "SessionEnd", [])
        if not st["hooks"].get("SessionEnd"):
            st["hooks"].pop("SessionEnd", None)
        _dump(settings, st)
        print("  ✓ Claude Code hooks（UserPromptSubmit → 召回脚本；Stop → 上报脚本，后台延迟等落盘）")
        print(f"      · → {settings}")


def do_kiro():
    """Kiro 的 hook 只有 runCommand / askAgent 两种动作，没有 mcp_tool。

    因此：

    * 召回（UserPromptSubmit）用**提示词**（``agent``）：Kiro 不会把 runCommand 的 stdout
      注入上下文，只能让模型经 Kiro 的 MCP 客户端调 ``memory_search``；
    * 上报（Stop）**始终用 command hook** 跑脚本，把整段
      ``~/.kiro/sessions/<workspace>/<sessionId>/messages.jsonl`` 提交进 L0 —— Kiro 侧
      最有价值的就是**原始的用户/助手消息**，绝不能让模型自己总结。

    项目级安装跳过 Kiro 的 MCP 条目（``.kiro/settings/mcp.json`` 自带凭据、会随 git 提交）；
    hooks（只有命令、没有凭据）照常写进项目。
    """
    if IN_PROJECT:
        hooks_dir = _project(".kiro", "hooks")
        print("  · Kiro 的 MCP 条目（.kiro/settings/mcp.json）含凭据、会随 git 提交：项目模式跳过")
        print("      · 需要 Kiro 的 MCP 就用全局安装（不带 project 的 /mcp/memory/setup）")
        _warn_global_also_installed("kiro")
    else:
        _merge_mcp(home / ".kiro" / "settings" / "mcp.json", transport="streamable_http")
        hooks_dir = KIRO_DIR
    _install_hooks(KIRO_DIR, "kiro")

    recall = hooks_dir / "memory-recall-on-start.json"
    _dump(
        recall,
        {
            "version": "v1",
            "hooks": [
                {
                    "name": "octop memory (UserPromptSubmit)",
                    "trigger": "UserPromptSubmit",
                    "enabled": True,
                    "timeout": 30,
                    "action": {"type": "agent", "prompt": SEARCH_PROMPT},
                }
            ],
        },
    )
    print(f"  ✓ Kiro 召回 hook（agent 提示词）已写入 {recall}")

    save = hooks_dir / "memory-save-on-stop.json"
    action = {"type": "command", "command": hook_command(f"{KIRO_DIR}/kiro/stop-capture.mjs")}
    _dump(
        save,
        {
            "version": "v1",
            "hooks": [
                {
                    "name": "octop memory (Stop)",
                    "trigger": "Stop",
                    "enabled": True,
                    "timeout": 120,
                    "action": action,
                }
            ],
        },
    )
    print(f"  ✓ Kiro 上报 hook（command 脚本提交整段 messages.jsonl）已写入 {save}")


_CODEX_HOOKS = (("UserPromptSubmit", "user-prompt-recall"), ("Stop", "stop-capture"))
_CURSOR_HOOKS = (("beforeSubmitPrompt", "user-prompt-recall"), ("stop", "stop-capture"))


def _toml_string(value):
    """TOML 字面串：hook 命令里有双引号、没有单引号，用单引号串就不必转义。"""
    return "'" + value + "'"


def _toml_blocks(text):
    """按表头行列把 TOML 切成块，保留原始文本（首块是文件头/杂项）。"""
    blocks = [[]]
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("[") and not line.lstrip().startswith("#"):
            blocks.append([])
        blocks[-1].append(line)
    return blocks


def _codex_upsert(path):
    """把两条 hook 挂进 ``~/.codex/config.toml``（幂等）。

    结构是 ``[[hooks.<Event>]]`` 容器 + ``[[hooks.<Event>.hooks]]`` 处理项，先删掉我们自己
    写过的处理项（连它那个空容器），再把新处理项插到该事件最后一组之后 —— 不动已有 hook 的
    先后位置，因为 codex 的 hook 信任状态按 ``<config>:<event>:<i>:<j>`` 记索引。
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks, kept = _toml_blocks(text), []
    for block in blocks:
        body = "".join(block)
        header = block[0].strip() if block else ""
        ours = _mentions_dir(body, CODEX_DIR)
        if ours and header.startswith("[[hooks.") and header.endswith(".hooks]]"):
            event = header[len("[[hooks.") : -len(".hooks]]")]
            # 我们自己写的空容器也一起清掉（重装不堆空表）
            if kept and kept[-1][0].strip() == f"[[hooks.{event}]]" and not _codex_container_body(
                kept[-1]
            ):
                kept.pop()
            continue
        kept.append(block)

    additions = {}
    for event, script in _CODEX_HOOKS:
        handler = (
            f"[[hooks.{event}.hooks]]\\n"
            f"command = {_toml_string(hook_command(f'{CODEX_DIR}/codex/{script}.mjs'))}\\n"
            f'type = "command"\\n'
        )
        insert_at = None
        for index, block in enumerate(kept):
            header = block[0].strip() if block else ""
            if header in (f"[[hooks.{event}]]", f"[[hooks.{event}.hooks]]"):
                insert_at = index + 1
        if insert_at is None:
            additions[event] = f"[[hooks.{event}]]\\n\\n{handler}"
        else:
            kept.insert(insert_at, [handler, "\\n"])

    body = "".join("".join(block) for block in kept).rstrip("\\n")
    tail = "\\n\\n".join(additions[event] for event, _ in _CODEX_HOOKS if event in additions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((body + "\\n\\n" if body else "") + tail + "\\n", encoding="utf-8")


def _codex_container_body(block):
    """容器块是否只有表头（没有处理项）。"""
    return not "".join(block[1:]).strip()


def _cursor_upsert(path):
    """把两条 hook 挂进 ``~/.cursor/hooks.json``（幂等，其它事件与别人的 hook 一律保留）。"""
    cfg = _load(path)
    if cfg is None:
        return
    cfg.setdefault("version", 1)
    hooks = cfg.setdefault("hooks", {})
    for event, script in _CURSOR_HOOKS:
        entries = [
            entry for entry in hooks.get(event) or [] if not _mentions_dir(entry, CURSOR_DIR)
        ]
        entries.append({"command": hook_command(f"{CURSOR_DIR}/cursor/{script}.mjs")})
        hooks[event] = entries
    _dump(path, cfg)


def do_codex():
    """Codex：hook 写在 ``~/.codex/config.toml``（``[[hooks.<Event>]]`` + ``type="command"``）。

    codex 对 hook 有信任机制：新写入的 hook 需要用户信任一次才会执行，所以这里只写配置、
    不伪造 ``hooks.state`` 里的 ``trusted_hash``。项目级写进仓库的 ``.codex/config.toml``，
    该仓库被 Codex 信任后才会加载（未信任只加载 skills）。
    """
    _install_hooks(CODEX_DIR, "codex")
    config = _project(".codex", "config.toml") if IN_PROJECT else home / ".codex" / "config.toml"
    _codex_upsert(config)
    print(f"  ✓ Codex hooks（UserPromptSubmit → 召回；Stop → 上报）→ {config}")
    print("      · 首次需在 codex 里信任该 hook（否则不执行）；自动化可加 --dangerously-bypass-hook-trust")
    print("      · Codex 的 MCP 服务由它自己的配置管理，这里不动")
    if IN_PROJECT:
        print("      · 项目级：仓库需被 Codex 信任后才加载这条配置（未信任只加载 skills）")
        _warn_global_also_installed("codex")


def do_cursor():
    """Cursor：hook 写在 ``~/.cursor/hooks.json``（``{"version":1,"hooks":{<event>:[{command}]}}``）。"""
    _install_hooks(CURSOR_DIR, "cursor")
    hooks = _project(".cursor", "hooks.json") if IN_PROJECT else home / ".cursor" / "hooks.json"
    _cursor_upsert(hooks)
    print(f"  ✓ Cursor hooks（beforeSubmitPrompt → 召回；stop → 上报）→ {hooks}")
    print("      · Cursor 的 MCP 服务由它自己的配置管理，这里不动")
    if IN_PROJECT:
        print("      · 项目级 hooks 需要 Cursor 版本支持 .cursor/hooks.json；没生效就改用全局安装")
        _warn_global_also_installed("cursor")


def _dsh_profile():
    """装哪个 profile：OCTOP_DSH_PROFILE，否则按 web / desktop / default 取第一个存在的。"""
    profiles = home / ".dsh" / "profiles"
    wanted = os.environ.get("OCTOP_DSH_PROFILE", "")
    for name in ([wanted] if wanted else ["web", "desktop", "default"]):
        if name and (profiles / name / "package.json").exists():
            return name, profiles / name
    return "", pathlib.Path()


def _run_dsh_install(bundle, profile, profile_dir):
    """把插件装进 profile：优先 dsh CLI，其次直接 pnpm（源码 checkout 常没有 dsh 命令）。

    两条路都在 profile 目录里跑包管理器——DSH 的 CLI 也只是把参数转给 profile 里的 pnpm。
    """
    if shutil.which("dsh"):
        command = ["dsh", "plugin", "--profile", profile, "add", str(bundle)]
    elif shutil.which("pnpm"):
        command = ["pnpm", "add", str(bundle)]
    else:
        print("  · 没找到 dsh / pnpm 命令，无法自动装依赖")
        return None
    done = subprocess.run(command, cwd=str(profile_dir), capture_output=True, text=True)
    if done.returncode != 0:
        tail = (done.stderr or done.stdout or "").strip().splitlines()
        print(f"  ! 装依赖失败（{command[0]} 退出码 {done.returncode}）" + (f"：{tail[-1]}" if tail else ""))
        return False
    return True


def _dsh_bundle_dir():
    """插件目录：~/.dsh/bundles/<name>。"""
    return DSH_DIR.parent / "bundles" / NATIVE_NAME


def _dsh_native_config():
    """原生插件的连接配置：与客户端 MCP 条目同一套语义（MCP 地址 + 用户级 MCP token）。

    ``tokenHeader`` 固定 ``Authorization``（值写成 ``Bearer <token>``）。token 绑定一个专家，
    插件不再需要（也不发送）任何专家标识头。
    """
    return {
        "endpoint": ENTRY_URL,
        "token": TOKEN,
        "tokenHeader": TOKEN_HEADER,
    }


def _dsh_native_config_hint(config):
    if not config["token"]:
        print("  ! 插件没有凭据（token 为空）：召回/上报会 401；重跑并填 MCP token")
    elif not config["endpoint"]:
        print("  ! 插件没有 endpoint：重跑并确认安装地址")


def _yaml_scalar(value):
    """YAML 单引号标量：值里的 ``'`` 写成 ``''``（token / URL 都能安全承载）。"""
    return "'" + str(value).replace("'", "''") + "'"


def _dsh_native_patch_block(config):
    """profile ``cordis.patch.yml`` 里的配置块：**只覆盖 config，不再 insert**。

    插件自己的 bundle patch 已经 insert 了同 id 的行；这里再 insert 一次会让 Loader 组合出
    重复 id（真实 profile 上有先例：duplicate ids 直接崩）。所以只写 id + config —— Loader
    按 id 找到已有行、整块替换 config，同 id 已存在时不会重复追加。
    """
    lines = [
        "# >>> octop-memory-native (octop 安装器写入，整块覆盖) >>>",
        "# 召回/上报在 DSH 进程内完成，不依赖 ~/.dsh/hooks 的 hook 桥接。",
        f"# 回滚：删掉本块，并从该 profile package.json 的 dsh.profile.bundles 移除 {NATIVE_NAME}。",
        f"- id: {NATIVE_NAME}",
        "  config:",
    ]
    for key in ("endpoint", "token", "tokenHeader"):
        lines.append(f"    {key}: {_yaml_scalar(config.get(key, ''))}")
    lines.append(f"# <<< {NATIVE_NAME} <<<")
    return "\\n".join(lines) + "\\n"


def _is_patch_entry(line, row_id):
    """这一行是不是顶层 ``- id: <row_id>``（缩进的 insert 行不算：我们只写顶层块）。"""
    if not line.startswith("-"):
        return False
    rest = line[1:].strip()
    if not rest.startswith("id:"):
        return False
    value = rest[len("id:") :].strip()
    if " #" in value:
        value = value.split(" #", 1)[0]
    return value.strip().strip("'").strip('"') == row_id


def _patch_entry_bounds(lines, row_id):
    """顶层 ``- id: <row_id>`` 条目的 ``[start, end)``，含紧贴其上的注释与结尾 ``# <<< id <<<``。

    注释只在「整段提到本插件」或「紧贴且提到本插件」时算进块里——别人的注释块（通常写在
    自己条目上方）原样保留。结尾标记兼容早期安装器写的 ``# <<< octop-memory-native <<<``。
    """
    entry = None
    for index, line in enumerate(lines):
        if _is_patch_entry(line, row_id):
            entry = index
            break
    if entry is None:
        return None
    start = entry
    comments = []
    cursor = entry - 1
    while cursor >= 0:
        above = lines[cursor]
        if above.strip() == "" or above[:1] in (" ", "\\t"):
            break
        if not above.lstrip().startswith("#"):
            break
        comments.insert(0, cursor)
        cursor -= 1
    if comments:
        joined = "".join(lines[index] for index in comments)
        if row_id not in joined:
            while comments and row_id not in lines[comments[0]]:
                comments.pop(0)
        if comments:
            start = comments[0]
    end = entry + 1
    while end < len(lines) and lines[end][:1] in (" ", "\\t"):
        end += 1  # 条目本体：缩进的 config 行
    probe = end
    while probe < len(lines) and lines[probe].strip() == "":
        probe += 1
    if (
        probe < len(lines)
        and lines[probe].strip().startswith("#")
        and "<<<" in lines[probe]
        and row_id in lines[probe]
    ):
        end = probe + 1  # 结尾标记（旧版在标记前留了空行，一起清掉）
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return start, end


def _replace_native_patch(text, block, row_id=None):
    """替换/追加配置块；其余内容（别人的条目、注释）逐字保留。"""
    row_id = row_id or NATIVE_NAME
    lines = text.splitlines(keepends=True)
    bounds = _patch_entry_bounds(lines, row_id)
    if bounds is None:
        base = text.rstrip("\\n")
        return (base + "\\n\\n" if base else "") + block
    start, end = bounds
    tail = "".join(lines[end:])
    return "".join(lines[:start]) + block + ("\\n" if tail else "") + tail


def _write_dsh_native_patch(profile_dir, config):
    """把配置块写进 profile 的 cordis.patch.yml：同 id 已存在则整块替换（写前备份）。"""
    patch = profile_dir / "cordis.patch.yml"
    existing = patch.read_text(encoding="utf-8") if patch.exists() else ""
    updated = _replace_native_patch(existing, _dsh_native_patch_block(config))
    if updated == existing:
        print(f"  ✓ DSH profile 的 cordis.patch.yml 已是最新配置块（id: {NATIVE_NAME}）→ {patch}")
        return
    if patch.exists():
        backup = patch.with_name(patch.name + ".octop.bak")
        backup.write_text(existing, encoding="utf-8")
        print(f"      · 原 cordis.patch.yml 已备份 → {backup}")
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(updated, encoding="utf-8")
    print(f"  ✓ 已写入 DSH profile 的 cordis.patch.yml（id: {NATIVE_NAME}，其余内容保留）→ {patch}")


def _dsh_native_spec_is_ours(spec, bundle, profile_dir):
    """profile 里登记的这个依赖是不是就指向我们的插件目录（link: / file: 两种写法都认）。"""
    text = str(spec or "")
    if text.startswith("link:"):
        target = text[len("link:") :]
    elif text.startswith("file:"):
        target = text[len("file:") :]
    else:
        return False
    if not os.path.isabs(target):
        target = os.path.join(str(profile_dir), target)
    try:
        return os.path.realpath(target) == os.path.realpath(str(bundle))
    except OSError:
        return False


def _register_dsh_native(profile_dir, bundle, profile):
    """登记 profile：dependencies + dsh.profile.bundles（幂等；已指向本插件就不动）。"""
    package = profile_dir / "package.json"
    config = _load(package)
    if not isinstance(config, dict):
        return False
    changed = []
    dependencies = config.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {}
        config["dependencies"] = dependencies
    if not _dsh_native_spec_is_ours(dependencies.get(NATIVE_NAME), bundle, profile_dir):
        dependencies[NATIVE_NAME] = "link:" + str(bundle)
        changed.append("dependencies")
    dsh = config.get("dsh")
    if not isinstance(dsh, dict):
        dsh = {}
        config["dsh"] = dsh
    profile_config = dsh.get("profile")
    if not isinstance(profile_config, dict):
        profile_config = {}
        dsh["profile"] = profile_config
    bundles = profile_config.get("bundles")
    if not isinstance(bundles, list):
        bundles = []
        profile_config["bundles"] = bundles
    if NATIVE_NAME not in bundles:
        bundles.append(NATIVE_NAME)
        changed.append("dsh.profile.bundles")
    if not changed:
        print(f"  ✓ profile「{profile}」已登记 {NATIVE_NAME}（不重复写）")
        return True
    _dump(package, config)
    print(f"  ✓ 已登记 profile「{profile}」的 {' + '.join(changed)} → {package}")
    return True


def _link_dsh_native_module(profile_dir, bundle):
    """把插件放进 profile 的 node_modules：包管理器没装成 / 装的是旧副本时自己补。

    POSIX 用目录软链（与 pnpm 对本地目录的 ``link:`` 语义一致）；Windows 建软链需要开发者
    模式或管理员权限，失败就整目录拷贝 —— Node 只按目录解析，两种都能用。
    """
    modules = profile_dir / "node_modules"
    target = modules / NATIVE_NAME
    if target.exists() and os.path.realpath(str(target)) == os.path.realpath(str(bundle)):
        print(f"  ✓ profile 的 node_modules 已指向插件目录 → {target}")
        return "ok"
    modules.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        print(f"  · profile 里已有 {NATIVE_NAME} 目录（不是本次的路径）：替换成指向插件目录的链接")
        shutil.rmtree(target)
    try:
        os.symlink(str(bundle), str(target), target_is_directory=True)
        print(f"  ✓ profile 的 node_modules 已链接到插件目录 → {target}")
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass
    try:
        shutil.copytree(bundle, target)
        print(f"  ✓ profile 的 node_modules 已复制插件（无软链权限时的等价做法）→ {target}")
        return "copy"
    except OSError as exc:
        print(f"  ! 无法把插件放进 {target}（{exc}）：DSH 会加载不到插件")
        return ""


def _install_dsh_native_files():
    """把 vendored 插件写到 ~/.dsh/bundles/<name>（逐字节还原，不在这里改插件代码）。"""
    if not NATIVE_FILES:
        print("  ! 安装器里没有插件源码（dsh_native_plugin 缺失）：跳过 DSH")
        return None
    bundle = _dsh_bundle_dir()
    for name, blob in NATIVE_FILES.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(blob))
    print(f"  ✓ DSH 原生插件 {NATIVE_NAME} → {bundle}（{len(NATIVE_FILES)} 个文件）")
    return bundle


def _dsh_profile_dirs():
    """所有已有 package.json 的 DSH profile（web / desktop / default / 自定义）。"""
    profiles = home / ".dsh" / "profiles"
    if not profiles.is_dir():
        return []
    return sorted(path for path in profiles.iterdir() if (path / "package.json").exists())


def _drop_dsh_bundle_name(profile_dir, names):
    """从某个 profile 的 dsh.profile.bundles 去掉指定名字（返回实际去掉的）。"""
    package = profile_dir / "package.json"
    config = _load(package)
    if not isinstance(config, dict):
        return []
    dsh = config.get("dsh")
    profile_config = dsh.get("profile") if isinstance(dsh, dict) else None
    bundles = profile_config.get("bundles") if isinstance(profile_config, dict) else None
    if not isinstance(bundles, list):
        return []
    gone = [name for name in names if name in bundles]
    if not gone:
        return []
    profile_config["bundles"] = [name for name in bundles if name not in names]
    _dump(package, config)
    return gone


def _remove_dsh_legacy_hooks():
    """从 hooks 方案升级过来：拆掉旧桥接与 preset —— 两套接入同时生效会双触发。"""
    removed = []
    bridge = DSH_DIR / "octop-hooks.json"
    if bridge.exists():
        bridge.unlink()
        removed.append(str(bridge))
    scripts = DSH_DIR / "dsh"  # 入口脚本目录；config.json 留着（插件拿它当兜底配置）
    if scripts.exists():
        shutil.rmtree(scripts)
        removed.append(str(scripts))
    preset = DSH_DIR.parent / "bundles" / "dsh-memory-share"
    if preset.exists():
        shutil.rmtree(preset)
        removed.append(str(preset))
    for profile_dir in _dsh_profile_dirs():
        for name in _drop_dsh_bundle_name(
            profile_dir, ("dsh-memory-share", "octop-dsh-memory-share")
        ):
            removed.append(f"{profile_dir.name}:{name}")
    if not removed:
        print("  · 没有旧的 hooks 桥接 / preset bundle（干净安装）")
        return
    print("  ✓ 已移除旧的 hooks 桥接 / preset bundle（避免与原生插件双触发）：")
    for item in removed:
        print(f"      · {item}")


def _dsh_mcp_hint():
    """MCP 条目仍由 DSH 自己管理：插件不登记它，这里只把参数打出来方便手动加。"""
    print("  · DSH 的 MCP 服务请在它的 MCP 面板/CLI 里添加（该条目由 DSH 自己管理）：")
    print(f"      url: {URL}")
    print(f"      headers: {json.dumps(_entry()['headers'], ensure_ascii=False)}")


def _install_dsh_native():
    """原生插件安装：写插件目录 → 拆旧桥接 → 登记 profile → 写 cordis.patch.yml 配置块。

    安装后 DSH 直接可用：插件行由插件自带的 bundle patch（dsh.bundle.patch）insert，profile
    的 cordis.patch.yml 只按同 id 覆盖 config（endpoint / token / tokenHeader）。
    """
    bundle = _install_dsh_native_files()
    if bundle is None:
        return
    _remove_dsh_legacy_hooks()
    config = _dsh_native_config()
    profile, profile_dir = _dsh_profile()
    if not profile:
        print("  ! 没找到 DSH profile（~/.dsh/profiles/<web|desktop|default>），跳过自动登记")
        print("  · 手动两步：")
        print(f"      1) 在 profile 目录执行：pnpm add {bundle}")
        print(f"      2) 把 {NATIVE_NAME} 加进该目录 package.json 的 dsh.profile.bundles，重启 DSH")
        _dsh_native_config_hint(config)
        _dsh_mcp_hint()
        return
    if _run_dsh_install(bundle, profile, profile_dir) is None:
        print("  · 没有 dsh / pnpm 命令：直接补 node_modules 与 package.json 登记")
    _link_dsh_native_module(profile_dir, bundle)
    _register_dsh_native(profile_dir, bundle, profile)
    _write_dsh_native_patch(profile_dir, config)
    print(
        f"  ✓ DSH 原生插件已装进 profile「{profile}」：重启 DSH 后生效"
        "（召回/上报在进程内，不再依赖 hook）"
    )
    _dsh_native_config_hint(config)
    _dsh_mcp_hint()


def do_dsh():
    """DSH 记忆接入：装原生插件（进程内召回/上报），不装 hook 桥接、不装 preset。

    DSH 没有项目级配置：hooks 的 ``configPath`` 是进程级、MCP 在 profile / 全局 patch 里，
    所以项目模式直接跳过（不写项目里的任何文件），且不算失败。
    """
    if IN_PROJECT:
        print("  · DSH 没有项目级配置（hooks 是进程级、MCP 在 profile 里）：项目模式跳过 DSH")
        return
    _install_dsh_native()


home = pathlib.Path(os.path.expanduser("~"))
URL = os.environ["OCTOP_URL"]
HOOK_URL = os.environ.get("OCTOP_HOOK_URL") or URL   # hooks 实际 POST 的地址（直连）
TOKEN = os.environ["OCTOP_TOKEN"]
# 用户级 MCP token 只有一个方言：``Authorization: Bearer <token>``（身份由 token 表达）。
TOKEN_HEADER = "Authorization"
ENTRY_URL = URL
NAME = os.environ["OCTOP_SERVER_NAME"]
NODE = os.environ.get("OCTOP_NODE") or "node"  # 安装时解析出的绝对路径（非 login shell 也能跑）

# ---- 安装范围：全局（默认）或只装到某个项目 ----
# 项目级只在项目里写「注册」（hooks 命令 / MCP 条目）；hook 脚本与 config.json（含 token）
# 始终留在用户目录，因此项目里不会出现脚本或凭据。
PROJECT = (os.environ.get("OCTOP_PROJECT_DIR") or "").strip()
PROJECT_DIR = pathlib.Path(PROJECT).expanduser() if PROJECT else None
IN_PROJECT = PROJECT_DIR is not None
PROJECT = str(PROJECT_DIR) if IN_PROJECT else ""


def _project(*parts):
    """项目级安装里某个文件/目录的绝对路径（全局模式不会被调用）。"""
    return PROJECT_DIR.joinpath(*parts)


def _global_hooks_present(host):
    """全局配置里是否已经注册过我们的 hook —— 项目+全局都装会双触发。"""
    if host == "claude-code":
        settings = _load(home / ".claude" / "settings.json") or {}
        return any(
            _is_our_group(entry)
            for entries in (settings.get("hooks") or {}).values()
            for entry in (entries or [])
        )
    if host == "kiro":
        return (home / ".kiro" / "hooks" / "memory-recall-on-start.json").exists()
    if host == "codex":
        path = home / ".codex" / "config.toml"
        return path.exists() and _mentions_dir(path.read_text(encoding="utf-8"), CODEX_DIR)
    if host == "cursor":
        cfg = _load(home / ".cursor" / "hooks.json")
        return cfg is not None and _mentions_dir(cfg, CURSOR_DIR)
    return False


def _warn_global_also_installed(host):
    if not IN_PROJECT or not _global_hooks_present(host):
        return
    print(f"      ! 全局也装过 {host} 的 octop hooks：两处都注册会双触发")
    print("      · 只要项目级就先跑全局卸载（不带 project 的 /mcp/memory/uninstall）")


def _merge_mcp_local(project):
    """Claude Code 的 local scope：``~/.claude.json`` 里按项目路径存 MCP 条目（不进仓库）。"""
    key = os.path.realpath(str(project))
    path = home / ".claude.json"
    cfg = _load(path)
    if cfg is None:
        return
    projects = cfg.get("projects")
    if not isinstance(projects, dict):
        projects = cfg["projects"] = {}
    bucket = projects.get(key)
    if not isinstance(bucket, dict):
        bucket = projects[key] = {}
    servers = bucket.get("mcpServers")
    if not isinstance(servers, dict):
        servers = bucket["mcpServers"] = {}
    entry = _entry()
    ours = _octop_servers(servers)
    reused = next(
        (name for name in ours if (servers.get(name) or {}).get("url") == entry["url"]), ""
    )
    if reused:
        print(f"  ✓ MCP 服务 {reused}（local scope 已有且端点一致，复用）→ {path}")
        return
    if ours:
        print(f"  · 项目 {key} 已有别的 octop 服务：{', '.join(ours)}（端点不同，保持原样）")
        return
    servers[NAME] = entry
    _dump(path, cfg)
    print(f"  ✓ MCP 服务 {NAME}（Claude Code local scope，项目 {key}）→ {path}")
    print("      · 本机私有、按项目的条目：不进仓库，也不需要 .mcp.json 审批")


def hook_command(script_path):
    """一条 command hook 的 ``command``：**独立包装脚本**的路径（写它、返回它）。

    不把 node 绝对路径 / ``NODE_OPTIONS`` / 失败兜底那一长串直接塞进 JSON-TOML 字符串 ——
    里面的引号与 ``$`` 很容易把配置写坏，也难读（用户反馈过这一点）。包装脚本负责：

    * 用安装时解析出的 node **绝对路径**跑 ``.mjs``（hook 由终端派生，非 login shell 里
      没有 nvm 的 node，裸 ``node`` 会找不到）；
    * ``OCTOP_USE_SYSTEM_CA=1`` 时导出 ``NODE_OPTIONS=--use-system-ca``（Node 22.15+）：
      Node 自带的证书库不认企业根（macOS 钥匙串 / Windows 证书库里有、Node 没有），
      不加这行 hook 里的 fetch 会失败；已有 ``NODE_OPTIONS`` 时追加，不覆盖；
    * 失败时把原因打到 stderr —— command hook 的非 0 退出是**静默**的。
    """
    mjs = pathlib.Path(str(script_path))
    if HOOK_WRAPPER == "cmd":
        return _cmd_hook_command(mjs)
    return _sh_hook_command(mjs)


def _sh_hook_command(mjs):
    """POSIX：写 ``.sh`` 包装脚本，配置里只引用它的路径。"""
    wrapper = mjs.with_suffix(".sh")
    lines = [
        "#!/bin/sh",
        "# octop memory hook（安装器生成，勿手改）：配置里只引用本文件路径",
    ]
    if os.environ.get("OCTOP_USE_SYSTEM_CA") == "1":
        lines.append('export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--use-system-ca"')
    run = f"{shlex.quote(str(NODE))} {shlex.quote(str(mjs))}"
    failure = 'echo "octop-memory: hook 执行失败（node 路径不对或脚本报错）" >&2'
    lines.append(f"{run} || {failure}")
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return shlex.quote(str(wrapper))


def _cmd_hook_command(mjs):
    """Windows：写 ``.cmd`` 包装脚本，配置里只引用它的路径。

    Windows 的客户端把 hook 命令交给系统 shell，``cmd.exe`` 能直接跑 ``.cmd`` —— 不要求装
    Git Bash，也不用把带空格/引号的 node 绝对路径塞进 JSON-TOML。

    文件内容是 **ASCII**（英文提示）：cmd.exe 按系统 ANSI 代码页读批处理文件，中文提示在
    cp936 / cp65001 之间会乱码；落盘编码用 ``mbcs``，路径里的中文用户名才不会被读错。
    """
    wrapper = mjs.with_suffix(".cmd")
    lines = [
        "@echo off",
        "rem octop memory hook (generated by installer; config only references this file)",
        "setlocal",
    ]
    if os.environ.get("OCTOP_USE_SYSTEM_CA") == "1":
        lines += [
            "if defined NODE_OPTIONS (",
            '  set "NODE_OPTIONS=%NODE_OPTIONS% --use-system-ca"',
            ") else (",
            '  set "NODE_OPTIONS=--use-system-ca"',
            ")",
        ]
    lines.append(f'"{NODE}" "{mjs}"')
    lines.append("if errorlevel 1 echo octop-memory: hook failed (node path or script error) 1>&2")
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text("\\r\\n".join(lines) + "\\r\\n", encoding=_wrapper_encoding())
    return '"' + str(wrapper) + '"'


def _wrapper_encoding():
    """包装脚本的落盘编码：cmd.exe 读系统 ANSI（``mbcs``），POSIX 用 UTF-8。"""
    return "mbcs" if os.name == "nt" else "utf-8"


CC_DIR = pathlib.Path(os.environ["OCTOP_CC_DIR"]).expanduser()
KIRO_DIR = pathlib.Path(os.environ["OCTOP_KIRO_DIR"]).expanduser()
DSH_DIR = pathlib.Path(os.environ["OCTOP_DSH_DIR"]).expanduser()
CODEX_DIR = pathlib.Path(os.environ["OCTOP_CODEX_DIR"]).expanduser()
CURSOR_DIR = pathlib.Path(os.environ["OCTOP_CURSOR_DIR"]).expanduser()
HOOK_FILES = {
    host: json.loads(os.environ["OCTOP_FILES_" + host.upper().replace("-", "_")])
    for host in ("claude-code", "kiro", "codex", "cursor")
}
# 原生插件（octop-memory-native）的 vendored 源码：{相对路径: base64}，与 hooks 同一套 payload
# 机制（安装器渲染时注入，避免脚本里再抄一份插件代码）。
NATIVE_FILES = json.loads(os.environ["OCTOP_FILES_NATIVE"])
NATIVE_NAME = "octop-memory-native"

for terminal in os.environ["OCTOP_TERMINALS"].split(","):
    terminal = terminal.strip()
    if not terminal:
        continue
    print(f"· {terminal}")
    {
        "claude-code": do_claude_code,
        "kiro": do_kiro,
        "dsh": do_dsh,
        "codex": do_codex,
        "cursor": do_cursor,
    }[terminal]()

print("  · hook 角色：用户提交时召回（CC / Codex 的 UserPromptSubmit，Cursor 的 beforeSubmitPrompt）；")
print("    回合结束时上报会话 transcript（Stop / Cursor 的 stop）")
print(f"  · hooks 直连 {HOOK_URL}；客户端 MCP 条目 {ENTRY_URL}（只用 Authorization: Bearer <MCP token>）")
print("  · DSH 用原生插件 octop-memory-native 在进程内召回/上报（不装 hooks 桥接）")
print("  · octop memory 接入完成（可重复执行，不会影响其它 MCP/hook 条目）")
'''.strip()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _host_manifest(host: str) -> str:
    """``{relative path: base64}`` for one host: its entries + the shared lib modules."""
    files = (*_LIB_FILES, *HOST_FILES[host])
    payload = {name: _b64((_HOOKS_SRC / name).read_text(encoding="utf-8")) for name in files}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _dsh_native_manifest() -> str:
    """``{relative path: base64}`` for the vendored native plugin (``octop-memory-native``).

    Tolerant of a checkout that has not vendored the plugin yet: the installer still renders
    (``/setup`` must never 500), and the DSH step then refuses with a clear message instead
    of writing a half-empty bundle.
    """
    payload: dict[str, str] = {}
    for name in _DSH_NATIVE_FILES:
        path = _DSH_NATIVE_SRC / name
        if path.is_file():
            payload[name] = _b64(path.read_text(encoding="utf-8"))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _server_name(mcp_url: str) -> str:
    """``octop-memory-local`` for a loopback endpoint, ``octop-memory`` otherwise."""
    host = mcp_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return "octop-memory-local" if host in ("127.0.0.1", "localhost", "::1") else "octop-memory"


def _sh_single_quote(value: str) -> str:
    """Always return a single-quoted shell literal (safe for script embedding).

    Unlike ``shlex.quote`` (which may leave safe tokens unquoted), this keeps the
    ``VAR='…'`` form used throughout the installer and escapes embedded quotes.
    """
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _ps_single_quote(value: str) -> str:
    """PowerShell single-quoted literal: ``'…'``, embedded ``'`` doubled (no interpolation)."""
    return "'" + str(value).replace("'", "''") + "'"


def _ps_home_rel(path: str) -> str:
    r"""``~/.claude/hooks`` → ``.claude\hooks``（PowerShell 里 Join-Path $HOME 的相对段）。"""
    return path.replace("~/", "", 1).replace("/", "\\")


def render_setup_script(
    *,
    mcp_url: str,
    hook_url: str = "",
    agent_id: str = "",
    terminals: str = "",
    default_token: str = "",
    project: str = "",
) -> str:
    """Render the interactive installer (POSIX ``sh``).

    ``mcp_url`` is the address registered into the client MCP entries; ``hook_url`` is what
    the hooks POST to, defaulting to ``mcp_url`` (a deployment that fronts the MCP mount
    with an ingress can point the entries elsewhere).

    ``default_token`` is an **optional prefill** for the user-level MCP token — callers pass
    an empty string, because the installer must never ship a credential of its own. The
    script falls back to ``OCTOP_MEMORY_TOKEN`` first and only then uses this value.
    ``terminals`` (comma list) only prefills the terminal prompt.

    ``agent_id`` is accepted for backwards compatibility and **ignored**: the MCP token is
    bound to one expert, so there is no expert id to install (and no ``X-Octop-Agent-Id``).

    ``project`` is the **prefill** path for a project-scoped install (the interactive
    default). Non-interactive runs read ``OCTOP_PROJECT_DIR`` — the environment wins, and an
    explicitly empty value forces a global install. Omitted = global.
    """
    hook_url = hook_url or mcp_url
    token_literal = _sh_single_quote(default_token) if default_token else "''"
    # Query-string prefills must be shell-safe (same escaping as DEFAULT_TOKEN).
    url_literal = _sh_single_quote(mcp_url)
    hook_url_literal = _sh_single_quote(hook_url)
    terminals_literal = _sh_single_quote(terminals) if terminals else "''"
    project_literal = _sh_single_quote(project) if project else "''"
    default_token_line = f"DEFAULT_TOKEN={token_literal}" if default_token else ""
    default_token_block = (
        f"""if [ -z "$TOKEN" ] && [ -n {token_literal} ]; then
  TOKEN={token_literal}
  echo "  · token：用安装链接预填的值（个人 MCP token）"
fi"""
        if default_token
        else ""
    )
    return f"""#!/bin/sh
# octop memory — 本地终端接入（hooks 发往 {hook_url}；可重复执行）
set -eu

# Git Bash / MSYS 上也能跑，但 Windows 原生（不需要 Git Bash）请用 PowerShell 版：
#   irm "{mcp_url}?os=windows" | iex
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) echo "  ! 检测到 Windows（Git Bash/MSYS）：推荐用原生安装器 irm \\"{mcp_url}?os=windows\\" | iex；这里按 sh 方式继续" >&2 ;;
esac

# hook 包装脚本用 .sh（与 sh 环境一致）；Windows 原生安装器走 ?os=windows 的 PowerShell 版
OCTOP_HOOK_WRAPPER=sh
export OCTOP_HOOK_WRAPPER

URL={url_literal}
HOOK_URL={hook_url_literal}
{default_token_line}
DEFAULT_TERMINALS={terminals_literal}
DEFAULT_PROJECT={project_literal}
CC_DIR='{HOOKS_DIRS["claude-code"]}'
KIRO_DIR='{HOOKS_DIRS["kiro"]}'
DSH_DIR='{HOOKS_DIRS["dsh"]}'
CODEX_DIR='{HOOKS_DIRS["codex"]}'
CURSOR_DIR='{HOOKS_DIRS["cursor"]}'

# ---- 1) 检测本机装了哪些终端（目录或命令任一命中）
have_claude=0; have_kiro=0; have_dsh=0; have_codex=0; have_cursor=0
{{ [ -e "$HOME/.claude.json" ] || [ -d "$HOME/.claude" ] || command -v claude >/dev/null 2>&1; }} && have_claude=1
{{ [ -d "$HOME/.kiro" ] || command -v kiro >/dev/null 2>&1; }} && have_kiro=1
{{ [ -d "$HOME/.dsh" ] || command -v dsh >/dev/null 2>&1; }} && have_dsh=1
{{ [ -d "$HOME/.codex" ] || command -v codex >/dev/null 2>&1; }} && have_codex=1
{{ [ -d "$HOME/.cursor" ] || command -v cursor >/dev/null 2>&1; }} && have_cursor=1

DETECTED=''
[ "$have_claude" = 1 ] && DETECTED="$DETECTED claude-code"
[ "$have_kiro" = 1 ] && DETECTED="$DETECTED kiro"
[ "$have_dsh" = 1 ] && DETECTED="$DETECTED dsh"
[ "$have_codex" = 1 ] && DETECTED="$DETECTED codex"
[ "$have_cursor" = 1 ] && DETECTED="$DETECTED cursor"
[ -n "$DETECTED" ] || DETECTED='claude-code'

echo "octop memory 接入 → {mcp_url}"
echo "检测到："
[ "$have_claude" = 1 ] && echo "  1) Claude Code　（hook 装到 ~/.claude/hooks-events）"
[ "$have_kiro" = 1 ] && echo "  2) Kiro　　　　（hook 装到 ~/.kiro/hooks）"
[ "$have_dsh" = 1 ] && echo "  3) DSH　　　　（装原生插件 octop-memory-native，进程内召回/上报）"
[ "$have_codex" = 1 ] && echo "  4) Codex　　　（hook 装到 ~/.codex/hooks，配置写 ~/.codex/config.toml）"
[ "$have_cursor" = 1 ] && echo "  5) Cursor　　　（hook 装到 ~/.cursor/hooks，配置写 ~/.cursor/hooks.json）"

# 有 controlling tty 才交互：curl | sh 时 stdin 是脚本本身，读它会把脚本吃掉；
# 没有 tty（CI/cron）时依赖环境变量，缺什么就明确报错而不是盲读 stdin。
HAS_TTY=0
if (true </dev/tty) 2>/dev/null; then HAS_TTY=1; fi

ask() {{  # ask <提示> <默认值>
  if [ "$HAS_TTY" = 1 ]; then
    printf '%s' "$1" > /dev/tty 2>/dev/null || true
    read -r _answer < /dev/tty || _answer=''
  else
    _answer=''
  fi
  if [ -n "$_answer" ]; then printf '%s' "$_answer"; else printf '%s' "$2"; fi
}}

# ---- 2) 选终端：交互式清单（↑↓ 移动 · 空格 选择 · a 全选 · 回车 确认）；
#         没有 tty 或没有 python3 时回退到数字输入。
TERMINALS="${{OCTOP_TERMINALS:-$DEFAULT_TERMINALS}}"
if [ -z "$TERMINALS" ] && [ "$HAS_TTY" = 1 ]; then
  _picked=''
  if command -v python3 >/dev/null 2>&1; then
    set --
    [ "$have_claude" = 1 ] && set -- "$@" "claude-code|Claude Code　（hook 装到 ~/.claude/hooks-events）"
    [ "$have_kiro" = 1 ] && set -- "$@" "kiro|Kiro　（hook 装到 ~/.kiro/hooks）"
    [ "$have_dsh" = 1 ] && set -- "$@" "dsh|DSH　（装原生插件 octop-memory-native）"
    [ "$have_codex" = 1 ] && set -- "$@" "codex|Codex　（hook 装到 ~/.codex/hooks）"
    [ "$have_cursor" = 1 ] && set -- "$@" "cursor|Cursor　（hook 装到 ~/.cursor/hooks）"
    _picked="$(python3 - "$@" 2>/dev/null <<'OCTOP_SELECT'
{_SELECT_PY}
OCTOP_SELECT
)" || _picked=''
  fi
  if [ -n "$_picked" ]; then
    TERMINALS="$_picked"
  else
    # 回退：数字输入（1,2 / 1 3 / 12 / a=全部；回车 = 全部检测到的；选不中会重问）
    _attempt=0
    while [ -z "$TERMINALS" ] && [ "$_attempt" -lt 3 ]; do
      _attempt=$((_attempt + 1))
      printf '要配置哪些？(可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的): ' > /dev/tty
      read -r _pick < /dev/tty || _pick=''
      _chosen=''
      case "$_pick" in
        ''|a|A|all|ALL|全部) _chosen="$DETECTED" ;;
        *)
          for _n in $(printf '%s' "$_pick" | tr ',' ' '); do
            case "$_n" in
              [0-9][0-9]*) _items="$(printf '%s' "$_n" | fold -w1 | tr '\\n' ' ')" ;;
              *) _items="$_n" ;;
            esac
            for _i in $_items; do
              case "$_i" in
                1) _add="$([ "$have_claude" = 1 ] && echo claude-code)" ;;
                2) _add="$([ "$have_kiro" = 1 ] && echo kiro)" ;;
                3) _add="$([ "$have_dsh" = 1 ] && echo dsh)" ;;
                4) _add="$([ "$have_codex" = 1 ] && echo codex)" ;;
                5) _add="$([ "$have_cursor" = 1 ] && echo cursor)" ;;
                *) _add='' ;;
              esac
              if [ -z "$_add" ]; then
                echo "  ? 已忽略：${{_i}}（未检测到或无法识别）" >&2
              else
                case ",$_chosen," in *",$_add,"*) ;; *) _chosen="$_chosen,$_add" ;; esac
              fi
            done
          done
          ;;
      esac
      TERMINALS="$(printf '%s' "$_chosen" | sed 's/^,//')"
      [ -n "$TERMINALS" ] || echo "  ! 没有选中任何已检测到的终端，请重选（1-5，或 a=全部）" >&2
    done
  fi
fi

[ -n "$TERMINALS" ] || {{ echo "没有可配置的终端" >&2; exit 1; }}

# ---- 2.5) 安装范围：全局（默认）还是只装到某个项目
# 项目级只在项目里写「注册」（hooks 命令 / MCP 条目）；hook 脚本与 config.json（含 token）
# 始终留在本机用户目录，项目里不出现脚本。Kiro 的 MCP 条目自带凭据、DSH 没有项目级配置，
# 这两个在项目模式会被跳过（见合并脚本里的提示）。
# ?project= 预填只在**交互式**生效（变成默认答案）；非交互只认 OCTOP_PROJECT_DIR ——
# 显式置空 = 强制全局。
if [ "${{OCTOP_PROJECT_DIR+x}}" = x ]; then
  PROJECT_DIR="$OCTOP_PROJECT_DIR"
else
  PROJECT_DIR=''
fi
if [ -z "$PROJECT_DIR" ] && [ "$HAS_TTY" = 1 ]; then
  echo "安装范围："
  echo "  1) 全局（所有项目生效，默认）"
  echo "  2) 只装到某个项目（项目里只写注册；脚本和凭据留在本机）"
  _default_scope=1
  if [ -n "$DEFAULT_PROJECT" ]; then _default_scope=2; fi
  _scope="$(ask "选择 [1/2]: " "$_default_scope")"
  case "$_scope" in
    2|p|P|project|项目)
      _project_default="${{DEFAULT_PROJECT:-$PWD}}"
      PROJECT_DIR="$(ask "项目根目录 [$_project_default]: " "$_project_default")"
      ;;
  esac
fi
if [ -n "$PROJECT_DIR" ]; then
  case "$PROJECT_DIR" in
    "~") PROJECT_DIR="$HOME" ;;
    "~/"*) PROJECT_DIR="$HOME/${{PROJECT_DIR#\\~/}}" ;;
  esac
  if [ ! -d "$PROJECT_DIR" ]; then
    echo "  ! 项目目录不存在（或不是目录）：$PROJECT_DIR" >&2
    exit 1
  fi
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
  if [ ! -w "$PROJECT_DIR" ]; then
    echo "  ! 项目目录不可写：$PROJECT_DIR" >&2
    exit 1
  fi
  echo "  · 安装范围：项目级 → $PROJECT_DIR"
  echo "      · 项目里只写注册（hooks 命令 / MCP 条目）；hook 脚本与 token 留在本机用户目录"
  echo "      · 不入仓库：Claude Code 走 ~/.claude.json 的 local scope 与 .claude/settings.local.json"
  echo "      · Codex / Cursor 的项目文件里只有命令（不含凭据）"
  echo "      · 跳过：Kiro 的 .kiro/settings/mcp.json（含凭据）、DSH（没有项目级配置）"
  if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "      · 提示：不是 git 仓库根目录（项目级配置仍可用，只是不会进版本库）"
  fi
fi
export OCTOP_PROJECT_DIR="$PROJECT_DIR"

# ---- 3) 凭据：用户级 MCP token（omcp_…），条目与 hooks 共用同一份
TOKEN="${{OCTOP_MEMORY_TOKEN:-}}"
{default_token_block}
if [ -z "$TOKEN" ] && [ "$HAS_TTY" = 1 ]; then
  stty -echo < /dev/tty 2>/dev/null || true
  printf 'MCP token（omcp_…，在 Octop 的 /api/memory-mcp/tokens 创建；不回显）: ' > /dev/tty
  read -r _t < /dev/tty || _t=''
  stty echo < /dev/tty 2>/dev/null || true
  printf '\\n' > /dev/tty
  [ -n "$_t" ] && TOKEN="$_t"
fi
[ -n "$TOKEN" ] || {{ echo "缺少 MCP token：非交互运行时请设 OCTOP_MEMORY_TOKEN=<omcp_…>" >&2; exit 1; }}
TOKEN_HEADER='Authorization'
echo "  · 客户端 MCP 条目与 hooks：${{URL}}（只用 Authorization: Bearer <MCP token>）"

command -v node >/dev/null 2>&1 || echo "  ! 未找到 node：hook 需要它，请先安装 Node.js" >&2
command -v python3 >/dev/null 2>&1 || {{ echo "  ! 未找到 python3：无法合并终端配置" >&2; exit 1; }}

# ---- 3.5) 解析 node 绝对路径：hook 由终端派生，常在非 login shell 里跑，
# nvm 的 node 不在 PATH —— 写裸 node 会静默失败（command hook 非 0 退出不报错）。
NODE_BIN="${{OCTOP_NODE:-}}"
if [ -z "$NODE_BIN" ] && command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
fi
if [ -z "$NODE_BIN" ] && [ -d "$HOME/.nvm/versions/node" ]; then
  _ver="$(ls -1 "$HOME/.nvm/versions/node" 2>/dev/null | sort | tail -n 1)"
  [ -n "$_ver" ] && [ -x "$HOME/.nvm/versions/node/$_ver/bin/node" ] && NODE_BIN="$HOME/.nvm/versions/node/$_ver/bin/node"
fi
for _cand in /opt/homebrew/bin/node /usr/local/bin/node "$HOME/.volta/bin/node" /usr/bin/node; do
  if [ -z "$NODE_BIN" ] && [ -x "$_cand" ]; then NODE_BIN="$_cand"; fi
done
if [ -z "$NODE_BIN" ] || [ ! -x "$NODE_BIN" ]; then
  NODE_BIN=node
  echo "  ! 找不到 node 的绝对路径：hook 里只能写裸 node，非 login shell 下可能静默失败" >&2
else
  echo "  · node: $NODE_BIN"
fi
export OCTOP_NODE="$NODE_BIN"

# Node 22.15+ 的 --use-system-ca 读操作系统证书库。企业根不在 Node 自带库里时，
# 不加这个前缀，hook 和下面的端点自检都会 TypeError: fetch failed。
USE_SYSTEM_CA=0
if "$NODE_BIN" --use-system-ca -e 'process.exit(0)' >/dev/null 2>&1; then
  USE_SYSTEM_CA=1
  echo "  · node 使用系统证书库（--use-system-ca）"
else
  echo "  ! 当前 node 不支持 --use-system-ca（需要 22.15+）：企业根证书下 hook 的 fetch 可能失败" >&2
fi
export OCTOP_USE_SYSTEM_CA="$USE_SYSTEM_CA"
if [ "$USE_SYSTEM_CA" = 1 ]; then
  NODE_OPTIONS="${{NODE_OPTIONS:+$NODE_OPTIONS }}--use-system-ca"
  export NODE_OPTIONS
fi

# ---- 4) 先验证这份凭据在该端点可用（免得装完才发现 401）
if [ "$NODE_BIN" != node ] || command -v node >/dev/null 2>&1; then
  OCTOP_URL="$HOOK_URL" OCTOP_TOKEN="$TOKEN" \\
  "$NODE_BIN" --input-type=module -e '
const cfg = {{ url: process.env.OCTOP_URL, token: process.env.OCTOP_TOKEN }};
const headers = {{ "Content-Type": "application/json", Accept: "application/json, text/event-stream",
  Authorization: `Bearer ${{cfg.token}}` }};
try {{
  const r = await fetch(cfg.url, {{ method: "POST", headers, signal: AbortSignal.timeout(8000), body: JSON.stringify({{ jsonrpc: "2.0", id: 1, method: "tools/list" }}) }});
  console.log(`  · 端点自检（hook 直连）：HTTP ${{r.status}}${{r.status === 200 ? "" : "（凭据或地址不对，请检查）"}}`);
}} catch (e) {{
  console.log(`  · 端点自检失败：${{e}}（安装仍继续，请自行确认地址）`);
}}
' 2>/dev/null || true
fi

# ---- 5) 各终端各自安装 hook 脚本 / 插件 + 合并其配置
OCTOP_URL="$URL" OCTOP_HOOK_URL="$HOOK_URL" OCTOP_TOKEN="$TOKEN" \\
OCTOP_SERVER_NAME='{_server_name(mcp_url)}' \\
OCTOP_CC_DIR="$CC_DIR" OCTOP_KIRO_DIR="$KIRO_DIR" OCTOP_DSH_DIR="$DSH_DIR" \\
OCTOP_CODEX_DIR="$CODEX_DIR" OCTOP_CURSOR_DIR="$CURSOR_DIR" \\
OCTOP_TERMINALS="$TERMINALS" \\
OCTOP_PROJECT_DIR="$PROJECT_DIR" \\
OCTOP_FILES_CLAUDE_CODE='{_host_manifest("claude-code")}' \\
OCTOP_FILES_KIRO='{_host_manifest("kiro")}' \\
OCTOP_FILES_CODEX='{_host_manifest("codex")}' \\
OCTOP_FILES_CURSOR='{_host_manifest("cursor")}' \\
OCTOP_FILES_NATIVE='{_dsh_native_manifest()}' \\
python3 - <<'OCTOP_PY'
{_MERGE_PY}
OCTOP_PY

echo "  · 重开终端/IDE（Kiro 重载 hooks；Codex 首次需在 codex 里信任该 hook；DSH 重启后加载插件）后生效"
"""


_UNINSTALL_PY = r'''
import json
import os
import pathlib
import shutil


_ENV_FILE = os.environ.get("OCTOP_ENV_FILE", "")
if _ENV_FILE:
    with open(_ENV_FILE, encoding="utf-8") as _env_handle:
        for _key, _value in json.load(_env_handle).items():
            os.environ.setdefault(str(_key), str(_value))


home = pathlib.Path(os.path.expanduser("~"))
CC_DIR = pathlib.Path(os.environ["OCTOP_CC_DIR"]).expanduser()
KIRO_DIR = pathlib.Path(os.environ["OCTOP_KIRO_DIR"]).expanduser()
DSH_DIR = pathlib.Path(os.environ["OCTOP_DSH_DIR"]).expanduser()
CODEX_DIR = pathlib.Path(os.environ["OCTOP_CODEX_DIR"]).expanduser()
CURSOR_DIR = pathlib.Path(os.environ["OCTOP_CURSOR_DIR"]).expanduser()

# ---- 安装范围：全局（默认）或只装到某个项目 ----
# 项目级卸载只清项目里的「注册」；用户目录里的 hook 脚本与 config.json 留给全局卸载。
PROJECT = (os.environ.get("OCTOP_PROJECT_DIR") or "").strip()
PROJECT_DIR = pathlib.Path(PROJECT).expanduser() if PROJECT else None
IN_PROJECT = PROJECT_DIR is not None
PROJECT = str(PROJECT_DIR) if IN_PROJECT else ""


def _project(*parts):
    """项目级产物路径（全局模式不会被调用）。"""
    return PROJECT_DIR.joinpath(*parts)


_OUR_SCRIPTS = (
    "user-prompt-recall.mjs",
    "stop-capture.mjs",
    # 包装脚本（配置里引用的是 .sh / Windows 的 .cmd）
    "user-prompt-recall.sh",
    "stop-capture.sh",
    "user-prompt-recall.cmd",
    "stop-capture.cmd",
    # 早期版本的文件名
    "octop-user-prompt-recall.mjs",
    "octop-stop-capture.mjs",
)
_OUR_MCP_TOOLS = ("memory_search", "memory_capture")


def _load(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  ! 读不了 {path}：{exc}")
        return None


def _dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _octop_servers(servers):
    return [name for name in servers if str(name).replace("_", "-").startswith("octop-memory")]


def _strings(value):
    """递归取出 JSON 结构里的所有字符串（判断「这条是不是我们写的」用）。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _mentions_dir(value, directory):
    """JSON / TOML 文本里是否引用了这个目录（统一成正斜杠再比，Windows 反斜杠也认）。"""
    needle = str(directory).replace("\\", "/")
    return any(needle in text.replace("\\", "/") for text in _strings(value))


def _handlers_of(entry):
    """一个 hook 条目里的处理项：嵌套 matcher 组或简写形态的单条（与安装器一致）。"""
    nested = (entry or {}).get("hooks")
    if isinstance(nested, list):
        return nested
    return [entry]


def _is_our_handler(handler):
    handler = handler or {}
    if handler.get("type") == "mcp_tool":
        return handler.get("tool") in _OUR_MCP_TOOLS
    command = handler.get("command") or ""
    return any(script in command for script in _OUR_SCRIPTS)


def _rm_tree(path, label):
    if not path.exists():
        print(f"  · {label} 不存在，跳过 → {path}")
        return
    shutil.rmtree(path)
    print(f"  ✓ 已删除 {label} → {path}")


def _strip_mcp(path):
    cfg = _load(path)
    if cfg is None:
        return
    servers = cfg.get("mcpServers") or {}
    ours = _octop_servers(servers)
    if not ours:
        print(f"  · {path} 无 octop-memory* MCP 条目")
        return
    for name in ours:
        servers.pop(name, None)
    cfg["mcpServers"] = servers
    _dump(path, cfg)
    print(f"  ✓ 已移除 MCP 服务 {', '.join(ours)} → {path}")


def _strip_claude_settings(settings):
    """清掉 settings 里我们写的 hook 条目（返回是否有改动）。"""
    st = _load(settings)
    if st is None:
        return False
    hooks = st.setdefault("hooks", {})
    changed = False
    for event in list(hooks):
        kept = [
            group
            for group in (hooks.get(event) or [])
            if not any(_is_our_handler(h) for h in _handlers_of(group))
        ]
        if len(kept) != len(hooks.get(event) or []):
            changed = True
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
            changed = True
    if changed:
        _dump(settings, st)
        print(f"  ✓ 已从 Claude Code settings 去掉 octop hooks → {settings}")
    else:
        print(f"  · Claude Code settings 无 octop hooks → {settings}")
    return changed


def _strip_mcp_local():
    """去掉 Claude Code local scope（``~/.claude.json`` 的 projects[<项目>]）里的 octop 条目。"""
    key = os.path.realpath(str(PROJECT_DIR))
    path = home / ".claude.json"
    cfg = _load(path)
    if not isinstance(cfg, dict):
        return
    projects = cfg.get("projects")
    if not isinstance(projects, dict):
        print(f"  · {path} 里没有按项目存的 MCP 条目")
        return
    bucket = projects.get(key)
    servers = bucket.get("mcpServers") if isinstance(bucket, dict) else None
    if not isinstance(servers, dict):
        print(f"  · {path} 的项目 {key} 无 octop-memory* MCP 条目")
        return
    ours = _octop_servers(servers)
    if not ours:
        print(f"  · {path} 的项目 {key} 无 octop-memory* MCP 条目")
        return
    for name in ours:
        servers.pop(name, None)
    if servers:
        bucket["mcpServers"] = servers
    else:
        bucket.pop("mcpServers", None)
    _dump(path, cfg)
    print(f"  ✓ 已移除 Claude Code local scope 的 MCP 服务 {', '.join(ours)}（项目 {key}）")


def undo_claude_code():
    if IN_PROJECT:
        _strip_claude_settings(_project(".claude", "settings.local.json"))
        _strip_mcp_local()
        print("  · 用户目录里的 hook 脚本保留（全局卸载才清）")
        return
    _strip_claude_settings(home / ".claude" / "settings.json")
    _strip_mcp(home / ".claude.json")
    _rm_tree(CC_DIR, "Claude Code hooks 目录")


def undo_kiro():
    hooks_dir = _project(".kiro", "hooks") if IN_PROJECT else KIRO_DIR
    for name in ("memory-recall-on-start.json", "memory-save-on-stop.json"):
        path = hooks_dir / name
        if path.exists():
            path.unlink()
            print(f"  ✓ 已删除 Kiro hook 文件 → {path}")
        else:
            print(f"  · Kiro hook 文件不存在 → {path}")
    if IN_PROJECT:
        _strip_mcp(_project(".kiro", "settings", "mcp.json"))
        print("  · 用户目录里的 hook 脚本保留（全局卸载才清）")
        return
    _strip_mcp(home / ".kiro" / "settings" / "mcp.json")
    _rm_tree(KIRO_DIR, "Kiro hooks 目录")


_DSH_NATIVE_NAME = "octop-memory-native"
_DSH_LEGACY_BUNDLES = ("dsh-memory-share", "octop-dsh-memory-share")


def _dsh_patch_entry(line):
    """这一行是不是顶层 ``- id: octop-memory-native``（缩进的 insert 行不算）。"""
    if not line.startswith("-"):
        return False
    rest = line[1:].strip()
    if not rest.startswith("id:"):
        return False
    value = rest[len("id:") :].strip()
    if " #" in value:
        value = value.split(" #", 1)[0]
    return value.strip().strip("'").strip('"') == _DSH_NATIVE_NAME


def _dsh_patch_bounds(lines):
    """配置块在 cordis.patch.yml 里的 ``[start, end)``（含块注释与 ``# <<< id <<<`` 结尾标记）。"""
    entry = None
    for index, line in enumerate(lines):
        if _dsh_patch_entry(line):
            entry = index
            break
    if entry is None:
        return None
    start = entry
    comments = []
    cursor = entry - 1
    while cursor >= 0:
        above = lines[cursor]
        if above.strip() == "" or above[:1] in (" ", "\t"):
            break
        if not above.lstrip().startswith("#"):
            break
        comments.insert(0, cursor)
        cursor -= 1
    if comments:
        joined = "".join(lines[index] for index in comments)
        if _DSH_NATIVE_NAME not in joined:
            while comments and _DSH_NATIVE_NAME not in lines[comments[0]]:
                comments.pop(0)
        if comments:
            start = comments[0]
    end = entry + 1
    while end < len(lines) and lines[end][:1] in (" ", "\t"):
        end += 1  # 条目本体：缩进的 config 行
    probe = end
    while probe < len(lines) and lines[probe].strip() == "":
        probe += 1
    if (
        probe < len(lines)
        and lines[probe].strip().startswith("#")
        and "<<<" in lines[probe]
        and _DSH_NATIVE_NAME in lines[probe]
    ):
        end = probe + 1  # 结尾标记（旧版在标记前留了空行，一起清掉）
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return start, end


def _strip_dsh_patch(profile_dir):
    """去掉该 profile 里我们写的配置块（别人的条目 / 注释逐字保留）。"""
    patch = profile_dir / "cordis.patch.yml"
    if not patch.exists():
        return
    lines = patch.read_text(encoding="utf-8").splitlines(keepends=True)
    bounds = _dsh_patch_bounds(lines)
    if bounds is None:
        print(f"  · {patch} 里没有 octop-memory-native 配置块")
        return
    start, end = bounds
    updated = "".join(lines[:start]) + "".join(lines[end:])
    if updated.strip():
        patch.write_text(updated.rstrip("\n") + "\n", encoding="utf-8")
        print(f"  ✓ 已从 {patch} 去掉 octop-memory-native 配置块（其余内容保留）")
    else:
        patch.unlink()
        print(f"  ✓ 已删除只含 octop-memory-native 配置块的 {patch}")


def _strip_dsh_profile(profile_dir):
    """去掉 profile 的插件登记：dependencies / node_modules 条目 / dsh.profile.bundles。"""
    changed = []
    package = profile_dir / "package.json"
    cfg = _load(package)
    if isinstance(cfg, dict):
        dependencies = cfg.get("dependencies")
        if isinstance(dependencies, dict) and _DSH_NATIVE_NAME in dependencies:
            dependencies.pop(_DSH_NATIVE_NAME)
            changed.append("dependencies")
        dsh = cfg.get("dsh")
        profile_cfg = dsh.get("profile") if isinstance(dsh, dict) else None
        bundles = profile_cfg.get("bundles") if isinstance(profile_cfg, dict) else None
        if isinstance(bundles, list):
            gone = [
                name for name in (_DSH_NATIVE_NAME,) + _DSH_LEGACY_BUNDLES if name in bundles
            ]
            if gone:
                profile_cfg["bundles"] = [
                    name
                    for name in bundles
                    if name not in (_DSH_NATIVE_NAME,) + _DSH_LEGACY_BUNDLES
                ]
                changed.append("dsh.profile.bundles（" + "、".join(gone) + "）")
        if changed:
            _dump(package, cfg)
    module = profile_dir / "node_modules" / _DSH_NATIVE_NAME
    if module.is_symlink():
        module.unlink()
        changed.append("node_modules 链接")
    elif module.exists():
        shutil.rmtree(module)
        changed.append("node_modules 目录")
    return changed


def undo_dsh():
    if IN_PROJECT:
        print("  · DSH 没有项目级配置：项目级卸载不需要清它")
        return
    plugin = home / ".dsh" / "bundles" / _DSH_NATIVE_NAME
    if plugin.exists():
        shutil.rmtree(plugin)
        print(f"  ✓ 已删除 DSH 原生插件 → {plugin}")
    profiles = home / ".dsh" / "profiles"
    if profiles.is_dir():
        for profile in sorted(profiles.iterdir()):
            if not (profile / "package.json").exists():
                continue
            changed = _strip_dsh_profile(profile)
            if changed:
                print(f"  ✓ 已从 DSH profile「{profile.name}」去掉 " + "、".join(changed))
            _strip_dsh_patch(profile)
    # hooks 回退模式（以及 native 之前的版本）留下的东西
    bridge = DSH_DIR / "octop-hooks.json"
    if bridge.exists():
        bridge.unlink()
        print(f"  ✓ 已删除 DSH 桥接 → {bridge}")
    bundle = DSH_DIR.parent / "bundles" / "dsh-memory-share"
    if bundle.exists():
        shutil.rmtree(bundle)
        print(f"  ✓ 已删除 DSH preset bundle → {bundle}")
    _rm_tree(DSH_DIR, "DSH hooks 目录")


def _toml_blocks(text):
    blocks = [[]]
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("[") and not line.lstrip().startswith("#"):
            blocks.append([])
        blocks[-1].append(line)
    return blocks


def undo_codex():
    path = _project(".codex", "config.toml") if IN_PROJECT else home / ".codex" / "config.toml"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        blocks, kept = _toml_blocks(text), []
        removed = 0
        for block in blocks:
            body = "".join(block)
            header = block[0].strip() if block else ""
            ours = _mentions_dir(body, CODEX_DIR)
            if ours and header.startswith("[[hooks.") and header.endswith(".hooks]]"):
                event = header[len("[[hooks.") : -len(".hooks]]")]
                if kept and kept[-1][0].strip() == f"[[hooks.{event}]]" and not "".join(kept[-1][1:]).strip():
                    kept.pop()
                removed += 1
                continue
            kept.append(block)
        if removed:
            path.write_text("".join("".join(block) for block in kept), encoding="utf-8")
            print(f"  ✓ 已从 Codex config.toml 去掉 octop hooks → {path}")
        else:
            print(f"  · Codex config.toml 无 octop hooks → {path}")
    else:
        print(f"  · Codex config.toml 不存在 → {path}")
    if IN_PROJECT:
        print("  · 用户目录里的 hook 脚本保留（全局卸载才清）")
        return
    _rm_tree(CODEX_DIR, "Codex hooks 目录")


def undo_cursor():
    path = _project(".cursor", "hooks.json") if IN_PROJECT else home / ".cursor" / "hooks.json"
    cfg = _load(path)
    if cfg is not None:
        hooks = cfg.setdefault("hooks", {})
        marker = str(CURSOR_DIR)
        changed = False
        for event in list(hooks):
            entries = hooks.get(event) or []
            kept = [entry for entry in entries if not _mentions_dir(entry, marker)]
            if len(kept) != len(entries):
                changed = True
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
                changed = True
        if changed:
            cfg["hooks"] = hooks
            _dump(path, cfg)
            print(f"  ✓ 已从 Cursor hooks.json 去掉 octop hooks → {path}")
        else:
            print(f"  · Cursor hooks.json 无 octop hooks → {path}")
    else:
        print(f"  · Cursor hooks.json 不存在 → {path}")
    if IN_PROJECT:
        print("  · 用户目录里的 hook 脚本保留（全局卸载才清）")
        return
    # setup 不为 Cursor 写 MCP，但检索常靠 ~/.cursor/mcp.json 里的 octop-memory*
    _strip_mcp(home / ".cursor" / "mcp.json")
    _rm_tree(CURSOR_DIR, "Cursor hooks 目录")


for terminal in os.environ["OCTOP_TERMINALS"].split(","):
    terminal = terminal.strip()
    if not terminal:
        continue
    print(f"· {terminal}")
    {
        "claude-code": undo_claude_code,
        "kiro": undo_kiro,
        "dsh": undo_dsh,
        "codex": undo_codex,
        "cursor": undo_cursor,
    }[terminal]()

print("  · octop memory 卸载完成（可重复执行；服务端已有记忆不会删除）")
print("  · 请重开终端/IDE 后生效")
'''.strip()


def render_uninstall_script(*, terminals: str = "", project: str = "") -> str:
    """Render the interactive uninstaller (counterpart of ``render_setup_script``).

    No token / agent prompts — only chooses which terminals to scrub (and whether to scrub
    the global install or one project's registrations). Safe to re-run; leaves non-octop
    hooks and MCP servers alone.

    ``project`` is the **prefill** for a project-scoped uninstall (the interactive default);
    non-interactive runs read ``OCTOP_PROJECT_DIR`` (an explicitly empty value = global).
    """
    terminals_literal = _sh_single_quote(terminals) if terminals else "''"
    project_literal = _sh_single_quote(project) if project else "''"
    return f"""#!/bin/sh
# octop memory — 卸载本地终端接入（与 /mcp/memory/setup 相对；可重复执行）
set -eu

DEFAULT_TERMINALS={terminals_literal}
DEFAULT_PROJECT={project_literal}
CC_DIR='{HOOKS_DIRS["claude-code"]}'
KIRO_DIR='{HOOKS_DIRS["kiro"]}'
DSH_DIR='{HOOKS_DIRS["dsh"]}'
CODEX_DIR='{HOOKS_DIRS["codex"]}'
CURSOR_DIR='{HOOKS_DIRS["cursor"]}'

have_claude=0; have_kiro=0; have_dsh=0; have_codex=0; have_cursor=0
{{ [ -e "$HOME/.claude.json" ] || [ -d "$HOME/.claude" ] || command -v claude >/dev/null 2>&1; }} && have_claude=1
{{ [ -d "$HOME/.kiro" ] || command -v kiro >/dev/null 2>&1; }} && have_kiro=1
{{ [ -d "$HOME/.dsh" ] || command -v dsh >/dev/null 2>&1; }} && have_dsh=1
{{ [ -d "$HOME/.codex" ] || command -v codex >/dev/null 2>&1; }} && have_codex=1
{{ [ -d "$HOME/.cursor" ] || command -v cursor >/dev/null 2>&1; }} && have_cursor=1

DETECTED=''
[ "$have_claude" = 1 ] && DETECTED="$DETECTED claude-code"
[ "$have_kiro" = 1 ] && DETECTED="$DETECTED kiro"
[ "$have_dsh" = 1 ] && DETECTED="$DETECTED dsh"
[ "$have_codex" = 1 ] && DETECTED="$DETECTED codex"
[ "$have_cursor" = 1 ] && DETECTED="$DETECTED cursor"
[ -n "$DETECTED" ] || DETECTED='cursor'

echo "octop memory 卸载"
echo "检测到："
[ "$have_claude" = 1 ] && echo "  1) Claude Code　（清 ~/.claude/hooks-events + settings/MCP）"
[ "$have_kiro" = 1 ] && echo "  2) Kiro　　　　（清 ~/.kiro/hooks + MCP）"
[ "$have_dsh" = 1 ] && echo "  3) DSH　　　　（清原生插件 + profile 登记 + ~/.dsh/hooks 桥接/preset）"
[ "$have_codex" = 1 ] && echo "  4) Codex　　　（清 ~/.codex/hooks + config.toml 中的 octop hooks）"
[ "$have_cursor" = 1 ] && echo "  5) Cursor　　　（清 ~/.cursor/hooks + hooks.json；顺带去掉 mcp.json 里的 octop-memory*）"

HAS_TTY=0
if (true </dev/tty) 2>/dev/null; then HAS_TTY=1; fi

TERMINALS="${{OCTOP_TERMINALS:-$DEFAULT_TERMINALS}}"
if [ -z "$TERMINALS" ] && [ "$HAS_TTY" = 1 ]; then
  _picked=''
  if command -v python3 >/dev/null 2>&1; then
    set --
    [ "$have_claude" = 1 ] && set -- "$@" "claude-code|Claude Code"
    [ "$have_kiro" = 1 ] && set -- "$@" "kiro|Kiro"
    [ "$have_dsh" = 1 ] && set -- "$@" "dsh|DSH"
    [ "$have_codex" = 1 ] && set -- "$@" "codex|Codex"
    [ "$have_cursor" = 1 ] && set -- "$@" "cursor|Cursor"
    _picked="$(python3 - "$@" 2>/dev/null <<'OCTOP_SELECT'
{_SELECT_PY}
OCTOP_SELECT
)" || _picked=''
  fi
  if [ -n "$_picked" ]; then
    TERMINALS="$_picked"
  else
    _attempt=0
    while [ -z "$TERMINALS" ] && [ "$_attempt" -lt 3 ]; do
      _attempt=$((_attempt + 1))
      printf '要卸载哪些？(可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的): ' > /dev/tty
      read -r _pick < /dev/tty || _pick=''
      _chosen=''
      case "$_pick" in
        ''|a|A|all|ALL|全部) _chosen="$DETECTED" ;;
        *)
          for _n in $(printf '%s' "$_pick" | tr ',' ' '); do
            case "$_n" in
              [0-9][0-9]*) _items="$(printf '%s' "$_n" | fold -w1 | tr '\\n' ' ')" ;;
              *) _items="$_n" ;;
            esac
            for _i in $_items; do
              case "$_i" in
                1) _add="$([ "$have_claude" = 1 ] && echo claude-code)" ;;
                2) _add="$([ "$have_kiro" = 1 ] && echo kiro)" ;;
                3) _add="$([ "$have_dsh" = 1 ] && echo dsh)" ;;
                4) _add="$([ "$have_codex" = 1 ] && echo codex)" ;;
                5) _add="$([ "$have_cursor" = 1 ] && echo cursor)" ;;
                *) _add='' ;;
              esac
              if [ -z "$_add" ]; then
                echo "  ? 已忽略：${{_i}}" >&2
              else
                case ",$_chosen," in *",$_add,"*) ;; *) _chosen="$_chosen,$_add" ;; esac
              fi
            done
          done
          ;;
      esac
      TERMINALS="$(printf '%s' "$_chosen" | sed 's/^,//')"
      [ -n "$TERMINALS" ] || echo "  ! 没有选中任何终端，请重选" >&2
    done
  fi
fi

[ -n "$TERMINALS" ] || {{ echo "没有可卸载的终端：非交互请设 OCTOP_TERMINALS=cursor" >&2; exit 1; }}

# ---- 卸载范围：全局（默认）还是只清某个项目里的注册
# ?project= 预填只在**交互式**生效（变成默认答案）；非交互只认 OCTOP_PROJECT_DIR。
if [ "${{OCTOP_PROJECT_DIR+x}}" = x ]; then
  PROJECT_DIR="$OCTOP_PROJECT_DIR"
else
  PROJECT_DIR=''
fi
if [ -z "$PROJECT_DIR" ] && [ "$HAS_TTY" = 1 ]; then
  echo "卸载范围："
  echo "  1) 全局（默认）"
  echo "  2) 只清某个项目里的注册（用户目录里的脚本保留）"
  _default_scope=1
  if [ -n "$DEFAULT_PROJECT" ]; then _default_scope=2; fi
  printf '选择 [1/2]（默认 %s）: ' "$_default_scope" > /dev/tty
  read -r _scope < /dev/tty || _scope=''
  if [ -z "$_scope" ]; then _scope="$_default_scope"; fi
  case "$_scope" in
    2|p|P|project|项目)
      if [ -n "$DEFAULT_PROJECT" ]; then
        printf '项目根目录 [%s]: ' "$DEFAULT_PROJECT" > /dev/tty
        read -r PROJECT_DIR < /dev/tty || PROJECT_DIR=''
        if [ -z "$PROJECT_DIR" ]; then PROJECT_DIR="$DEFAULT_PROJECT"; fi
      else
        printf '项目根目录: ' > /dev/tty
        read -r PROJECT_DIR < /dev/tty || PROJECT_DIR=''
      fi
      if [ -z "$PROJECT_DIR" ]; then
        echo "  ! 项目根目录不能为空" >&2
        exit 1
      fi
      ;;
  esac
fi
if [ -n "$PROJECT_DIR" ]; then
  case "$PROJECT_DIR" in
    "~") PROJECT_DIR="$HOME" ;;
    "~/"*) PROJECT_DIR="$HOME/${{PROJECT_DIR#\\~/}}" ;;
  esac
  if [ ! -d "$PROJECT_DIR" ]; then
    echo "  ! 项目目录不存在（或不是目录）：$PROJECT_DIR" >&2
    exit 1
  fi
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
  if [ ! -w "$PROJECT_DIR" ]; then
    echo "  ! 项目目录不可写：$PROJECT_DIR" >&2
    exit 1
  fi
  echo "  · 卸载范围：项目级 → ${{PROJECT_DIR}}（用户目录里的 hook 脚本保留）"
fi
export OCTOP_PROJECT_DIR="$PROJECT_DIR"

command -v python3 >/dev/null 2>&1 || {{ echo "  ! 未找到 python3" >&2; exit 1; }}

OCTOP_CC_DIR="$CC_DIR" OCTOP_KIRO_DIR="$KIRO_DIR" OCTOP_DSH_DIR="$DSH_DIR" \\
OCTOP_CODEX_DIR="$CODEX_DIR" OCTOP_CURSOR_DIR="$CURSOR_DIR" \\
OCTOP_TERMINALS="$TERMINALS" \\
OCTOP_PROJECT_DIR="$PROJECT_DIR" \\
python3 - <<'OCTOP_PY'
{_UNINSTALL_PY}
OCTOP_PY
"""


_PS_SELF_CHECK_JS = r"""
const cfg = { url: process.env.OCTOP_CHECK_URL, token: process.env.OCTOP_CHECK_TOKEN };
const headers = { "Content-Type": "application/json", Accept: "application/json, text/event-stream",
  Authorization: `Bearer ${cfg.token}` };
try {
  const r = await fetch(cfg.url, { method: "POST", headers, signal: AbortSignal.timeout(8000), body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }) });
  console.log(`  · 端点自检（hook 直连）：HTTP ${r.status}${r.status === 200 ? "" : "（凭据或地址不对，请检查）"}`);
} catch (e) {
  console.log(`  · 端点自检失败：${e}（安装仍继续，请自行确认地址）`);
}
""".strip()
"""Windows 安装器的端点自检脚本（与 sh 安装器同一段，环境变量名不同以免和合并逻辑抢）。"""


_SETUP_PS_TEMPLATE = r"""# octop memory — Windows 终端接入（hooks 发往 __HOOK_URL_TEXT__；可重复执行）
#   用法（PowerShell）：irm "<octop>/mcp/memory/setup?os=windows" | iex
#   非交互（CI/批量）：先设 $env:OCTOP_MEMORY_TOKEN / $env:OCTOP_TERMINALS
#
# 与 POSIX 安装器共用同一套终端宿主和同一份「合并配置」python 程序；差别只在两处：
#   * 交互走 PowerShell 的 Read-Host（Windows 没有 POSIX 的终端控制这套做法）；
#   * hook 包装脚本是 .cmd（OCTOP_HOOK_WRAPPER=cmd），由系统 shell 直接执行 —— 不需要 Git Bash。
if ($PSVersionTable.PSVersion.Major -lt 5) { throw '需要 PowerShell 5.1 或更高版本' }
& {
  $ErrorActionPreference = 'Stop'

  $URL = __URL_LITERAL__
  $HOOK_URL = __HOOK_URL_LITERAL__
  $DEFAULT_TOKEN = __DEFAULT_TOKEN_LITERAL__
  $DEFAULT_TERMINALS = __DEFAULT_TERMINALS_LITERAL__
  $DEFAULT_PROJECT = __DEFAULT_PROJECT_LITERAL__

  $CC_DIR = Join-Path $HOME '__CC_DIR_REL__'
  $KIRO_DIR = Join-Path $HOME '__KIRO_DIR_REL__'
  $DSH_DIR = Join-Path $HOME '__DSH_DIR_REL__'
  $CODEX_DIR = Join-Path $HOME '__CODEX_DIR_REL__'
  $CURSOR_DIR = Join-Path $HOME '__CURSOR_DIR_REL__'

  $interactive = $true
  try { $interactive = -not [Console]::IsInputRedirected } catch { $interactive = $true }

  function Test-Terminal([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
  }

  function Read-Secret([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  }

  # ---- 1) 检测本机装了哪些终端（配置目录或命令任一命中）
  $haveClaude = (Test-Path (Join-Path $HOME '.claude.json')) -or (Test-Path (Join-Path $HOME '.claude')) -or (Test-Terminal 'claude')
  $haveKiro = (Test-Path (Join-Path $HOME '.kiro')) -or (Test-Terminal 'kiro')
  $haveDsh = (Test-Path (Join-Path $HOME '.dsh')) -or (Test-Terminal 'dsh')
  $haveCodex = (Test-Path (Join-Path $HOME '.codex')) -or (Test-Terminal 'codex')
  $haveCursor = (Test-Path (Join-Path $HOME '.cursor')) -or (Test-Terminal 'cursor')

  # 固定槽位与 POSIX 安装器一致：1 Claude Code 2 Kiro 3 DSH 4 Codex 5 Cursor
  $slotName = @{ 1 = 'claude-code'; 2 = 'kiro'; 3 = 'dsh'; 4 = 'codex'; 5 = 'cursor' }
  $slotDetected = @{ 1 = $haveClaude; 2 = $haveKiro; 3 = $haveDsh; 4 = $haveCodex; 5 = $haveCursor }
  $slotHint = @{
    1 = 'Claude Code　（hook 装到 ~/.claude/hooks-events）'
    2 = 'Kiro　（hook 装到 ~/.kiro/hooks）'
    3 = 'DSH　（装原生插件 octop-memory-native，进程内召回/上报）'
    4 = 'Codex　（hook 装到 ~/.codex/hooks，配置写 ~/.codex/config.toml）'
    5 = 'Cursor　（hook 装到 ~/.cursor/hooks，配置写 ~/.cursor/hooks.json）'
  }
  $detected = @()
  foreach ($key in 1, 2, 3, 4, 5) { if ($slotDetected[$key]) { $detected += $slotName[$key] } }
  if ($detected.Count -eq 0) { $detected = @('claude-code') }

  Write-Host "octop memory 接入 → $URL"
  Write-Host '检测到：'
  foreach ($key in 1, 2, 3, 4, 5) {
    if ($slotDetected[$key]) { Write-Host ("  {0}) {1}" -f $key, $slotHint[$key]) }
  }

  # ---- 2) 选终端（1,2 / 1 3 / 12 / a=全部；回车=全部检测到的；选不中会重问）
  $terminals = $env:OCTOP_TERMINALS
  if (-not $terminals) { $terminals = $DEFAULT_TERMINALS }
  if (-not $terminals -and $interactive) {
    $attempt = 0
    while (-not $terminals -and $attempt -lt 3) {
      $attempt++
      $pick = Read-Host '要配置哪些？(可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的)'
      $chosen = @()
      if (-not $pick -or $pick -match '^(?i)(a|all|全部)$') {
        $chosen = @($detected)
      }
      else {
        $tokens = @()
        foreach ($token in ($pick -replace '[,\s]+', ' ').Split(' ')) {
          if (-not $token) { continue }
          if ($token -match '^[0-9]{2,}$') {
            foreach ($char in $token.ToCharArray()) { $tokens += [string]$char }
          }
          else { $tokens += $token }
        }
        foreach ($token in $tokens) {
          $index = 0
          if (-not [int]::TryParse($token, [ref]$index) -or -not $slotDetected[$index]) {
            Write-Host "  ? 已忽略：$token（未检测到或无法识别）"
            continue
          }
          $name = $slotName[$index]
          if ($chosen -notcontains $name) { $chosen += $name }
        }
      }
      if ($chosen.Count -gt 0) { $terminals = ($chosen -join ',') }
      else { Write-Host '  ! 没有选中任何已检测到的终端，请重选（1-5，或 a=全部）' -ForegroundColor Yellow }
    }
  }
  if (-not $terminals) { throw '没有可配置的终端（非交互请先设 $env:OCTOP_TERMINALS）' }

  # ---- 2.5) 安装范围：全局（默认）还是只装到某个项目
  # 项目级只在项目里写「注册」（hooks 命令 / MCP 条目）；hook 脚本与 config.json（含 token）
  # 始终留在本机用户目录。Kiro 的 MCP 条目自带凭据、DSH 没有项目级配置，这两个在项目模式
  # 会被跳过（见合并脚本里的提示）。
  # ?project= 预填只在**交互式**生效（变成默认答案）；非交互只认 OCTOP_PROJECT_DIR。
  # 显式设置（哪怕是空串）就以环境变量为准：空串 = 强制全局，不再交互提问。
  $projectSet = $null -ne $env:OCTOP_PROJECT_DIR
  $projectDir = ''
  if ($projectSet) { $projectDir = $env:OCTOP_PROJECT_DIR }
  if (-not $projectSet -and $interactive) {
    Write-Host '安装范围：'
    Write-Host '  1) 全局（所有项目生效，默认）'
    Write-Host '  2) 只装到某个项目（项目里只写注册；脚本和凭据留在本机）'
    $defaultScope = '1'
    if ($DEFAULT_PROJECT) { $defaultScope = '2' }
    $scope = Read-Host "选择 [1/2]（回车=$defaultScope）"
    if (-not $scope) { $scope = $defaultScope }
    if ($scope -in @('2', 'p', 'P', 'project', '项目')) {
      $defaultProject = $DEFAULT_PROJECT
      if (-not $defaultProject) { $defaultProject = (Get-Location).Path }
      $projectDir = Read-Host "项目根目录 [$defaultProject]"
      if (-not $projectDir) { $projectDir = $defaultProject }
    }
  }
  if ($projectDir) {
    if ($projectDir -eq '~' -or $projectDir -eq '~/' -or $projectDir -eq '~\') { $projectDir = $HOME }
    elseif ($projectDir -match '^~[\\/]') { $projectDir = Join-Path $HOME $projectDir.Substring(2) }
    if (-not (Test-Path -LiteralPath $projectDir -PathType Container)) { throw "项目目录不存在（或不是目录）：$projectDir" }
    $projectDir = (Resolve-Path -LiteralPath $projectDir).Path
    $probe = Join-Path $projectDir ('.octop-write-probe-' + [guid]::NewGuid().ToString('N'))
    try {
      [System.IO.File]::WriteAllText($probe, '')
      Remove-Item -LiteralPath $probe -Force
    }
    catch { throw "项目目录不可写：$projectDir" }
    Write-Host "  · 安装范围：项目级 → $projectDir"
    Write-Host '      · 项目里只写注册（hooks 命令 / MCP 条目）；hook 脚本与 token 留在本机用户目录'
    Write-Host '      · 不入仓库：Claude Code 走 ~\.claude.json 的 local scope 与 .claude\settings.local.json'
    Write-Host '      · Codex / Cursor 的项目文件里只有命令（不含凭据）'
    Write-Host '      · 跳过：Kiro 的 .kiro\settings\mcp.json（含凭据）、DSH（没有项目级配置）'
    if (-not (Test-Path -LiteralPath (Join-Path $projectDir '.git'))) {
      Write-Host '      · 提示：不是 git 仓库根目录（项目级配置仍可用，只是不会进版本库）'
    }
  }

  # ---- 3) 凭据：用户级 MCP token（omcp_…），条目与 hooks 共用同一份
  $localNote = ''
  $isLocal = @('127.0.0.1', 'localhost') -contains ([Uri]$HOOK_URL).Host
  if ($isLocal) { $localNote = '（本机实例）' }
  $token = $env:OCTOP_MEMORY_TOKEN
  if (-not $token -and $DEFAULT_TOKEN) {
    $token = $DEFAULT_TOKEN
    Write-Host '  · token：用安装链接预填的值（个人 MCP token）'
  }
  if (-not $token -and $interactive) {
    $token = Read-Secret 'MCP token（omcp_…，在 Octop 的 /api/memory-mcp/tokens 创建；不回显）: '
  }
  if (-not $token) { throw '缺少 MCP token：非交互运行时请先设 $env:OCTOP_MEMORY_TOKEN=<omcp_…>' }
  Write-Host "  · hook 直连：$HOOK_URL$localNote"
  Write-Host "  · 客户端 MCP 条目：$URL（只用 Authorization: Bearer <MCP token>）"

  # ---- 4) 解析 node 绝对路径（hook 由终端派生，非 login shell 里没有 PATH 上的 node）
  $nodeBin = $env:OCTOP_NODE
  if (-not $nodeBin) {
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCmd) { $nodeBin = $nodeCmd.Source }
  }
  if (-not $nodeBin) {
    $candidates = @()
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'nodejs\node.exe') }
    if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe') }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe') }
    foreach ($cand in $candidates) {
      if (-not $nodeBin -and (Test-Path $cand)) { $nodeBin = $cand }
    }
  }
  if (-not $nodeBin) {
    $nodeBin = 'node'
    Write-Host '  ! 未找到 node：hook 需要它，请先安装 Node.js' -ForegroundColor Yellow
  }
  else { Write-Host "  · node: $nodeBin" }

  # 合并配置要用 python3；Windows 上常见的命令是 py -3 / python
  $python = $null
  foreach ($spec in @('py -3', 'python', 'python3')) {
    $parts = $spec.Split(' ')
    $exe = Get-Command $parts[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $pre = @()
    if ($parts.Count -gt 1) { $pre = $parts[1..($parts.Count - 1)] }
    & $exe.Source @pre -c 'import sys; raise SystemExit(0)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = @($exe.Source) + $pre; break }
  }
  if (-not $python) { throw '未找到 python3：无法合并终端配置（安装 Python 3 时请勾选 Add python.exe to PATH）' }

  # Node 22.15+ 的 --use-system-ca 读系统证书库：hook 的 fetch 走企业根证书时需要它
  $useSystemCa = 0
  $nodeOk = $false
  if ($nodeBin) { $nodeOk = (Test-Path $nodeBin) -or [bool](Get-Command $nodeBin -ErrorAction SilentlyContinue) }
  if ($nodeOk) {
    try {
      & $nodeBin --use-system-ca -e 'process.exit(0)' 2>$null
      if ($LASTEXITCODE -eq 0) {
        $useSystemCa = 1
        Write-Host '  · node 使用系统证书库（--use-system-ca）'
      }
      else {
        Write-Host '  ! 当前 node 不支持 --use-system-ca（需要 22.15+）：企业根证书下 hook 的 fetch 可能失败' -ForegroundColor Yellow
      }
    }
    catch { Write-Host '  ! node 无法执行：跳过端点自检，hook 可能跑不起来' -ForegroundColor Yellow }
  }

  # ---- 5) 端点自检（warn-only）：先确认这份 token 在该端点可用，免得装完才发现 401
  if ($nodeOk) {
    $env:OCTOP_CHECK_URL = $HOOK_URL
    $env:OCTOP_CHECK_TOKEN = $token
    $check = @'
__SELF_CHECK_JS__
'@
    try { & $nodeBin --input-type=module -e $check } catch { }
  }

  # ---- 6) 各终端安装 hook / 插件 + 合并配置（调用与 sh 安装器同一份 python 程序）
  $payload = @{
    OCTOP_URL = $URL
    OCTOP_HOOK_URL = $HOOK_URL
    OCTOP_TOKEN = $token
    OCTOP_SERVER_NAME = __SERVER_NAME_LITERAL__
    OCTOP_CC_DIR = $CC_DIR
    OCTOP_KIRO_DIR = $KIRO_DIR
    OCTOP_DSH_DIR = $DSH_DIR
    OCTOP_CODEX_DIR = $CODEX_DIR
    OCTOP_CURSOR_DIR = $CURSOR_DIR
    OCTOP_TERMINALS = $terminals
    OCTOP_PROJECT_DIR = [string]$projectDir
    OCTOP_FILES_CLAUDE_CODE = __FILES_CLAUDE_CODE_LITERAL__
    OCTOP_FILES_KIRO = __FILES_KIRO_LITERAL__
    OCTOP_FILES_CODEX = __FILES_CODEX_LITERAL__
    OCTOP_FILES_CURSOR = __FILES_CURSOR_LITERAL__
    OCTOP_FILES_NATIVE = __FILES_NATIVE_LITERAL__
    OCTOP_NODE = $nodeBin
    OCTOP_USE_SYSTEM_CA = [string]$useSystemCa
    OCTOP_HOOK_WRAPPER = 'cmd'
  }
  $envFile = [System.IO.Path]::GetTempFileName()
  $mergeFile = [System.IO.Path]::GetTempFileName()
  try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($envFile, ($payload | ConvertTo-Json -Compress), $utf8)
    $merge = @'
__MERGE_PY__
'@
    [System.IO.File]::WriteAllText($mergeFile, $merge, $utf8)
    $env:OCTOP_ENV_FILE = $envFile
    $pyArgs = @()
    if ($python.Count -gt 1) { $pyArgs = $python[1..($python.Count - 1)] }
    $pythonExe = $python[0]
    & $pythonExe @pyArgs $mergeFile
    if ($LASTEXITCODE -ne 0) { throw "配置合并失败（python 退出码 $LASTEXITCODE）" }
  }
  finally {
    Remove-Item -LiteralPath $envFile -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $mergeFile -ErrorAction SilentlyContinue
  }
  # 别把安装器的临时环境变量留在当前 PowerShell 会话里
  Remove-Item Env:OCTOP_ENV_FILE -ErrorAction SilentlyContinue
  Remove-Item Env:OCTOP_CHECK_URL, Env:OCTOP_CHECK_TOKEN -ErrorAction SilentlyContinue

  Write-Host '  · 重开终端/IDE（Kiro 重载 hooks；Codex 首次需在 codex 里信任该 hook；DSH 重启后加载插件）后生效'
}
"""


def render_setup_ps1(
    *,
    mcp_url: str,
    hook_url: str = "",
    agent_id: str = "",
    terminals: str = "",
    default_token: str = "",
    project: str = "",
) -> str:
    """Render the Windows (PowerShell) installer — counterpart of ``render_setup_script``.

    Entry point is ``irm "<octop>/mcp/memory/setup?os=windows" | iex``. The terminals,
    hook roles and the "merge config" python program are the same as the POSIX installer;
    what Windows adds is:

    * interaction through ``Read-Host`` (no ``/dev/tty`` / ``stty``);
    * ``.cmd`` hook wrappers (``OCTOP_HOOK_WRAPPER=cmd``) executed by the system shell, so
      Git Bash is not required;
    * config + manifests passed through a temp JSON (``OCTOP_ENV_FILE``) — the Windows
      environment block has a hard length limit.

    ``default_token`` / ``project`` keep the same "optional prefill" meaning as in
    ``render_setup_script``; non-interactive runs read ``OCTOP_PROJECT_DIR``.

    ``agent_id`` is accepted for backwards compatibility and **ignored** — the MCP token is
    bound to one expert, so the installer writes no expert id and no ``X-Octop-Agent-Id``.
    """
    hook_url = hook_url or mcp_url
    replacements = {
        "__URL_LITERAL__": _ps_single_quote(mcp_url),
        "__HOOK_URL_LITERAL__": _ps_single_quote(hook_url),
        "__HOOK_URL_TEXT__": hook_url,
        "__DEFAULT_TOKEN_LITERAL__": _ps_single_quote(default_token) if default_token else "''",
        "__DEFAULT_PROJECT_LITERAL__": _ps_single_quote(project) if project else "''",
        "__DEFAULT_TERMINALS_LITERAL__": _ps_single_quote(terminals) if terminals else "''",
        "__CC_DIR_REL__": _ps_home_rel(HOOKS_DIRS["claude-code"]),
        "__KIRO_DIR_REL__": _ps_home_rel(HOOKS_DIRS["kiro"]),
        "__DSH_DIR_REL__": _ps_home_rel(HOOKS_DIRS["dsh"]),
        "__CODEX_DIR_REL__": _ps_home_rel(HOOKS_DIRS["codex"]),
        "__CURSOR_DIR_REL__": _ps_home_rel(HOOKS_DIRS["cursor"]),
        "__SERVER_NAME_LITERAL__": _ps_single_quote(_server_name(mcp_url)),
        "__FILES_CLAUDE_CODE_LITERAL__": _ps_single_quote(_host_manifest("claude-code")),
        "__FILES_KIRO_LITERAL__": _ps_single_quote(_host_manifest("kiro")),
        "__FILES_CODEX_LITERAL__": _ps_single_quote(_host_manifest("codex")),
        "__FILES_CURSOR_LITERAL__": _ps_single_quote(_host_manifest("cursor")),
        "__FILES_NATIVE_LITERAL__": _ps_single_quote(_dsh_native_manifest()),
        "__SELF_CHECK_JS__": _PS_SELF_CHECK_JS,
        "__MERGE_PY__": _MERGE_PY,
    }
    script = _SETUP_PS_TEMPLATE
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    return script


_UNINSTALL_PS_TEMPLATE = r"""# octop memory — Windows 卸载本地终端接入（与 /mcp/memory/setup 相对；可重复执行）
#   用法（PowerShell）：irm "<octop>/mcp/memory/uninstall?os=windows" | iex
#   非交互：先设 $env:OCTOP_TERMINALS=cursor
if ($PSVersionTable.PSVersion.Major -lt 5) { throw '需要 PowerShell 5.1 或更高版本' }
& {
  $ErrorActionPreference = 'Stop'

  $DEFAULT_TERMINALS = __DEFAULT_TERMINALS_LITERAL__
  $DEFAULT_PROJECT = __DEFAULT_PROJECT_LITERAL__
  $CC_DIR = Join-Path $HOME '__CC_DIR_REL__'
  $KIRO_DIR = Join-Path $HOME '__KIRO_DIR_REL__'
  $DSH_DIR = Join-Path $HOME '__DSH_DIR_REL__'
  $CODEX_DIR = Join-Path $HOME '__CODEX_DIR_REL__'
  $CURSOR_DIR = Join-Path $HOME '__CURSOR_DIR_REL__'

  $interactive = $true
  try { $interactive = -not [Console]::IsInputRedirected } catch { $interactive = $true }

  function Test-Terminal([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
  }

  $haveClaude = (Test-Path (Join-Path $HOME '.claude.json')) -or (Test-Path (Join-Path $HOME '.claude')) -or (Test-Terminal 'claude')
  $haveKiro = (Test-Path (Join-Path $HOME '.kiro')) -or (Test-Terminal 'kiro')
  $haveDsh = (Test-Path (Join-Path $HOME '.dsh')) -or (Test-Terminal 'dsh')
  $haveCodex = (Test-Path (Join-Path $HOME '.codex')) -or (Test-Terminal 'codex')
  $haveCursor = (Test-Path (Join-Path $HOME '.cursor')) -or (Test-Terminal 'cursor')

  $slotName = @{ 1 = 'claude-code'; 2 = 'kiro'; 3 = 'dsh'; 4 = 'codex'; 5 = 'cursor' }
  $slotDetected = @{ 1 = $haveClaude; 2 = $haveKiro; 3 = $haveDsh; 4 = $haveCodex; 5 = $haveCursor }
  $slotHint = @{
    1 = 'Claude Code　（清 ~/.claude/hooks-events + settings/MCP）'
    2 = 'Kiro　（清 ~/.kiro/hooks + MCP）'
    3 = 'DSH　（清原生插件 + profile 登记 + ~/.dsh/hooks 桥接/preset）'
    4 = 'Codex　（清 ~/.codex/hooks + config.toml 中的 octop hooks）'
    5 = 'Cursor　（清 ~/.cursor/hooks + hooks.json）'
  }
  $detected = @()
  foreach ($key in 1, 2, 3, 4, 5) { if ($slotDetected[$key]) { $detected += $slotName[$key] } }
  if ($detected.Count -eq 0) { $detected = @('cursor') }

  Write-Host 'octop memory 卸载'
  Write-Host '检测到：'
  foreach ($key in 1, 2, 3, 4, 5) {
    if ($slotDetected[$key]) { Write-Host ("  {0}) {1}" -f $key, $slotHint[$key]) }
  }

  $terminals = $env:OCTOP_TERMINALS
  if (-not $terminals) { $terminals = $DEFAULT_TERMINALS }
  if (-not $terminals -and $interactive) {
    $attempt = 0
    while (-not $terminals -and $attempt -lt 3) {
      $attempt++
      $pick = Read-Host '要卸载哪些？(可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的)'
      $chosen = @()
      if (-not $pick -or $pick -match '^(?i)(a|all|全部)$') {
        $chosen = @($detected)
      }
      else {
        $tokens = @()
        foreach ($token in ($pick -replace '[,\s]+', ' ').Split(' ')) {
          if (-not $token) { continue }
          if ($token -match '^[0-9]{2,}$') {
            foreach ($char in $token.ToCharArray()) { $tokens += [string]$char }
          }
          else { $tokens += $token }
        }
        foreach ($token in $tokens) {
          $index = 0
          if (-not [int]::TryParse($token, [ref]$index) -or -not $slotDetected[$index]) {
            Write-Host "  ? 已忽略：$token"
            continue
          }
          $name = $slotName[$index]
          if ($chosen -notcontains $name) { $chosen += $name }
        }
      }
      if ($chosen.Count -gt 0) { $terminals = ($chosen -join ',') }
      else { Write-Host '  ! 没有选中任何终端，请重选（1-5，或 a=全部）' -ForegroundColor Yellow }
    }
  }
  if (-not $terminals) { throw '没有可卸载的终端：非交互请先设 $env:OCTOP_TERMINALS=cursor' }

  # ---- 卸载范围：全局（默认）还是只清某个项目里的注册
  # ?project= 预填只在**交互式**生效（变成默认答案）；非交互只认 OCTOP_PROJECT_DIR。
  # 显式设置（哪怕是空串）就以环境变量为准：空串 = 全局，不再交互提问。
  $projectSet = $null -ne $env:OCTOP_PROJECT_DIR
  $projectDir = ''
  if ($projectSet) { $projectDir = $env:OCTOP_PROJECT_DIR }
  if (-not $projectSet -and $interactive) {
    Write-Host '卸载范围：'
    Write-Host '  1) 全局（默认）'
    Write-Host '  2) 只清某个项目里的注册（用户目录里的脚本保留）'
    $defaultScope = '1'
    if ($DEFAULT_PROJECT) { $defaultScope = '2' }
    $scope = Read-Host "选择 [1/2]（回车=$defaultScope）"
    if (-not $scope) { $scope = $defaultScope }
    if ($scope -in @('2', 'p', 'P', 'project', '项目')) {
      $defaultProject = $DEFAULT_PROJECT
      if (-not $defaultProject) { $defaultProject = (Get-Location).Path }
      $projectDir = Read-Host "项目根目录 [$defaultProject]"
      if (-not $projectDir) { $projectDir = $defaultProject }
    }
  }
  if ($projectDir) {
    if ($projectDir -eq '~' -or $projectDir -eq '~/' -or $projectDir -eq '~\') { $projectDir = $HOME }
    elseif ($projectDir -match '^~[\\/]') { $projectDir = Join-Path $HOME $projectDir.Substring(2) }
    if (-not (Test-Path -LiteralPath $projectDir -PathType Container)) { throw "项目目录不存在（或不是目录）：$projectDir" }
    $projectDir = (Resolve-Path -LiteralPath $projectDir).Path
    Write-Host "  · 卸载范围：项目级 → $projectDir（用户目录里的 hook 脚本保留）"
  }

  $python = $null
  foreach ($spec in @('py -3', 'python', 'python3')) {
    $parts = $spec.Split(' ')
    $exe = Get-Command $parts[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $pre = @()
    if ($parts.Count -gt 1) { $pre = $parts[1..($parts.Count - 1)] }
    & $exe.Source @pre -c 'import sys; raise SystemExit(0)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = @($exe.Source) + $pre; break }
  }
  if (-not $python) { throw '未找到 python3：无法清理终端配置' }

  $payload = @{
    OCTOP_CC_DIR = $CC_DIR
    OCTOP_KIRO_DIR = $KIRO_DIR
    OCTOP_DSH_DIR = $DSH_DIR
    OCTOP_CODEX_DIR = $CODEX_DIR
    OCTOP_CURSOR_DIR = $CURSOR_DIR
    OCTOP_TERMINALS = $terminals
    OCTOP_PROJECT_DIR = [string]$projectDir
  }
  $envFile = [System.IO.Path]::GetTempFileName()
  $scriptFile = [System.IO.Path]::GetTempFileName()
  try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($envFile, ($payload | ConvertTo-Json -Compress), $utf8)
    $code = @'
__UNINSTALL_PY__
'@
    [System.IO.File]::WriteAllText($scriptFile, $code, $utf8)
    $env:OCTOP_ENV_FILE = $envFile
    $pyArgs = @()
    if ($python.Count -gt 1) { $pyArgs = $python[1..($python.Count - 1)] }
    $pythonExe = $python[0]
    & $pythonExe @pyArgs $scriptFile
    if ($LASTEXITCODE -ne 0) { throw "卸载失败（python 退出码 $LASTEXITCODE）" }
  }
  finally {
    Remove-Item -LiteralPath $envFile -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scriptFile -ErrorAction SilentlyContinue
  }
  Remove-Item Env:OCTOP_ENV_FILE -ErrorAction SilentlyContinue
}
"""


def render_uninstall_ps1(*, terminals: str = "", project: str = "") -> str:
    """Render the Windows uninstaller (counterpart of ``render_uninstall_script``).

    ``project`` is the **prefill** for a project-scoped uninstall; non-interactive runs read
    ``OCTOP_PROJECT_DIR`` (an explicitly empty value = global).
    """
    replacements = {
        "__DEFAULT_TERMINALS_LITERAL__": _ps_single_quote(terminals) if terminals else "''",
        "__DEFAULT_PROJECT_LITERAL__": _ps_single_quote(project) if project else "''",
        "__CC_DIR_REL__": _ps_home_rel(HOOKS_DIRS["claude-code"]),
        "__KIRO_DIR_REL__": _ps_home_rel(HOOKS_DIRS["kiro"]),
        "__DSH_DIR_REL__": _ps_home_rel(HOOKS_DIRS["dsh"]),
        "__CODEX_DIR_REL__": _ps_home_rel(HOOKS_DIRS["codex"]),
        "__CURSOR_DIR_REL__": _ps_home_rel(HOOKS_DIRS["cursor"]),
        "__UNINSTALL_PY__": _UNINSTALL_PY,
    }
    script = _UNINSTALL_PS_TEMPLATE
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    return script
