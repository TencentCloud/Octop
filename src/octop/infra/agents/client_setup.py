"""Bootstrap a local terminal so it talks to this memory service.

``GET /mcp/memory/setup`` streams the interactive installer this module renders — no
authentication, because it only hands out a script: the credentials are typed by the
person running it, never fetched::

    curl -fsSL "https://<octop>/mcp/memory/setup" | sh
    #   → 检测到：1) Claude Code  2) Kiro  3) DSH  4) Codex  5) Cursor
    #   → 要配置哪些？   token: ****（不回显）   专家 ID: XXXX   用户标识（建议域账号）: xxxx

``GET /mcp/memory/uninstall`` is the counterpart — removes hooks / MCP entries this
installer wrote (does not delete server-side memory)::

    curl -fsSL "https://<octop>/mcp/memory/uninstall" | OCTOP_TERMINALS=cursor sh

Nothing is assumed about where an installer runs. The script detects which terminals
exist, asks which to configure, prompts for the token and the expert id (reading
``/dev/tty`` — a piped script must not consume its own stdin), then installs a copy of
both hook scripts next to *each* terminal, in the directory that terminal uses, and
registers them in that terminal's own hook config:

===========================  ==========================================  ==============================
Claude Code                  ``~/.claude/hooks-events/``                  ``~/.claude/settings.json``
Kiro                         ``~/.kiro/hooks/``                           ``~/.kiro/hooks/*.json``
DSH                          ``~/.dsh/hooks/``                            ``~/.dsh/hooks/octop-hooks.json``
Codex                        ``~/.codex/hooks/``                          ``~/.codex/config.toml``
Cursor                       ``~/.cursor/hooks/``                         ``~/.cursor/hooks.json``
===========================  ==========================================  ==============================

Each copy carries its own ``config.json`` (endpoint, token, expert). The hook roles are
fixed: **UserPromptSubmit / beforeSubmitPrompt → memory_search** (pull background in)
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
    "dsh": ("dsh/stop-capture.mjs", "dsh/user-prompt-recall.mjs", "dsh/memory-target.mjs"),
    "codex": ("codex/stop-capture.mjs", "codex/user-prompt-recall.mjs"),
    "cursor": ("cursor/stop-capture.mjs", "cursor/user-prompt-recall.mjs"),
}
"""Which hook scripts a terminal gets. Each host has its own entry script — no
runtime host detection — so changing one host cannot affect another; the only
shared file is the host-agnostic transport module."""

_DSH_PRESET_SRC = Path(__file__).with_name("agent_presets") / "dsh-memory-share"
_DSH_PRESET_FILES = ("package.json", "cordis.patch.yml")
"""DSH ≥0.1.7 declares presets in a bundle patch, so the installer ships one:
``记忆共享模式`` = the shipped ``cordis`` plugin list + the memory hooks row."""

TERMINALS: tuple[str, ...] = ("claude-code", "kiro", "dsh", "codex", "cursor")
"""Terminals this installer knows how to configure."""

# Owned by each terminal, so no cross-terminal directory is invented.
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


def _install_hooks(target, host):
    """把共享传输模块 + 该宿主的入口脚本写进这个终端自己的 hooks 目录。"""
    target.mkdir(parents=True, exist_ok=True)
    for rel, blob in HOOK_FILES[host].items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(blob))
    config = {"url": HOOK_URL, "token": TOKEN, "tokenHeader": TOKEN_HEADER, "agentId": AGENT}
    if USER_ID:
        config["userId"] = USER_ID  # 直连端点时「谁问的」只靠这个头
    _dump(target / "config.json", config)
    print(f"  ✓ hook 脚本（{host} 专用，含共享传输模块）+ config.json → {target}")
    print(
        f"      · 日志/增量状态：{target}/octop-hook.log、{target}/octop-transcript-state.json"
        "（该目录不可写时退到 $TMPDIR/octop-hooks 并打印告警）"
    )


def _entry(transport=None):
    # 两种模式，凭据各带各的：
    #   直连（条目落在实例挂载点）：带**实例共享 token**；header 名由 ``OCTOP_TOKEN_HEADER``
    #   决定（缺省 ``Authorization`` → ``Bearer <token>``），身份只能靠 ``X-Octop-User-Id``
    #   头表达。
    #   OAuth 前置（条目指向代理）：必须带**个人令牌**；header 名由 ``OCTOP_ENTRY_TOKEN_HEADER``
    #   决定（缺省 ``Authorization``），身份由代理按令牌重写，所以条目不写 ``X-Octop-User-Id``。
    headers = {"X-Octop-Agent-Id": AGENT}
    if OAUTH_ENTRY:
        if ENTRY_TOKEN:
            header = ENTRY_TOKEN_HEADER or "Authorization"
            headers[header] = f"Bearer {ENTRY_TOKEN}" if header == "Authorization" else ENTRY_TOKEN
    else:
        headers[TOKEN_HEADER] = f"Bearer {TOKEN}" if TOKEN_HEADER == "Authorization" else TOKEN
        if USER_ID:
            headers["X-Octop-User-Id"] = USER_ID  # 「谁问的」靠这个头，不靠 token 解析
    entry = {"type": transport or "http", "url": ENTRY_URL, "headers": headers}
    return entry


def _octop_servers(servers):
    """配置里已有的 octop memory 服务名——``local`` / ``prod`` / ``oauth`` / ``test`` 都算。"""
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
    # **简写形态**：事件直接挂 handler 数组，不套 matcher 组那层。我们的 hook 对所有调用都生效，
    # 本来就不需要 matcher；而某些终端的 SDK 侧不保证 ``hooks`` 数组按顺序执行，
    # 少一层嵌套更稳（老配置里的嵌套形态仍会被识别并替换，见 _handlers_of）。
    return {"UserPromptSubmit": [search], "Stop": [stop]}


_OUR_SCRIPTS = (
    "user-prompt-recall.mjs",
    "stop-capture.mjs",
    # 包装脚本（配置里引用的是 .sh）
    "user-prompt-recall.sh",
    "stop-capture.sh",
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
      最有价值的就是**原始的用户/助手消息**，绝不能让模型自己总结（早期版本在共享 token
      下退化为 ``agent`` 提示词，结果是"AI 复述"进 L0）。共享 token 下"谁问的"由脚本带的
      ``X-Octop-User-Id``（安装时的 ``OCTOP_USER_ID``）表达，不再需要额外的个人令牌。
    """
    _merge_mcp(home / ".kiro" / "settings" / "mcp.json", transport="streamable_http")
    _install_hooks(KIRO_DIR, "kiro")

    recall = KIRO_DIR / "memory-recall-on-start.json"
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

    save = KIRO_DIR / "memory-save-on-stop.json"
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
        ours = str(CODEX_DIR) in body
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
            entry
            for entry in hooks.get(event) or []
            if str(CURSOR_DIR) not in json.dumps(entry, ensure_ascii=False)
        ]
        entries.append({"command": hook_command(f"{CURSOR_DIR}/cursor/{script}.mjs")})
        hooks[event] = entries
    _dump(path, cfg)


def do_codex():
    """Codex：hook 写在 ``~/.codex/config.toml``（``[[hooks.<Event>]]`` + ``type="command"``）。

    codex 对 hook 有信任机制：新写入的 hook 需要用户信任一次才会执行，所以这里只写配置、
    不伪造 ``hooks.state`` 里的 ``trusted_hash``。
    """
    _install_hooks(CODEX_DIR, "codex")
    config = home / ".codex" / "config.toml"
    _codex_upsert(config)
    print(f"  ✓ Codex hooks（UserPromptSubmit → 召回；Stop → 上报）→ {config}")
    print("      · 首次需在 codex 里信任该 hook（否则不执行）；自动化可加 --dangerously-bypass-hook-trust")
    print("      · Codex 的 MCP 服务由它自己的配置管理，这里不动")


def do_cursor():
    """Cursor：hook 写在 ``~/.cursor/hooks.json``（``{"version":1,"hooks":{<event>:[{command}]}}``）。"""
    _install_hooks(CURSOR_DIR, "cursor")
    hooks = home / ".cursor" / "hooks.json"
    _cursor_upsert(hooks)
    print(f"  ✓ Cursor hooks（beforeSubmitPrompt → 召回；stop → 上报）→ {hooks}")
    print("      · Cursor 的 MCP 服务由它自己的配置管理，这里不动")


def _dsh_bridge(hooks_dir):
    """DSH 的 hooks 桥接只执行 command 钩子（mcp_tool / prompt 会被跳过），故写死 command。"""
    return {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": hook_command(f"{hooks_dir}/dsh/user-prompt-recall.mjs")}
                    ]
                }
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": hook_command(f"{hooks_dir}/dsh/stop-capture.mjs")}]}
            ],
        }
    }


def _dsh_profile():
    """装哪个 profile：OCTOP_DSH_PROFILE，否则按 web / desktop / default 取第一个存在的。"""
    profiles = home / ".dsh" / "profiles"
    wanted = os.environ.get("OCTOP_DSH_PROFILE", "")
    for name in ([wanted] if wanted else ["web", "desktop", "default"]):
        if name and (profiles / name / "package.json").exists():
            return name, profiles / name
    return "", pathlib.Path()


def _install_dsh_preset(bridge):
    """把「记忆共享模式」bundle 写到 ~/.dsh/bundles，configPath 换成刚写好的桥接文件。"""
    bundle = DSH_DIR.parent / "bundles" / "dsh-memory-share"
    for name, blob in PRESET_FILES.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            base64.b64decode(blob).decode("utf-8").replace("__OCTOP_HOOKS_JSON__", str(bridge)),
            encoding="utf-8",
        )
    return bundle


def _select_dsh_bundle(profile_dir, name):
    """把 bundle 加进 profile 的 dsh.profile.bundles（幂等）——DSH 只按那里的名字加载 bundle。"""
    package = profile_dir / "package.json"
    config = _load(package)
    if config is None:
        return False
    bundles = config.setdefault("dsh", {}).setdefault("profile", {}).setdefault("bundles", [])
    if name in bundles:
        return True
    bundles.append(name)
    package.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    return True


def _run_dsh_install(bundle, profile, profile_dir):
    """把 bundle 装进 profile：优先 dsh CLI，其次直接 pnpm（源码 checkout 常没有 dsh 命令）。

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


def do_dsh():
    """装 hook 脚本 + 桥接文件（只有 command 钩子），并把 preset bundle 装进 profile。

    DSH 0.1.7 起 preset 由 bundle patch 声明，旧版「在 agent preset 文件里加一行」已经
    不再生效，所以这里直接生成 bundle 并装进 profile 的 dsh.profile.bundles。

    脚本直传不再挑 token 方言：共享 token 下"谁问的"由脚本带的 ``X-Octop-User-Id``
    （安装时的 ``OCTOP_USER_ID``）表达，所以任何模式都装 hooks。
    """
    _install_hooks(DSH_DIR, "dsh")
    bridge = DSH_DIR / "octop-hooks.json"
    _dump(bridge, _dsh_bridge(DSH_DIR))
    print(f"  ✓ DSH hooks 桥接（UserPromptSubmit → 召回；Stop → 上报）→ {bridge}")
    bundle = _install_dsh_preset(bridge)
    name = json.loads((bundle / "package.json").read_text(encoding="utf-8"))["name"]
    print(f"  ✓ DSH 模式 bundle「记忆共享模式」→ {bundle}")
    profile, profile_dir = _dsh_profile()
    if not profile:
        print("  ! 没找到 DSH profile（~/.dsh/profiles/<web|desktop|default>），跳过自动安装")
    elif _run_dsh_install(bundle, profile, profile_dir) and _select_dsh_bundle(profile_dir, name):
        print(f"  ✓ 已装进 profile「{profile}」：重启 DSH 后，新会话的模式里选「记忆共享模式」")
    else:
        print("  ! 没自动装进 profile，手动两步：")
        print(f"      1) 在 {profile_dir} 执行：pnpm add {bundle}")
        print(f"      2) 把 {name} 加进该目录 package.json 的 dsh.profile.bundles，然后重启 DSH")
    if OAUTH_ENTRY:
        print("      · DSH 侧这条目带个人令牌（OAuth 前置），静态凭据由代理校验")
    print("  · DSH 的 MCP 服务请在它的 MCP 面板/CLI 里添加（该条目由 DSH 自己管理）：")
    print(f"      url: {URL}")
    print(f"      headers: {json.dumps(_entry()['headers'], ensure_ascii=False)}")


home = pathlib.Path(os.path.expanduser("~"))
URL = os.environ["OCTOP_URL"]
HOOK_URL = os.environ.get("OCTOP_HOOK_URL") or URL   # hooks 实际 POST 的地址（直连）
TOKEN = os.environ["OCTOP_TOKEN"]
TOKEN_HEADER = os.environ["OCTOP_TOKEN_HEADER"]
# 条目专属凭据（只有 OAuth 前置用得到）：hooks 打实例、客户端条目打代理，两个凭据可以不同。
ENTRY_TOKEN = os.environ.get("OCTOP_ENTRY_TOKEN", "").strip()
ENTRY_TOKEN_HEADER = os.environ.get("OCTOP_ENTRY_TOKEN_HEADER", "").strip()
NODE = os.environ.get("OCTOP_NODE") or "node"  # 安装时解析出的绝对路径（非 login shell 也能跑）
# 用户标识：token 的唯一作用是让服务端知道「谁问的」，直连端点时只能靠这个头。
# 建议填域账号：HTTP header 只能是 ASCII，Node 的 fetch 对非 ASCII 直接抛错（hook 会崩）。
USER_ID = os.environ.get("OCTOP_USER_ID", "").strip()
if USER_ID and not USER_ID.isascii():
    print(f"  ! 用户标识「{USER_ID}」含非 ASCII 字符：header 传不了（hook 会直接报错），已忽略")
    print("      · 请填域账号（如 alice）；要中文显示名需服务端支持 percent 解码")
    USER_ID = ""
# MCP 条目只有两种模式：**OAuth（默认）** 或 直连 MCP token（明确不要 OAuth 时）。
#   OCTOP_DISABLE_OAUTH=true（1/yes）→ 直连：条目写 X-Octop-Agent-Id + 实例共享 token
#   不传 / false（0/no）              → OAuth：条目只留 X-Octop-Agent-Id，Authorization 由客户端临时注入
_DISABLE_OAUTH = (os.environ.get("OCTOP_DISABLE_OAUTH") or "").strip().lower()
if _DISABLE_OAUTH in ("", "0", "false", "no"):
    OAUTH_ENTRY = True
elif _DISABLE_OAUTH in ("1", "true", "yes"):
    OAUTH_ENTRY = False
else:
    raise SystemExit(
        f"OCTOP_DISABLE_OAUTH 只能填 true/false（1/0），收到 {_DISABLE_OAUTH!r}"
    )

# 模式与地址是配对的：OAuth 只能打代理（静态 token 在那儿会被 401），直连必须打 octop 实例
# 自己的挂载点（代理不做静态 token）。所以由模式决定条目地址，而不是由地址猜模式。
if OAUTH_ENTRY and URL == HOOK_URL:
    # 部署没声明 OAuth 前置地址 → OAuth 条目点的是实例挂载点、又没凭据，必然 401。
    # 这时按直连模式生成（实例 token 走 Authorization，身份靠 X-Octop-User-Id）。
    print("  · 本实例未声明 OAuth 前置地址（memory_public_mcp_url / ?url=）→ 按直连模式生成条目")
    OAUTH_ENTRY = False

if OAUTH_ENTRY:
    ENTRY_URL = URL  # 部署声明的代理地址（memory_public_mcp_url / ?url=）
    NAME = os.environ["OCTOP_SERVER_NAME"]
    if not ENTRY_TOKEN:
        print("  ! OAuth 前置必须带个人令牌，但没拿到：条目调用会 401")
        print("      · 重跑并设 OCTOP_ENTRY_TOKEN=<token>")
else:
    ENTRY_URL = HOOK_URL  # 直连不认识代理，声明了也不用
    NAME = os.environ["OCTOP_SERVER_NAME_DIRECT"]
    if URL != HOOK_URL:
        print(f"  · 直连模式忽略声明的代理地址 {URL}，条目指向实例 {HOOK_URL}")


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
    wrapper = mjs.with_suffix(".sh")
    lines = [
        "#!/bin/sh",
        "# octop memory hook（安装器生成，勿手改）：配置里只引用本文件路径",
    ]
    if os.environ.get("OCTOP_USE_SYSTEM_CA") == "1":
        lines.append('export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--use-system-ca"')
    lines.append(
        f"{shlex.quote(str(NODE))} {shlex.quote(str(mjs))} "
        '|| echo "octop-memory: hook 执行失败（node 路径不对或脚本报错）" >&2'
    )
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return shlex.quote(str(wrapper))
AGENT = os.environ["OCTOP_AGENT"]
CC_DIR = pathlib.Path(os.environ["OCTOP_CC_DIR"]).expanduser()
KIRO_DIR = pathlib.Path(os.environ["OCTOP_KIRO_DIR"]).expanduser()
DSH_DIR = pathlib.Path(os.environ["OCTOP_DSH_DIR"]).expanduser()
CODEX_DIR = pathlib.Path(os.environ["OCTOP_CODEX_DIR"]).expanduser()
CURSOR_DIR = pathlib.Path(os.environ["OCTOP_CURSOR_DIR"]).expanduser()
HOOK_FILES = {
    host: json.loads(os.environ["OCTOP_FILES_" + host.upper().replace("-", "_")])
    for host in ("claude-code", "kiro", "dsh", "codex", "cursor")
}
PRESET_FILES = json.loads(os.environ["OCTOP_FILES_PRESET"])

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

print("  · hook 角色：用户提交时召回（CC / DSH / Codex 的 UserPromptSubmit，Cursor 的 beforeSubmitPrompt）；")
print("    回合结束时上报（Stop / Cursor 的 stop）")
how = (
    f"OAuth 前置：条目带个人令牌（{ENTRY_TOKEN_HEADER or 'Authorization'}）"
    if OAUTH_ENTRY
    else f"直连 MCP token：条目写 {TOKEN_HEADER}"
)
print(f"  · hooks 直连 {HOOK_URL}；客户端 MCP 条目指向 {ENTRY_URL}（{how}）")
if USER_ID:
    where = (
        "只写进 hooks 的 X-Octop-User-Id；条目身份由代理按令牌重写"
        if OAUTH_ENTRY
        else "写进条目 X-Octop-User-Id 与 hooks"
    )
    print(f"  · 用户标识：{USER_ID}（{where}）")
print("  · octop memory 接入完成（可重复执行，不会影响其它 MCP/hook 条目）")
'''.strip()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _host_manifest(host: str) -> str:
    """``{relative path: base64}`` for one host: its entries + the shared lib modules."""
    files = (*_LIB_FILES, *HOST_FILES[host])
    payload = {name: _b64((_HOOKS_SRC / name).read_text(encoding="utf-8")) for name in files}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _dsh_preset_manifest() -> str:
    """``{relative path: base64}`` for the DSH preset bundle the installer writes."""
    payload = {
        name: _b64((_DSH_PRESET_SRC / name).read_text(encoding="utf-8"))
        for name in _DSH_PRESET_FILES
    }
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


def render_setup_script(
    *,
    mcp_url: str,
    hook_url: str = "",
    agent_id: str = "",
    terminals: str = "",
    default_token: str = "",
) -> str:
    """Render the interactive installer.

    ``mcp_url`` 是登记进客户端 MCP 条目的地址；``hook_url`` 是 hooks 真正 POST 的地址，
    默认同 ``mcp_url``。两者不同 = 条目走 OAuth 前置（客户端自己授权，条目不写凭据）；
    MCP 条目默认 **OAuth**（条目不写凭据，Authorization 由客户端临时注入）；明确不要 OAuth 时
    用 ``OCTOP_DISABLE_OAUTH=true`` 走直连 MCP token。

    ``default_token`` 是部署内置的默认凭据（实例发布时设置了 ``OCTOP_MEMORY_MCP_TOKEN``）：
    脚本把它当 ``OCTOP_MEMORY_TOKEN`` 的兜底，于是用户只需要专家 ID（可选用户标识）。
    为空时照旧在安装时问 token；header 名由 ``OCTOP_TOKEN_HEADER`` /
    ``OCTOP_ENTRY_TOKEN_HEADER`` 决定，缺省 ``Authorization``（此时值写成 ``Bearer <token>``）。
    ``agent_id`` 和 ``terminals``（逗号清单）只是给自动化预填提示用。
    """
    hook_url = hook_url or mcp_url
    token_literal = _sh_single_quote(default_token) if default_token else "''"
    # Query-string prefills must be shell-safe (same escaping as DEFAULT_TOKEN).
    url_literal = _sh_single_quote(mcp_url)
    hook_url_literal = _sh_single_quote(hook_url)
    agent_literal = _sh_single_quote(agent_id) if agent_id else "''"
    terminals_literal = _sh_single_quote(terminals) if terminals else "''"
    default_token_line = f"DEFAULT_TOKEN={token_literal}" if default_token else ""
    default_token_block = (
        f"""if [ -z "$TOKEN" ] && [ -n {token_literal} ]; then
  TOKEN={token_literal}
  echo "  · token：用本实例部署时配置的默认凭据（要覆盖设 OCTOP_MEMORY_TOKEN）"
fi"""
        if default_token
        else ""
    )
    return f"""#!/bin/sh
# octop memory — 本地终端接入（hooks 发往 {hook_url}；可重复执行）
set -eu

URL={url_literal}
HOOK_URL={hook_url_literal}
DEFAULT_AGENT={agent_literal}
{default_token_line}
DEFAULT_TERMINALS={terminals_literal}
CC_DIR='{HOOKS_DIRS["claude-code"]}'
KIRO_DIR='{HOOKS_DIRS["kiro"]}'
DSH_DIR='{HOOKS_DIRS["dsh"]}'
CODEX_DIR='{HOOKS_DIRS["codex"]}'
CURSOR_DIR='{HOOKS_DIRS["cursor"]}'

# hooks 与「客户端 MCP 条目」可以是两个地址（默认同一个）：条目可以走 OAuth 前置
# （客户端自己授权，条目里不写凭据），hooks 永远直连本实例。
SPLIT=0
[ "$URL" = "$HOOK_URL" ] || SPLIT=1

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
[ "$have_dsh" = 1 ] && echo "  3) DSH　　　　（hook 装到 ~/.dsh/hooks）"
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
    [ "$have_dsh" = 1 ] && set -- "$@" "dsh|DSH　（hook 装到 ~/.dsh/hooks）"
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
              [0-9][0-9]*) _items="$(printf '%s' "$_n" | fold -w1 | tr '\n' ' ')" ;;
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

# 本机实例（loopback）的共享 token 走 Authorization: Bearer；判据用 hooks 真正要打的地址。
URL_HOST="$(printf '%s' "$HOOK_URL" | sed -e 's#^[^/]*//##' -e 's#/.*##' -e 's#:.*##')"
IS_LOCAL=0
case "$URL_HOST" in
  127.0.0.1|localhost) IS_LOCAL=1 ;;
esac

# ---- 3) 凭据：hooks 与「客户端 MCP 条目」各带各的
# 模式：部署声明了 OAuth 前置地址（SPLIT=1）且没显式 OCTOP_DISABLE_OAUTH=true → OAuth 前置；
# 其余（含"没声明代理地址"）→ 直连。
MODE=direct
if [ "$SPLIT" = 1 ]; then
  case "${{OCTOP_DISABLE_OAUTH:-}}" in
    1|true|yes) MODE=direct ;;
    *)          MODE=oauth ;;
  esac
fi

# hooks 的凭据永远是「实例共享 token」（部署内置的 DEFAULT_TOKEN 就是它），与模式无关。
TOKEN="${{OCTOP_MEMORY_TOKEN:-}}"
{default_token_block}
if [ -z "$TOKEN" ] && [ "$HAS_TTY" = 1 ]; then
  stty -echo < /dev/tty 2>/dev/null || true
  if [ "$SPLIT" = 1 ]; then
    printf '共享 token（hook 直连端点 %s 用，通常是 octopoctop）: ' "$HOOK_URL" > /dev/tty
  elif [ "$IS_LOCAL" = 1 ]; then
    printf '共享 token（本机实例，走 Authorization: Bearer）: ' > /dev/tty
  else
    printf '共享 token（云上实例）: ' > /dev/tty
  fi
  read -r _t < /dev/tty || _t=''
  stty echo < /dev/tty 2>/dev/null || true
  printf '\n' > /dev/tty
  [ -n "$_t" ] && TOKEN="$_t"
fi
[ -n "$TOKEN" ] || {{ echo "缺少 token：非交互运行时请设 OCTOP_MEMORY_TOKEN=<token>" >&2; exit 1; }}
# header 名可配（缺省 Authorization）；header 是 Authorization 时值写成 ``Bearer <token>``。
TOKEN_HEADER="${{OCTOP_TOKEN_HEADER:-Authorization}}"

# 条目凭据：只有 OAuth 前置（条目指向代理）才需要，且**必须**给个人令牌。没给就当场问；
# 非交互（CI）拿不到就报错，不写一个必然 401 的条目。
ENTRY_TOKEN=''
ENTRY_TOKEN_HEADER=''
if [ "$MODE" = oauth ]; then
  ENTRY_TOKEN="${{OCTOP_ENTRY_TOKEN:-}}"
  if [ -z "$ENTRY_TOKEN" ] && [ "$HAS_TTY" = 1 ]; then
    stty -echo < /dev/tty 2>/dev/null || true
    printf '个人令牌（OAuth 前置必须；不回显）: ' > /dev/tty
    read -r _et < /dev/tty || _et=''
    stty echo < /dev/tty 2>/dev/null || true
    printf '\n' > /dev/tty
    if [ -n "$_et" ]; then ENTRY_TOKEN="$_et"; fi
  fi
  if [ -z "$ENTRY_TOKEN" ]; then
    echo "  ! OAuth 前置（${{URL}}）必须带个人令牌：请设 OCTOP_ENTRY_TOKEN=<token> 后重跑" >&2
    exit 1
  fi
  ENTRY_TOKEN_HEADER="${{OCTOP_ENTRY_TOKEN_HEADER:-Authorization}}"
fi
echo "  · hook 直连：$HOOK_URL$([ "$IS_LOCAL" = 1 ] && echo '（本机实例）' || true)"
if [ "$MODE" = oauth ]; then
  echo "  · 客户端 MCP 条目：${{URL}}（OAuth 前置：带个人令牌 ${{ENTRY_TOKEN_HEADER}}）"
else
  echo "  · 客户端 MCP 条目：${{HOOK_URL}}（直连 MCP token：写 ${{TOKEN_HEADER}}）"
fi
echo "  · 认证方式：$TOKEN_HEADER"

AGENT="${{OCTOP_AGENT_ID:-}}"
if [ -z "$AGENT" ]; then
  if [ -n "$DEFAULT_AGENT" ]; then
    AGENT="$(ask "专家 ID [$DEFAULT_AGENT]: " "$DEFAULT_AGENT")"
  else
    AGENT="$(ask "专家 ID: " "")"
  fi
fi
[ -n "$AGENT" ] || {{ echo "缺少专家 ID：非交互运行时请设 OCTOP_AGENT_ID=<id>" >&2; exit 1; }}

# 用户标识（建议域账号）：直连时「谁问的」只能靠 X-Octop-User-Id（条目和 hooks 都写它）；
# OAuth 前置时条目身份由代理按令牌重写，但 hooks 仍靠这个头 —— 两种模式都问一次。
USER_ID="${{OCTOP_USER_ID:-}}"
if [ -z "$USER_ID" ] && [ "$HAS_TTY" = 1 ]; then
  USER_ID="$(ask "用户标识（建议填域账号，如 alice；写进 X-Octop-User-Id 标记谁问的）: " "")"
fi

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
  OCTOP_URL="$HOOK_URL" OCTOP_TOKEN="$TOKEN" OCTOP_TOKEN_HEADER="$TOKEN_HEADER" \\
  OCTOP_AGENT="$AGENT" "$NODE_BIN" --input-type=module -e '
const cfg = {{ url: process.env.OCTOP_URL, token: process.env.OCTOP_TOKEN }};
const headers = {{ "Content-Type": "application/json", Accept: "application/json, text/event-stream",
  "X-Octop-Agent-Id": process.env.OCTOP_AGENT }};
const header = process.env.OCTOP_TOKEN_HEADER || "Authorization";
headers[header] = header === "Authorization" ? `Bearer ${{cfg.token}}` : cfg.token;
try {{
  const r = await fetch(cfg.url, {{ method: "POST", headers, signal: AbortSignal.timeout(8000), body: JSON.stringify({{ jsonrpc: "2.0", id: 1, method: "tools/list" }}) }});
  console.log(`  · 端点自检（hook 直连）：HTTP ${{r.status}}${{r.status === 200 ? "" : "（凭据或地址不对，请检查）"}}`);
}} catch (e) {{
  console.log(`  · 端点自检失败：${{e}}（安装仍继续，请自行确认地址）`);
}}
' 2>/dev/null || true
fi

# ---- 5) 各终端各自安装 hook 脚本 + 合并其配置
OCTOP_URL="$URL" OCTOP_HOOK_URL="$HOOK_URL" OCTOP_TOKEN="$TOKEN" OCTOP_TOKEN_HEADER="$TOKEN_HEADER" \\
OCTOP_ENTRY_TOKEN="$ENTRY_TOKEN" OCTOP_ENTRY_TOKEN_HEADER="$ENTRY_TOKEN_HEADER" \\
OCTOP_AGENT="$AGENT" OCTOP_SERVER_NAME='{_server_name(mcp_url)}' \\
OCTOP_SERVER_NAME_DIRECT='{_server_name(hook_url)}' \\
OCTOP_USER_ID="$USER_ID" \\
OCTOP_CC_DIR="$CC_DIR" OCTOP_KIRO_DIR="$KIRO_DIR" OCTOP_DSH_DIR="$DSH_DIR" \\
OCTOP_CODEX_DIR="$CODEX_DIR" OCTOP_CURSOR_DIR="$CURSOR_DIR" \\
OCTOP_TERMINALS="$TERMINALS" \\
OCTOP_FILES_CLAUDE_CODE='{_host_manifest("claude-code")}' \\
OCTOP_FILES_KIRO='{_host_manifest("kiro")}' \\
OCTOP_FILES_DSH='{_host_manifest("dsh")}' \\
OCTOP_FILES_CODEX='{_host_manifest("codex")}' \\
OCTOP_FILES_CURSOR='{_host_manifest("cursor")}' \\
OCTOP_FILES_PRESET='{_dsh_preset_manifest()}' \\
python3 - <<'OCTOP_PY'
{_MERGE_PY}
OCTOP_PY

echo "  · 重开终端/IDE（Kiro 重载 hooks；Codex 首次需在 codex 里信任该 hook）后生效"
"""


_UNINSTALL_PY = r"""
import json
import os
import pathlib
import shutil


home = pathlib.Path(os.path.expanduser("~"))
CC_DIR = pathlib.Path(os.environ["OCTOP_CC_DIR"]).expanduser()
KIRO_DIR = pathlib.Path(os.environ["OCTOP_KIRO_DIR"]).expanduser()
DSH_DIR = pathlib.Path(os.environ["OCTOP_DSH_DIR"]).expanduser()
CODEX_DIR = pathlib.Path(os.environ["OCTOP_CODEX_DIR"]).expanduser()
CURSOR_DIR = pathlib.Path(os.environ["OCTOP_CURSOR_DIR"]).expanduser()

_OUR_SCRIPTS = (
    "user-prompt-recall.mjs",
    "stop-capture.mjs",
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


def undo_claude_code():
    settings = home / ".claude" / "settings.json"
    st = _load(settings)
    if st is not None:
        hooks = st.setdefault("hooks", {})
        changed = False
        for event in list(hooks):
            kept = [
                group
                for group in (hooks.get(event) or [])
                if not any(_is_our_handler(h) for h in (group or {}).get("hooks") or [])
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
    _strip_mcp(home / ".claude.json")
    _rm_tree(CC_DIR, "Claude Code hooks 目录")


def undo_kiro():
    for name in ("memory-recall-on-start.json", "memory-save-on-stop.json"):
        path = KIRO_DIR / name
        if path.exists():
            path.unlink()
            print(f"  ✓ 已删除 Kiro hook 文件 → {path}")
        else:
            print(f"  · Kiro hook 文件不存在 → {path}")
    _strip_mcp(home / ".kiro" / "settings" / "mcp.json")
    _rm_tree(KIRO_DIR, "Kiro hooks 目录")


def undo_dsh():
    bridge = DSH_DIR / "octop-hooks.json"
    if bridge.exists():
        bridge.unlink()
        print(f"  ✓ 已删除 DSH 桥接 → {bridge}")
    bundle = DSH_DIR.parent / "bundles" / "dsh-memory-share"
    if bundle.exists():
        shutil.rmtree(bundle)
        print(f"  ✓ 已删除 DSH preset bundle → {bundle}")
    profiles = home / ".dsh" / "profiles"
    for name in ("web", "desktop", "default"):
        package = profiles / name / "package.json"
        cfg = _load(package)
        if cfg is None:
            continue
        bundles = cfg.get("dsh", {}).get("profile", {}).get("bundles")
        if not isinstance(bundles, list):
            continue
        kept = [b for b in bundles if b != "dsh-memory-share"]
        if len(kept) != len(bundles):
            cfg["dsh"]["profile"]["bundles"] = kept
            _dump(package, cfg)
            print(f"  ✓ 已从 DSH profile「{name}」去掉 dsh-memory-share")
    _rm_tree(DSH_DIR, "DSH hooks 目录")


def _toml_blocks(text):
    blocks = [[]]
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("[") and not line.lstrip().startswith("#"):
            blocks.append([])
        blocks[-1].append(line)
    return blocks


def undo_codex():
    path = home / ".codex" / "config.toml"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        blocks, kept = _toml_blocks(text), []
        removed = 0
        for block in blocks:
            body = "".join(block)
            header = block[0].strip() if block else ""
            ours = str(CODEX_DIR) in body
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
    _rm_tree(CODEX_DIR, "Codex hooks 目录")


def undo_cursor():
    path = home / ".cursor" / "hooks.json"
    cfg = _load(path)
    if cfg is not None:
        hooks = cfg.setdefault("hooks", {})
        marker = str(CURSOR_DIR)
        changed = False
        for event in list(hooks):
            entries = hooks.get(event) or []
            kept = [
                entry
                for entry in entries
                if marker not in json.dumps(entry, ensure_ascii=False)
            ]
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
""".strip()


def render_uninstall_script(*, terminals: str = "") -> str:
    """Render the interactive uninstaller (counterpart of ``render_setup_script``).

    No token / agent prompts — only chooses which terminals to scrub. Safe to
    re-run; leaves non-octop hooks and MCP servers alone.
    """
    terminals_literal = _sh_single_quote(terminals) if terminals else "''"
    return f"""#!/bin/sh
# octop memory — 卸载本地终端接入（与 /mcp/memory/setup 相对；可重复执行）
set -eu

DEFAULT_TERMINALS={terminals_literal}
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
[ "$have_dsh" = 1 ] && echo "  3) DSH　　　　（清 ~/.dsh/hooks + preset）"
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
command -v python3 >/dev/null 2>&1 || {{ echo "  ! 未找到 python3" >&2; exit 1; }}

OCTOP_CC_DIR="$CC_DIR" OCTOP_KIRO_DIR="$KIRO_DIR" OCTOP_DSH_DIR="$DSH_DIR" \\
OCTOP_CODEX_DIR="$CODEX_DIR" OCTOP_CURSOR_DIR="$CURSOR_DIR" \\
OCTOP_TERMINALS="$TERMINALS" \\
python3 - <<'OCTOP_PY'
{_UNINSTALL_PY}
OCTOP_PY
"""
