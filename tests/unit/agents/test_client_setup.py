"""Unit tests for the interactive local-terminal installer generator."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from octop.infra.agents.client_setup import (
    _DSH_NATIVE_FILES,
    _DSH_NATIVE_NAME,
    _DSH_NATIVE_SRC,
    _MERGE_PY,
    _SELECT_PY,
    _UNINSTALL_PY,
    HOOKS_DIRS,
    TERMINALS,
    render_setup_ps1,
    render_setup_script,
    render_uninstall_ps1,
    render_uninstall_script,
)

_URL = "http://127.0.0.1:8088/mcp/memory/"
_TOKEN = "omcp_test_token"

posix_only = pytest.mark.skipif(os.name != "posix", reason="假的 dsh 命令用 POSIX 可执行脚本")


def _script(**overrides) -> str:
    kwargs = {"mcp_url": _URL}
    kwargs.update(overrides)
    return render_setup_script(**kwargs)


# ---------------------------------------------------------------- 生成脚本的静态形态


def test_installer_detects_the_local_terminals() -> None:
    script = _script()

    assert '[ -e "$HOME/.claude.json" ] || [ -d "$HOME/.claude" ] || command -v claude' in script
    assert '[ -d "$HOME/.kiro" ] || command -v kiro' in script
    assert '[ -d "$HOME/.dsh" ] || command -v dsh' in script
    assert 'echo "  1) Claude Code' in script
    assert 'echo "  2) Kiro' in script
    assert 'echo "  3) DSH' in script


def test_installer_asks_for_a_user_mcp_token_not_a_user_id() -> None:
    """凭据是**用户级 MCP token**（token 绑定专家）：只问 token，不问专家 ID / 用户标识。"""
    script = _script()

    # 交互走 /dev/tty：curl | sh 时 stdin 是脚本本身，直接 read 会把脚本吃掉
    assert "if (true </dev/tty) 2>/dev/null; then HAS_TTY=1; fi" in script
    assert script.count("< /dev/tty") >= 2  # 探测 + 选择 + token
    assert "要配置哪些？" in script
    assert "专家 ID" not in script  # token 绑定专家，不再问专家 ID
    # token 提示说明去哪儿创建（omcp_…），且不回显
    assert "MCP token（omcp_…，在 Octop 的 /api/memory-mcp/tokens 创建；不回显）" in script
    assert "stty -echo" in script
    # 没有 tty 时不盲读 stdin，而是明确要求环境变量
    assert 'TOKEN="${OCTOP_MEMORY_TOKEN:-}"' in script
    assert "非交互运行时请设 OCTOP_MEMORY_TOKEN" in script
    assert "OCTOP_AGENT" not in script  # 没有专家 ID 这个必填项
    # 「用户标识」这一整套概念消失：token 就代表「谁问的」
    assert "OCTOP_USER_ID" not in script
    assert "X-Octop-User-Id" not in script
    assert "用户标识" not in script
    assert "userId" not in script
    # 也不再有第二份凭据 / OAuth 前置 / token 方言
    assert "OCTOP_ENTRY_TOKEN" not in script
    assert "OCTOP_DISABLE_OAUTH" not in script
    assert "个人令牌" not in script
    assert "OCTOP_TOKEN_HEADER" not in script


def test_terminal_pick_allows_multiselect() -> None:
    """五个选项可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的。"""
    script = _script()

    assert "可多选：1,2 / 1 3 / 12 / a=全部" in script
    assert "''|a|A|all|ALL|全部) _chosen=\"$DETECTED\"" in script
    assert "fold -w1" in script  # 连写数字 12/13 按位拆开
    assert 'case ",$_chosen," in *",$_add,"*' in script  # 去重
    assert "已忽略" in script  # 未检测到/无法识别
    assert "没有选中任何已检测到的终端，请重选" in script  # 选不中会重问
    assert 'while [ -z "$TERMINALS" ]' in script


def test_installer_embeds_no_credential() -> None:
    """没内置默认值时不内嵌密钥：token 由运行的人粘贴自己的。"""
    script = _script()

    assert "DEFAULT_TOKEN=" not in script
    assert "Bearer " in script  # 只在运行时按输入拼头，不是写死的 token
    # 只有一个 header 方言：Authorization → Bearer <token>
    assert "TOKEN_HEADER='Authorization'" in script
    assert 'TOKEN_HEADER="${OCTOP_TOKEN_HEADER:-Authorization}"' not in script


def test_default_token_is_an_optional_prefill() -> None:
    """``default_token`` 只是可选预填；环境变量仍然优先，没预填就现场问。"""
    script = _script(default_token="omcp_prefilled")

    assert "DEFAULT_TOKEN='omcp_prefilled'" in script
    assert "if [ -z \"$TOKEN\" ] && [ -n 'omcp_prefilled' ]; then" in script
    assert "用安装链接预填的值" in script
    # 预填只填 TOKEN；凭据仍是运行人自己的
    assert "OCTOP_MEMORY_TOKEN:-" in script


def test_known_values_only_prefill_prompts() -> None:
    """``terminals`` 只是预填；``agent_id`` 保留形参但**被忽略**（token 已绑定专家）。"""
    script = _script(agent_id="RY9RQC", terminals="kiro")

    assert "DEFAULT_TERMINALS='kiro'" in script
    assert "DEFAULT_AGENT" not in script
    assert "RY9RQC" not in script


def test_setup_script_shell_quotes_query_prefills() -> None:
    script = _script(terminals="cursor';id", project="/tmp/p';id")
    # Classic POSIX single-quote escape: ' → '"'"'
    assert "DEFAULT_TERMINALS='cursor'\"'\"';id'" in script
    assert "DEFAULT_PROJECT='/tmp/p'\"'\"';id'" in script
    assert "DEFAULT_TERMINALS='cursor';id'" not in script


def test_each_terminal_gets_its_own_hooks_directory() -> None:
    script = _script()

    assert "CC_DIR='~/.claude/hooks-events'" in script
    assert "KIRO_DIR='~/.kiro/hooks'" in script
    assert "DSH_DIR='~/.dsh/hooks'" in script
    assert "CODEX_DIR='~/.codex/hooks'" in script
    assert "CURSOR_DIR='~/.cursor/hooks'" in script
    assert HOOKS_DIRS == {
        "claude-code": "~/.claude/hooks-events",
        "kiro": "~/.kiro/hooks",
        "dsh": "~/.dsh/hooks",
        "codex": "~/.codex/hooks",
        "cursor": "~/.cursor/hooks",
    }


def test_claude_code_uses_two_command_hooks() -> None:
    """Claude Code：召回与上报都必须是 command hook。

    - ``UserPromptSubmit`` 上 `mcp_tool` 会被静默跳过（实测 2.1.263）；
    - ``Stop`` 用脚本，脚本自己后台脱离+延迟，等本轮落盘后再读 transcript
      （``SessionEnd`` 不可用：那里没有 MCP 客户端上下文）。
    """
    script = _script()

    assert (
        'search = {"type": "command", "command": hook_command(f"{hooks_dir}/claude-code/user-prompt-recall.mjs")}'
        in script
    )
    assert (
        'stop = {"type": "command", "command": hook_command(f"{hooks_dir}/claude-code/stop-capture.mjs")}'
        in script
    )
    assert "该事件不支持 ``mcp_tool``" in script
    assert "SessionEnd`` 不能用" in script
    # 简写形态：事件直接挂 handler 数组，不套 matcher 组那层
    assert 'return {"UserPromptSubmit": [search], "Stop": [stop]}' in script
    # 收尾提示按事件名列出两端角色（Cursor 的事件名不同，故不能只写 UserPromptSubmit/Stop）
    assert "用户提交时召回" in script and "memory_search" in script
    assert "回合结束时上报" in script and "memory_capture" in script
    assert "Cursor 的 beforeSubmitPrompt" in script


def test_claude_code_clears_the_legacy_session_end_hook() -> None:
    """早期版本挂过 SessionEnd（mcp_tool 在那里不可用、会持续报错）：重装时要清掉。"""
    script = _script()

    assert '_upsert_groups(st, "SessionEnd", [])' in script
    assert 'st["hooks"].pop("SessionEnd", None)' in script
    assert 'hooks["SessionEnd"]' not in script  # 不再定义


def test_previous_inline_hook_command_is_replaced_by_the_wrapper(tmp_path) -> None:
    """老配置里那串内联 node 命令（含 ``.mjs`` 与转义字符）重装时换成包装脚本，不留重复。"""
    legacy = (
        "/usr/bin/node /home/u/.claude/hooks-events/claude-code/stop-capture.mjs "
        '|| echo "octop-memory: hook 执行失败（node 路径不对或脚本报错）" >&2'
    )
    home, _ = _run_claude_code_installer(
        tmp_path, {}, {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": legacy}]}]}}
    )
    stops = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"][
        "Stop"
    ]
    assert len(stops) == 1  # 老命令被替换，没有并列
    assert stops[0]["type"] == "command"  # 换成简写形态（事件直接挂 handler）
    command = stops[0]["command"]
    assert command.endswith("claude-code/stop-capture.sh")
    assert ".mjs" not in command  # 配置里不再有那串长命令
    assert (home / ".claude/hooks-events/claude-code/stop-capture.sh").exists()


def test_foreign_hook_groups_are_kept_next_to_ours(tmp_path) -> None:
    """别人的 hook（matcher 组或裸 handler）都要原样留着，只动我们自己那两条。"""
    settings = {
        "hooks": {
            "Stop": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "git-ai checkpoint"}]},
                {"type": "command", "command": "/usr/local/bin/other-check"},
            ]
        }
    }
    home, _ = _run_claude_code_installer(tmp_path, {}, settings)
    stops = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"][
        "Stop"
    ]

    assert stops[0] == {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "git-ai checkpoint"}],
    }
    assert stops[1] == {"type": "command", "command": "/usr/local/bin/other-check"}
    assert stops[2]["command"].endswith("claude-code/stop-capture.sh")  # 我们的追加在最后


def test_hook_scripts_are_installed_for_every_hook_terminal() -> None:
    """四个 hook 宿主各装一份脚本 + config.json；DSH 走原生插件，不装 hook 脚本。"""
    script = _script()

    assert "SCRIPT_OK" not in script
    assert "CAPTURE_PROMPT" not in script  # 上报绝不走"让模型总结"的提示词
    assert "def do_claude_code():\n    # 两条 hook 都是 command 脚本" in script
    assert '_install_hooks(CC_DIR, "claude-code")' in script
    assert '_install_hooks(KIRO_DIR, "kiro")' in script
    assert '_install_hooks(CODEX_DIR, "codex")' in script
    assert '_install_hooks(CURSOR_DIR, "cursor")' in script
    # DSH 不再装 hooks（原生插件在进程内做召回/上报）
    assert '_install_hooks(DSH_DIR, "dsh")' not in script
    assert '"dsh": ("dsh/stop-capture.mjs"' not in script


def test_kiro_capture_is_always_a_command_hook() -> None:
    """Kiro：召回用提示词（Kiro 只支持 runCommand/askAgent）；上报始终用脚本提交整段 jsonl。"""
    script = _script()

    kiro = script[script.index("def do_kiro():") : script.index("_CODEX_HOOKS = ")]
    # 召回仍然是 agent 提示词（runCommand 的 stdout 不会被注入上下文）
    assert '"action": {"type": "agent", "prompt": SEARCH_PROMPT}' in kiro
    # 上报只有 command 一种形态，没有提示词兜底
    assert (
        '{"type": "command", "command": hook_command(f"{KIRO_DIR}/kiro/stop-capture.mjs")}' in kiro
    )
    assert '"type": "agent", "prompt": CAPTURE_PROMPT' not in kiro
    assert "提交整段 messages.jsonl" in kiro
    assert "Kiro 上报 hook" in script


def test_prompts_carry_the_role_instructions() -> None:
    script = _script()

    assert "先用 memory_search 检索" in script
    # 上报没有提示词：模型"总结会话"不算捕获原始会话
    assert "用 memory_capture 记录" not in script


def test_generated_script_embeds_each_hosts_scripts() -> None:
    """按宿主分别内嵌：共享传输模块 + 该宿主的入口脚本。"""
    script = _script()

    assert "OCTOP_FILES_CLAUDE_CODE=" in script
    assert "OCTOP_FILES_KIRO=" in script
    assert "OCTOP_FILES_CODEX=" in script and "OCTOP_FILES_CURSOR=" in script
    assert "OCTOP_FILES_DSH=" not in script  # 没有 dsh hook 脚本可装
    assert "OCTOP_FILES_PRESET=" not in script  # preset 方案已废弃
    assert "HOOK_FILES = {" in script and "OCTOP_FILES_" in script
    assert "lib/octop-memory-client.mjs" in script
    assert "claude-code/stop-capture.mjs" in script and "kiro/stop-capture.mjs" in script
    assert "codex/user-prompt-recall.mjs" in script and "codex/stop-capture.mjs" in script
    assert "cursor/user-prompt-recall.mjs" in script and "cursor/stop-capture.mjs" in script
    # 旧版的单文件变量不再使用
    assert "OCTOP_STOP_B64" not in script and "OCTOP_RECALL_B64" not in script


def test_dsh_native_plugin_manifest_is_vendored() -> None:
    """原生插件按 ``_DSH_NATIVE_FILES`` 逐字节内嵌（安装器不依赖插件仓/git）。"""
    script = _script()

    assert "OCTOP_FILES_NATIVE=" in script
    for name in _DSH_NATIVE_FILES:
        assert (_DSH_NATIVE_SRC / name).is_file(), f"缺少 vendored 插件文件：{name}"
    # 清单里的每个文件都被打进脚本（base64，脚本里看不到明文插件源码）
    assert _DSH_NATIVE_NAME == "octop-memory-native"
    assert "def _install_dsh_native_files():" in script
    assert "def _install_dsh_native():" in script


def test_dsh_native_install_registers_profile_and_patch_block() -> None:
    """DSH：写插件目录 → 登记 dependencies / dsh.profile.bundles → 同 id 覆盖 cordis.patch.yml。"""
    script = _script()

    assert "def _write_dsh_native_patch(profile_dir, config):" in script
    assert "def _replace_native_patch(text, block, row_id=None):" in script
    assert "def _register_dsh_native(profile_dir, bundle, profile):" in script
    assert 'dependencies[NATIVE_NAME] = "link:" + str(bundle)' in script
    assert "bundles.append(NATIVE_NAME)" in script
    # 配置块只覆盖 config，不再 insert（重复 id 会让 Loader 直接崩）
    assert "插件自己的 bundle patch 已经 insert 了同 id 的行" in script
    assert '"dsh", "plugin", "--profile", profile, "add", str(bundle)' in script
    assert '"pnpm", "add", str(bundle)' in script  # 源码 checkout 常没有 dsh 命令
    assert "没找到 DSH profile" in script
    assert "重启 DSH" in script


def test_dsh_native_config_block_uses_the_user_token_shape() -> None:
    """配置块里的连接信息 = 用户级 MCP token 形状（endpoint/token/tokenHeader，无 agentId）。"""
    script = _script()

    block = script[script.index("def _dsh_native_patch_block(config):") :]
    block = block[: block.index("def _is_patch_entry(")]
    assert 'for key in ("endpoint", "token", "tokenHeader"):' in block
    assert "userId" not in block and "agentId" not in block
    config = script[script.index("def _dsh_native_config():") : script.index("def _yaml_scalar(")]
    assert '"tokenHeader": TOKEN_HEADER' in config
    assert "userId" not in config


def test_dsh_install_cleans_the_legacy_hook_bridge_and_preset() -> None:
    """两套接法同时生效会双触发：升级路径先拆旧桥接 / preset bundle。"""
    script = _script()

    assert "def _remove_dsh_legacy_hooks():" in script
    assert '"dsh-memory-share", "octop-dsh-memory-share"' in script
    bridge_cleanup = script[
        script.index("def _remove_dsh_legacy_hooks():") : script.index("def _dsh_mcp_hint():")
    ]
    assert 'DSH_DIR / "octop-hooks.json"' in bridge_cleanup
    assert "shutil.rmtree(scripts)" in bridge_cleanup


def test_entries_use_authorization_bearer_only() -> None:
    """条目与 hooks 只用 ``Authorization: Bearer <MCP token>``（token 绑定专家）。"""
    script = _script()

    assert '"Authorization": f"Bearer {TOKEN}"' in script
    assert "X-Octop-Agent-Id" not in script
    assert "客户端 MCP 条目与 hooks：" in script
    assert "只用 Authorization: Bearer <MCP token>" in script


def test_node_is_resolved_to_an_absolute_path() -> None:
    """hook 由终端派生、常在非 login shell 里跑：node 必须解析成绝对路径。"""
    script = _script()

    assert 'NODE_BIN="${OCTOP_NODE:-}"' in script
    assert "command -v node" in script
    assert "$HOME/.nvm/versions/node" in script  # nvm 是最常见的坑
    assert "/opt/homebrew/bin/node" in script and "/usr/local/bin/node" in script
    assert "找不到 node 的绝对路径" in script  # 都找不到时明确告警
    assert 'export OCTOP_NODE="$NODE_BIN"' in script


def test_hook_commands_use_the_resolved_node_and_report_failures() -> None:
    script = _script()

    assert 'NODE = os.environ.get("OCTOP_NODE") or "node"' in script
    assert "def hook_command(script_path):" in script
    assert 'hook_command(f"{hooks_dir}/claude-code/stop-capture.mjs")' in script
    assert 'hook_command(f"{KIRO_DIR}/kiro/stop-capture.mjs")' in script
    # 非 0 退出不再静默：包装脚本把原因打到 stderr
    assert "failure = 'echo \"octop-memory: hook 执行失败" in script
    # 企业根在系统证书库里、不在 Node 自带库里：Node 22.15+ 才加 --use-system-ca
    assert "OCTOP_USE_SYSTEM_CA" in script
    assert "--use-system-ca" in script
    assert 'NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--use-system-ca"' in script


def test_hook_wrapper_follows_the_platform() -> None:
    """POSIX 安装器写 ``.sh``；Windows 安装器写 ``.cmd``（不需要 Git Bash）。"""
    script = _script()

    assert "def _sh_hook_command(mjs):" in script
    assert "def _cmd_hook_command(mjs):" in script
    assert "OCTOP_HOOK_WRAPPER=sh" in script  # sh 安装器显式指定
    assert 'wrapper = mjs.with_suffix(".cmd")' in script
    assert "if errorlevel 1 echo octop-memory: hook failed" in script


def test_installer_names_the_log_and_state_location() -> None:
    """日志与增量状态就落在终端自己的 hooks 目录（该目录不可写才退到临时目录）。"""
    script = _script()

    assert "日志/增量状态：" in script
    assert "{target}/octop-hook.log" in script
    assert "{target}/octop-transcript-state.json" in script
    assert "退到 {scratch}/octop-hooks" in script
    assert '"%TEMP%" if os.name == "nt" else "$TMPDIR"' in script  # POSIX / Windows


def test_mcp_entry_is_per_terminal_and_keeps_other_entries() -> None:
    script = _script()

    assert 'home / ".claude.json"' in script
    assert 'home / ".kiro" / "settings" / "mcp.json"' in script
    assert "def _octop_servers(servers):" in script  # 按 octop-memory* 认已有服务，不认具体名字
    assert "保持原样" in script
    assert "if not any(" in script


def test_legacy_mcp_tool_hooks_are_recognized_by_tool_not_by_server_name() -> None:
    """旧版 mcp_tool hook 的清理按工具名认：服务名可能是 local / prod 或改过名。"""
    script = _script()

    assert '_OUR_MCP_TOOLS = ("memory_search", "memory_capture")' in script
    assert 'handler.get("tool") in _OUR_MCP_TOOLS' in script
    assert 'handler.get("server") == NAME' not in script


def test_endpoint_self_check_is_warn_only() -> None:
    script = _script()

    assert "端点自检" in script
    assert "安装仍继续" in script
    # 自检与 hook 共用同一次探测；支持时先 export NODE_OPTIONS，再去 fetch
    assert 'if "$NODE_BIN" --use-system-ca -e' in script
    assert "export NODE_OPTIONS" in script
    assert "AbortSignal.timeout(8000)" in script
    # 自检也只发 Authorization Bearer + 专家头
    assert "Authorization: `Bearer ${cfg.token}`" in script


def test_server_name_follows_the_endpoint() -> None:
    assert "OCTOP_SERVER_NAME='octop-memory-local'" in _script()
    remote = _script(mcp_url="https://octop.example.com/mcp/")
    assert "OCTOP_SERVER_NAME='octop-memory'" in remote
    assert "octop-memory-local" not in remote


def test_generator_knows_only_the_supported_terminals() -> None:
    assert TERMINALS == ("claude-code", "kiro", "dsh", "codex", "cursor")


def test_generated_shell_and_embedded_python_are_valid() -> None:
    """脚本是 shell + 内嵌 python 拼出来的：两半都要能独立解析。"""
    ast.parse(_MERGE_PY)
    ast.parse(_UNINSTALL_PY)
    ast.parse(_SELECT_PY)
    assert "sys.exit(main())" in _SELECT_PY


def test_codex_and_cursor_are_detected_and_offered() -> None:
    """两个宿主都要进检测与菜单。"""
    script = _script()

    assert '[ -d "$HOME/.codex" ] || command -v codex' in script
    assert '[ -d "$HOME/.cursor" ] || command -v cursor' in script
    assert 'echo "  4) Codex' in script and 'echo "  5) Cursor' in script
    assert '"codex|Codex' in script and '"cursor|Cursor' in script
    assert "请重选（1-5，或 a=全部）" in script
    assert "4) _add=" in script and "5) _add=" in script
    assert '"codex": do_codex' in script and '"cursor": do_cursor' in script


def test_terminal_selection_is_an_interactive_checklist() -> None:
    """选终端是清单式：↑↓ 移动 · 空格 选择 · a 全选 · 回车 确认。"""
    script = _script()

    assert "OCTOP_SELECT" in script
    assert "↑/↓ 移动 · 空格 选择 · a 全选 · 回车 确认" in script
    assert 'if key == b"\\x1b":' in script  # 方向键 ESC [ A/B
    assert 'return {b"[A": "up", b"[B": "down"}' in script
    assert 'if key == b" ":' in script  # 空格切换
    assert "setraw(fd)" in script  # raw 模式读单键
    assert 'box = "◉" if chosen[index] else "◯"' in script  # 勾选状态可见
    # 一个都没选时回车不确认；无 tty / python3 不可用则回退数字输入
    assert "if not any(chosen):" in script
    assert "可多选：1,2 / 1 3 / 12 / a=全部" in script


def test_installer_mentions_the_windows_native_installer() -> None:
    """sh 版在 Windows（Git Bash/MSYS）上提示改用 PowerShell 原生安装器。"""
    script = _script()

    assert "MINGW*|MSYS*|CYGWIN*" in script
    assert '?os=windows" | iex' in script


def test_the_mcp_token_is_the_only_credential() -> None:
    """token 绑定专家：渲染出的脚本 / 配置里没有专家 ID 与专家头。"""
    scripts = (
        _script(),
        render_uninstall_script(),
        render_setup_ps1(mcp_url=_URL),
        render_uninstall_ps1(),
    )
    for script in scripts:
        for word in ("X-Octop-Agent-Id", "agentId", "OCTOP_AGENT", "专家 ID", "DEFAULT_AGENT"):
            assert word not in script, f"安装器还在用专家 ID：{word}"


def test_no_internal_only_vocabulary_leaks() -> None:
    """脱敏底线：安装器不能出现废弃的身份头或第二套凭据。"""
    scripts = (
        _script(),
        render_uninstall_script(),
        render_setup_ps1(mcp_url=_URL),
        render_uninstall_ps1(),
    )
    forbidden = (
        "OCTOP_USER_ID",
        "X-Octop-User-Id",
        "userId",
        "OCTOP_ENTRY_TOKEN",
        "OCTOP_DISABLE_OAUTH",
    )
    for script in scripts:
        for word in forbidden:
            assert word not in script, f"安装器泄漏了废弃概念：{word}"


# ---------------------------------------------------------------- 真跑生成的脚本


def test_generated_installer_actually_runs(tmp_path) -> None:
    """把生成的安装脚本真跑一遍（沙箱 HOME）。

    脚本是 shell + 内嵌 python 拼出来的：语法正确不等于能跑，拼装错误（变量改名、
    参数漏传）只有执行才会发现。
    """
    home, result = _run_terminals(
        tmp_path,
        "claude-code,kiro,dsh,codex,cursor",
        prepare=lambda home: _dsh_profile(home),
    )

    # 每个 hook 宿主只有自己的入口脚本 + 一份共享传输模块 + config.json
    assert (home / ".claude/hooks-events/claude-code/stop-capture.mjs").exists()
    assert (home / ".claude/hooks-events/claude-code/user-prompt-recall.mjs").exists()
    assert (home / ".kiro/hooks/kiro/stop-capture.mjs").exists()
    assert (home / ".codex/hooks/codex/stop-capture.mjs").exists()
    assert (home / ".codex/hooks/codex/user-prompt-recall.mjs").exists()
    assert (home / ".cursor/hooks/cursor/stop-capture.mjs").exists()
    assert (home / ".cursor/hooks/cursor/user-prompt-recall.mjs").exists()
    for hooks_dir in (
        ".claude/hooks-events",
        ".kiro/hooks",
        ".codex/hooks",
        ".cursor/hooks",
    ):
        assert (home / hooks_dir / "lib/octop-memory-client.mjs").exists()
        assert (home / hooks_dir / "config.json").exists()
    # DSH 不装 hooks：它拿原生插件
    assert not (home / ".dsh/hooks/dsh").exists()
    # 宿主之间不串
    assert not (home / ".claude/hooks-events/kiro").exists()
    assert not (home / ".kiro/hooks/claude-code").exists()
    # Codex / Cursor 的 hook 配置只引用包装脚本路径（长命令收在 .sh 里）
    assert ".codex/hooks/codex/stop-capture.sh" in (home / ".codex/config.toml").read_text(
        encoding="utf-8"
    )
    cursor_hooks = json.loads((home / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert (
        "cursor/hooks/cursor/user-prompt-recall.sh"
        in cursor_hooks["hooks"]["beforeSubmitPrompt"][0]["command"]
    )
    assert "cursor/hooks/cursor/stop-capture.sh" in cursor_hooks["hooks"]["stop"][0]["command"]
    # 每个宿主的包装脚本：可执行，内容是「绝对 node 路径 + .mjs + 失败兜底」
    for hooks_dir, host in (
        (".claude/hooks-events", "claude-code"),
        (".kiro/hooks", "kiro"),
        (".codex/hooks", "codex"),
        (".cursor/hooks", "cursor"),
    ):
        wrapper = home / hooks_dir / host / "stop-capture.sh"
        text = wrapper.read_text(encoding="utf-8")
        assert text.startswith("#!/bin/sh")
        assert f"{host}/stop-capture.mjs" in text
        assert "hook 执行失败" in text  # 非 0 退出不再静默
        assert os.access(wrapper, os.X_OK)
        if "node 使用系统证书库" in result.stdout:
            assert "--use-system-ca" in text
    # DSH：原生插件落盘 + profile 登记 + cordis.patch.yml 配置块
    bundle = home / ".dsh/bundles/octop-memory-native"
    for name in _DSH_NATIVE_FILES:
        assert (bundle / name).is_file()
    profile = home / ".dsh/profiles/web"
    package = json.loads((profile / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["octop-memory-native"] == f"link:{bundle}"
    assert package["dsh"]["profile"]["bundles"] == [
        "@deepseek-ai/dsh-base",
        "octop-memory-native",
    ]
    assert (profile / "node_modules/octop-memory-native").is_symlink()
    patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
    assert patch.count("- id: octop-memory-native") == 1  # 跑两遍也不重复
    assert "endpoint:" in patch and "tokenHeader:" in patch
    assert "userId" not in patch and "agentId" not in patch
    assert "不依赖 ~/.dsh/hooks 的 hook 桥接" in patch


_CODEX_EXISTING = """model = "gpt-5"

[[hooks.PreToolUse]]

[[hooks.PreToolUse.hooks]]
command = "/usr/local/bin/git-ai checkpoint codex"
type = "command"

[[hooks.Stop]]

[[hooks.Stop.hooks]]
command = "/usr/local/bin/git-ai checkpoint codex"
type = "command"

[hooks.state."CONFIG:stop:0:0"]
enabled = true
trusted_hash = "sha256:deadbeef"
"""


def _dsh_profile(home: Path, bundles: tuple[str, ...] = ("@deepseek-ai/dsh-base",)) -> Path:
    """沙箱里的 DSH profile（``~/.dsh/profiles/web/package.json``）。"""
    profile = home / ".dsh/profiles/web"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "package.json").write_text(
        json.dumps(
            {"name": "profile-web", "dsh": {"profile": {"bundles": list(bundles)}}}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return profile


def _run_terminals(tmp_path, terminals: str, prepare=None, extra_env=None, home_name="home"):
    """按给定终端跑两遍安装器（第二遍验证幂等），返回 (HOME, 最后一次输出)。"""
    home = tmp_path / home_name
    home.mkdir(parents=True, exist_ok=True)
    if prepare is not None:
        prepare(home)
    script = tmp_path / f"setup-{home_name}.sh"
    script.write_text(_script(), encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": terminals,
        "OCTOP_MEMORY_TOKEN": _TOKEN,
        **(extra_env or {}),
    }
    result = None
    for _ in range(2):
        result = subprocess.run(
            ["sh", str(script)], env=env, capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert result is not None
    return home, result


def _run_uninstall(tmp_path, home: Path, terminals: str, extra_env=None):
    script = tmp_path / "uninstall.sh"
    script.write_text(render_uninstall_script(), encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": terminals,
        **(extra_env or {}),
    }
    result = subprocess.run(
        ["sh", str(script)], env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_config_and_entry_carry_the_user_mcp_token(tmp_path) -> None:
    """config.json 与 MCP 条目只带「MCP 地址 + 用户 token」：没有 agentId、没有身份头。"""
    home, _ = _run_terminals(tmp_path, "claude-code")

    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config == {
        "url": _URL,
        "token": _TOKEN,
        "tokenHeader": "Authorization",
    }
    assert "agentId" not in config

    entry = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory-local"
    ]
    assert entry["url"] == _URL
    assert entry["headers"] == {"Authorization": f"Bearer {_TOKEN}"}


def test_entry_defaults_to_the_instance_mount(tmp_path) -> None:
    """没有声明公网地址时，条目与 hooks 都落在实例自己的挂载点。"""
    instance = "https://octop.example.com/mcp/memory/"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    script = tmp_path / "setup.sh"
    script.write_text(_script(mcp_url=instance), encoding="utf-8")
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": "shared-token",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    entry = next(iter(servers.values()))
    assert entry["url"] == instance
    assert entry["headers"] == {"Authorization": "Bearer shared-token"}


def test_declared_public_url_becomes_the_entry_address(tmp_path) -> None:
    """条目地址与 hooks 地址可以分开：条目走部署声明的公网地址，hooks 打实例挂载点。"""
    public = "https://octop-memory.example.com/mcp/memory/"
    direct = "https://octop.example.com/mcp/memory/"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    script = tmp_path / "setup.sh"
    script.write_text(_script(mcp_url=public, hook_url=direct), encoding="utf-8")
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": "shared-token",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    name, entry = next(iter(servers.items()))
    assert name == "octop-memory"
    assert entry["url"] == public
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config["url"] == direct and config["token"] == "shared-token"


def test_without_a_token_the_installer_still_demands_one(tmp_path) -> None:
    """无 tty + 没给环境变量 → 明确报错，不盲读 stdin。"""
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": "claude-code",
    }
    env.pop("OCTOP_MEMORY_TOKEN", None)
    result = subprocess.run(
        ["sh", str(script)], env=env, capture_output=True, text=True, timeout=180
    )

    assert result.returncode != 0
    assert "缺少 MCP token" in result.stderr
    assert "DEFAULT_TOKEN=" not in _script()  # 没预填值就不该有赋值


def test_codex_hooks_join_the_existing_config_without_clobbering_it(tmp_path) -> None:
    """~/.codex/config.toml 已有别人的 hook：只追加我们的，别的字段与信任状态原样保留。"""

    def prepare(home):
        (home / ".codex").mkdir(parents=True)
        config = home / ".codex/config.toml"
        (config).write_text(_CODEX_EXISTING.replace("CONFIG", str(config)), encoding="utf-8")

    home, _ = _run_terminals(tmp_path, "codex", prepare)
    cfg = tomllib.loads((home / ".codex/config.toml").read_text(encoding="utf-8"))
    hooks = cfg["hooks"]

    def commands(event):
        return [entry["command"] for group in hooks[event] for entry in group.get("hooks", [])]

    assert cfg["model"] == "gpt-5"  # 其它字段不动
    assert len(commands("PreToolUse")) == 1 and "git-ai" in commands("PreToolUse")[0]
    assert len(commands("Stop")) == 2  # 别人的 + 我们的（跑了两遍也不重复）
    assert any("codex/stop-capture.sh" in command for command in commands("Stop"))
    assert len(commands("UserPromptSubmit")) == 1
    assert any("codex/user-prompt-recall.sh" in command for command in commands("UserPromptSubmit"))
    assert list(hooks["state"]) == [f"{home}/.codex/config.toml:stop:0:0"]  # 信任状态保留


def test_cursor_hooks_join_the_existing_json_without_clobbering_it(tmp_path) -> None:
    """~/.cursor/hooks.json 其它事件（如 git-ai 的 postToolUse）原样保留。"""

    def prepare(home):
        (home / ".cursor").mkdir(parents=True)
        (home / ".cursor/hooks.json").write_text(
            json.dumps(
                {"hooks": {"postToolUse": [{"command": "git-ai cursor"}]}, "version": 1}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )

    home, _ = _run_terminals(tmp_path, "cursor", prepare)
    cfg = json.loads((home / ".cursor/hooks.json").read_text(encoding="utf-8"))

    assert cfg["version"] == 1
    assert cfg["hooks"]["postToolUse"] == [{"command": "git-ai cursor"}]
    assert len(cfg["hooks"]["beforeSubmitPrompt"]) == 1  # 幂等：跑两遍仍只有一条
    assert (
        "cursor/hooks/cursor/user-prompt-recall.sh"
        in cfg["hooks"]["beforeSubmitPrompt"][0]["command"]
    )
    assert len(cfg["hooks"]["stop"]) == 1
    assert "cursor/hooks/cursor/stop-capture.sh" in cfg["hooks"]["stop"][0]["command"]


# ---------------------------------------------------------------- DSH 原生插件


@posix_only
def test_dsh_native_install_is_idempotent(tmp_path) -> None:
    """DSH：插件目录、profile 登记、配置块都幂等（跑两遍结果一致）。"""

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        _dsh_profile(home)

    home, _ = _run_terminals(tmp_path, "dsh", prepare)
    bundle = home / ".dsh/bundles/octop-memory-native"
    profile = home / ".dsh/profiles/web"

    for name in _DSH_NATIVE_FILES:
        assert (bundle / name).is_file()
    # 插件是从 vendored 副本逐字节还原的
    for name in _DSH_NATIVE_FILES:
        assert (bundle / name).read_bytes() == (_DSH_NATIVE_SRC / name).read_bytes()

    package = json.loads((profile / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"] == {"octop-memory-native": f"link:{bundle}"}
    assert package["dsh"]["profile"]["bundles"] == ["@deepseek-ai/dsh-base", "octop-memory-native"]
    assert (profile / "node_modules/octop-memory-native").is_symlink()

    patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
    assert patch.count("- id: octop-memory-native") == 1
    assert "# <<< octop-memory-native <<<" in patch
    # 配置块 = 用户级 token 形状（无 userId / agentId）
    assert "    endpoint: 'http://127.0.0.1:8088/mcp/memory/'" in patch
    assert "    token: 'omcp_test_token'" in patch
    assert "    tokenHeader: 'Authorization'" in patch
    assert "userId" not in patch and "agentId" not in patch  # token 绑定专家


@posix_only
def test_dsh_native_install_keeps_other_patch_entries(tmp_path) -> None:
    """profile 的 cordis.patch.yml 里别人的条目 / 注释逐字保留，我们只追加自己的块。"""
    existing = (
        "# 用户自己的 patch\n"
        "- insert:\n"
        "    - id: some-other-plugin\n"
        "      name: 'some-other-plugin'\n"
    )

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        profile = _dsh_profile(home)
        (profile / "cordis.patch.yml").write_text(existing, encoding="utf-8")

    home, _ = _run_terminals(tmp_path, "dsh", prepare)
    patch = (home / ".dsh/profiles/web/cordis.patch.yml").read_text(encoding="utf-8")

    assert patch.startswith(existing)
    assert patch.count("- id: some-other-plugin") == 1
    assert patch.count("- id: octop-memory-native") == 1
    # 覆盖前备份原文件
    assert (home / ".dsh/profiles/web/cordis.patch.yml.octop.bak").read_text(
        encoding="utf-8"
    ) == existing


@posix_only
def test_dsh_install_removes_the_legacy_bridge_and_preset(tmp_path) -> None:
    """从 hooks 方案升级：旧桥接 / preset bundle / 脚本目录都拆掉，避免双触发。"""

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        shim = {"name": "profile-web", "dsh": {"profile": {"bundles": ["dsh-memory-share"]}}}
        profile = home / ".dsh/profiles/web"
        profile.mkdir(parents=True)
        (profile / "package.json").write_text(json.dumps(shim, indent=2) + "\n", encoding="utf-8")
        preset = home / ".dsh/bundles/dsh-memory-share"
        preset.mkdir(parents=True)
        (preset / "package.json").write_text("{}", encoding="utf-8")
        (home / ".dsh/hooks").mkdir(parents=True)
        (home / ".dsh/hooks/octop-hooks.json").write_text("{}", encoding="utf-8")
        (home / ".dsh/hooks/dsh").mkdir()
        (home / ".dsh/hooks/dsh/stop-capture.mjs").write_text("//", encoding="utf-8")

    home, result = _run_terminals(tmp_path, "dsh", prepare)
    profile = home / ".dsh/profiles/web"

    assert not (home / ".dsh/bundles/dsh-memory-share").exists()
    assert not (home / ".dsh/hooks/octop-hooks.json").exists()
    assert not (home / ".dsh/hooks/dsh").exists()
    assert json.loads((profile / "package.json").read_text(encoding="utf-8"))["dsh"]["profile"][
        "bundles"
    ] == ["octop-memory-native"]


@posix_only
def test_dsh_prefers_the_cli_and_still_registers_the_profile(tmp_path) -> None:
    """有 dsh CLI 时优先用它装依赖；登记与配置块仍然由安装器写好（幂等）。"""

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        _dsh_profile(home)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    shim = fake_bin / "dsh"
    shim.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$0.args"\n', encoding="utf-8")
    shim.chmod(0o755)

    home, _ = _run_terminals(
        tmp_path,
        "dsh",
        prepare,
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )
    profile = home / ".dsh/profiles/web"

    calls = (fake_bin / "dsh.args").read_text(encoding="utf-8")
    assert "plugin" in calls and "--profile" in calls and "web" in calls
    assert str(home / ".dsh/bundles/octop-memory-native") in calls
    assert not (fake_bin / "pnpm.args").exists()  # 有 dsh 就不必自己调 pnpm
    assert (
        "octop-memory-native"
        in json.loads((profile / "package.json").read_text(encoding="utf-8"))["dsh"]["profile"][
            "bundles"
        ]
    )


@posix_only
def test_dsh_uninstall_removes_the_native_plugin(tmp_path) -> None:
    """卸载：插件目录 / profile 登记 / node_modules 条目 / 配置块都清掉。"""

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        _dsh_profile(home)

    home, _ = _run_terminals(tmp_path, "dsh", prepare)
    profile = home / ".dsh/profiles/web"
    assert (home / ".dsh/bundles/octop-memory-native").exists()

    _run_uninstall(tmp_path, home, "dsh")

    assert not (home / ".dsh/bundles/octop-memory-native").exists()
    assert not (profile / "node_modules/octop-memory-native").exists()
    package = json.loads((profile / "package.json").read_text(encoding="utf-8"))
    assert "octop-memory-native" not in package["dependencies"]
    assert package["dsh"]["profile"]["bundles"] == ["@deepseek-ai/dsh-base"]  # 别人的不动
    # 只含我们配置块的 patch 文件被删掉
    assert not (profile / "cordis.patch.yml").exists()


def test_dsh_is_skipped_in_project_mode(tmp_path) -> None:
    """DSH 没有项目级配置：项目模式跳过（不算失败，也不写 DSH 文件）。"""

    def prepare(home):
        (home / ".dsh").mkdir(parents=True)
        _dsh_profile(home)

    project = tmp_path / "proj"
    project.mkdir()
    home, result = _run_terminals(
        tmp_path,
        "claude-code,dsh",
        prepare,
        extra_env={"OCTOP_PROJECT_DIR": str(project)},
    )

    assert "项目模式跳过 DSH" in result.stdout
    assert not (home / ".dsh/bundles/octop-memory-native").exists()
    assert not (home / ".dsh/profiles/web/cordis.patch.yml").exists()
    assert (home / ".claude/hooks-events/config.json").exists()  # 其它终端照装


# ---------------------------------------------------------------- 项目级安装


def test_project_install_registers_into_the_project_and_keeps_scripts_in_home(tmp_path) -> None:
    """项目模式：项目里只写注册；hook 脚本与含 token 的 config.json 留在用户目录。"""

    def prepare(home):
        (home / ".claude").mkdir(parents=True)
        (home / ".kiro").mkdir(parents=True)
        (home / ".codex").mkdir(parents=True)
        (home / ".cursor").mkdir(parents=True)

    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    home, result = _run_terminals(
        tmp_path,
        "claude-code,kiro,codex,cursor",
        prepare,
        extra_env={"OCTOP_PROJECT_DIR": str(project)},
    )

    assert f"安装范围：项目级 → {project.resolve()}" in result.stdout
    # 注册落在项目里
    settings = json.loads((project / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert "UserPromptSubmit" in settings["hooks"] and "Stop" in settings["hooks"]
    assert "codex/stop-capture.sh" in (project / ".codex/config.toml").read_text(encoding="utf-8")
    cursor = json.loads((project / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert "beforeSubmitPrompt" in cursor["hooks"] and "stop" in cursor["hooks"]
    # Kiro 的 hooks 是命令（无凭据）→ 写进项目
    assert (project / ".kiro/hooks/memory-save-on-stop.json").exists()
    # 脚本与凭据留在 HOME
    for hooks_dir in (".claude/hooks-events", ".kiro/hooks", ".codex/hooks", ".cursor/hooks"):
        assert (home / hooks_dir / "config.json").exists()
    assert (home / ".claude/hooks-events/claude-code/stop-capture.mjs").exists()
    # 项目里没有任何凭据
    for path in project.rglob("*"):
        if path.is_file():
            assert _TOKEN not in path.read_text(encoding="utf-8"), path


def test_project_mode_skips_the_kiro_mcp_entry(tmp_path) -> None:
    """Kiro 的 MCP 条目自带凭据、会随 git 提交：项目模式跳过并提示。"""

    def prepare(home):
        (home / ".kiro").mkdir(parents=True)

    project = tmp_path / "proj"
    project.mkdir()
    home, result = _run_terminals(
        tmp_path, "kiro", prepare, extra_env={"OCTOP_PROJECT_DIR": str(project)}
    )

    assert "项目模式跳过" in result.stdout
    assert not (project / ".kiro/settings/mcp.json").exists()
    # hooks（只有命令）照旧进项目，脚本留在 HOME
    assert (project / ".kiro/hooks/memory-recall-on-start.json").exists()
    assert (home / ".kiro/hooks/config.json").exists()


def test_claude_code_project_mode_uses_the_local_scope(tmp_path) -> None:
    """Claude Code 的 MCP 走 ``~/.claude.json`` 的 local scope（按项目路径存，不进仓库）。"""

    def prepare(home):
        (home / ".claude").mkdir(parents=True)

    project = tmp_path / "proj"
    project.mkdir()
    home, _ = _run_terminals(
        tmp_path, "claude-code", prepare, extra_env={"OCTOP_PROJECT_DIR": str(project)}
    )

    projects = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["projects"]
    key = os.path.realpath(str(project))
    assert key in projects
    entry = projects[key]["mcpServers"]["octop-memory-local"]
    assert entry["headers"]["Authorization"] == f"Bearer {_TOKEN}"
    assert not (project / ".mcp.json").exists()  # 不写仓库里的 .mcp.json


def test_project_env_wins_over_the_query_prefill(tmp_path) -> None:
    """``project=`` 只是交互式预填：非交互只认 OCTOP_PROJECT_DIR，显式置空 = 全局。"""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    project = tmp_path / "prefilled"
    project.mkdir()
    target = tmp_path / "from-env"
    target.mkdir()
    script = tmp_path / "setup.sh"
    script.write_text(_script(project=str(project)), encoding="utf-8")
    base_env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": "claude-code",
        "OCTOP_MEMORY_TOKEN": _TOKEN,
    }

    # 环境变量优先：装到 from-env，而不是 query 预填的 prefilled
    result = subprocess.run(
        ["sh", str(script)],
        env={**base_env, "OCTOP_PROJECT_DIR": str(target)},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / ".claude/settings.local.json").exists()
    assert not (project / ".claude").exists()

    # 显式置空 = 强制全局
    home2 = tmp_path / "home2"
    (home2 / ".claude").mkdir(parents=True)
    result = subprocess.run(
        ["sh", str(script)],
        env={**base_env, "HOME": str(home2), "OCTOP_PROJECT_DIR": ""},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "安装范围：项目级" not in result.stdout
    assert (home2 / ".claude/settings.json").exists()  # 全局安装


def test_project_uninstall_only_clears_the_registrations(tmp_path) -> None:
    """项目级卸载只清项目的注册，用户目录里的 hook 脚本保留给全局卸载。"""

    def prepare(home):
        (home / ".claude").mkdir(parents=True)
        (home / ".codex").mkdir(parents=True)

    project = tmp_path / "proj"
    project.mkdir()
    home, _ = _run_terminals(
        tmp_path,
        "claude-code,codex",
        prepare,
        extra_env={"OCTOP_PROJECT_DIR": str(project)},
    )
    assert (project / ".claude/settings.local.json").exists()

    _run_uninstall(tmp_path, home, "claude-code,codex", {"OCTOP_PROJECT_DIR": str(project)})

    settings = json.loads((project / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert settings["hooks"] == {}
    assert "[[hooks." not in (project / ".codex/config.toml").read_text(encoding="utf-8")
    # 用户目录里的脚本与 config.json 还在
    assert (home / ".claude/hooks-events/claude-code/stop-capture.mjs").exists()
    assert (home / ".claude/hooks-events/config.json").exists()


# ---------------------------------------------------------------- 卸载


def test_uninstall_script_mentions_cursor_and_needs_no_token() -> None:
    script = render_uninstall_script()
    assert script.startswith("#!/bin/sh")
    assert "octop memory 卸载" in script
    assert "OCTOP_TERMINALS" in script
    assert "Cursor" in script
    assert "OCTOP_MEMORY_TOKEN" not in script
    assert "undo_cursor" in script or "CURSOR_DIR" in script
    # 卸载也支持项目级范围
    assert "OCTOP_PROJECT_DIR" in script
    assert "卸载范围" in script


def test_uninstall_script_shell_quotes_terminals_and_project_query() -> None:
    """HTTP ``terminals`` / ``project`` must not break out of the shell assignment."""
    script = render_uninstall_script(
        terminals="cursor'; curl evil.example", project="/p'; curl evil.example"
    )
    assert "DEFAULT_TERMINALS='cursor'\"'\"'; curl evil.example'" in script
    assert "DEFAULT_PROJECT='/p'\"'\"'; curl evil.example'" in script
    assert "DEFAULT_TERMINALS='cursor'; curl evil.example'" not in script


def test_cursor_uninstall_removes_hooks_keeps_others(tmp_path) -> None:
    """setup → uninstall：octop hooks/目录清掉，别人的 hook 与无关 MCP 保留。"""

    def prepare(home):
        (home / ".cursor").mkdir(parents=True)
        (home / ".cursor/hooks.json").write_text(
            json.dumps(
                {"hooks": {"postToolUse": [{"command": "git-ai cursor"}]}, "version": 1},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (home / ".cursor/mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "octop-memory": {"url": "https://example/mcp"},
                        "other": {"url": "https://other"},
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    home, _ = _run_terminals(tmp_path, "cursor", prepare)
    assert (home / ".cursor/hooks/cursor/stop-capture.mjs").exists()

    _run_uninstall(tmp_path, home, "cursor")

    cfg = json.loads((home / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert cfg["hooks"]["postToolUse"] == [{"command": "git-ai cursor"}]
    assert "beforeSubmitPrompt" not in cfg["hooks"]
    assert "stop" not in cfg["hooks"]
    assert not (home / ".cursor/hooks").exists()

    mcp = json.loads((home / ".cursor/mcp.json").read_text(encoding="utf-8"))
    assert "octop-memory" not in mcp["mcpServers"]
    assert mcp["mcpServers"]["other"]["url"] == "https://other"


def _run_claude_code_installer(tmp_path, claude_json: dict, settings: dict | None = None):
    """只装 Claude Code：沙箱 HOME + 预置的 .claude.json / settings.json。"""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps(claude_json, indent=2) + "\n", encoding="utf-8")
    if settings is not None:
        (home / ".claude/settings.json").write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": _TOKEN,
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return home, result


def test_mcp_entry_is_added_when_no_octop_server_exists(tmp_path) -> None:
    home, _ = _run_claude_code_installer(
        tmp_path, {"mcpServers": {"other-mcp": {"type": "http", "url": "http://other/"}}}
    )
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "octop-memory-local" in servers  # 全新安装才新建条目
    assert "other-mcp" in servers  # 别人的条目原样保留


def test_mcp_entry_reuses_an_existing_octop_entry_with_the_same_endpoint(tmp_path) -> None:
    """已有同一个端点的 octop 服务（名字可能是 prod / 自定义）→ 复用，不新增条目。"""
    home, result = _run_claude_code_installer(
        tmp_path,
        {"mcpServers": {"octop-memory-prod": {"type": "http", "url": _URL}}},
    )
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert list(servers) == ["octop-memory-prod"]
    assert "复用" in result.stdout


def test_mcp_entry_does_not_add_a_duplicate_for_a_different_octop_endpoint(tmp_path) -> None:
    """已有别的 octop 端点时保持原样：不按服务名硬塞第二个 octop 服务。"""
    home, result = _run_claude_code_installer(
        tmp_path,
        {
            "mcpServers": {
                "octop-memory-other": {"type": "http", "url": "https://other.example/mcp/"}
            }
        },
    )
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert list(servers) == ["octop-memory-other"]
    assert "保持原样" in result.stdout


def test_legacy_mcp_tool_hook_under_another_server_name_is_replaced(tmp_path) -> None:
    """旧版 mcp_tool hook 的服务名可能是 octop-memory-prod：按工具名清掉它。"""
    legacy = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "mcp_tool",
                            "server": "octop-memory-prod",
                            "tool": "memory_search",
                            "input": {"query": "${prompt}"},
                        }
                    ]
                }
            ]
        }
    }
    home, _ = _run_claude_code_installer(tmp_path, {"mcpServers": {}}, settings=legacy)
    entries = json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"][
        "UserPromptSubmit"
    ]
    assert len(entries) == 1  # 旧 mcp_tool 那条被替换，只剩我们新写的
    assert entries[0]["type"] == "command"  # 简写形态：事件直接挂 handler
    assert not any(entry.get("type") == "mcp_tool" for entry in entries)


# ---------------------------------------------------------------- Windows（PowerShell）


def test_powershell_installer_renders_a_native_installer() -> None:
    """``?os=windows`` 是原生 PowerShell 安装器：不需要 Git Bash，也不写 .cmd 包装链。"""
    # agent_id 形参保留但被忽略
    script = render_setup_ps1(mcp_url=_URL, agent_id="AGT1", terminals="cursor")

    assert "$PSVersionTable.PSVersion.Major" in script
    assert "Read-Host" in script and "Read-Secret" in script  # 不回显
    assert "Join-Path $HOME '.claude\\hooks-events'" in script
    assert "Join-Path $HOME '.cursor\\hooks'" in script
    assert "$DEFAULT_TERMINALS = 'cursor'" in script
    # token 绑定专家：没有专家 ID 可填，agent_id 形参被忽略
    assert "DEFAULT_AGENT" not in script and "专家 ID" not in script
    assert "OCTOP_AGENT" not in script
    # 同一个 Python 合并程序 + .cmd 包装脚本
    assert "OCTOP_HOOK_WRAPPER = 'cmd'" in script
    assert "def _cmd_hook_command(mjs):" in script
    # 五个终端与 POSIX 槽位一致
    assert "{ 1 = 'claude-code'; 2 = 'kiro'; 3 = 'dsh'; 4 = 'codex'; 5 = 'cursor' }" in script
    assert "1-5" in script
    # 用户级 token 的提示与没有 userId
    assert "MCP token（omcp_…，在 Octop 的 /api/memory-mcp/tokens 创建；不回显）" in script
    assert "OCTOP_USER_ID" not in script and "X-Octop-User-Id" not in script
    # 项目级范围
    assert "OCTOP_PROJECT_DIR" in script and "安装范围" in script
    # 环境块长度：配置走临时 JSON
    assert "OCTOP_ENV_FILE" in script
    assert "GetTempFileName" in script
    # 没有留下未替换的占位符
    assert "__URL_LITERAL__" not in script and "__MERGE_PY__" not in script


def test_powershell_uninstaller_renders() -> None:
    script = render_uninstall_ps1(terminals="cursor", project="/tmp/proj")

    assert "$PSVersionTable.PSVersion.Major" in script
    assert "$DEFAULT_TERMINALS = 'cursor'" in script
    assert "$DEFAULT_PROJECT = '/tmp/proj'" in script
    assert "undo_cursor" in script
    assert "卸载范围" in script
    assert "OCTOP_ENV_FILE" in script
    assert "__UNINSTALL_PY__" not in script and "__DEFAULT_PROJECT_LITERAL__" not in script


def test_powershell_quoting_escapes_single_quotes() -> None:
    """PowerShell 单引号串里 ``'`` 要写成 ``''``（不然后面的语句被吃掉）。"""
    script = render_setup_ps1(
        mcp_url=_URL,
        agent_id="a'b",  # 形参保留但忽略：不应出现在脚本里
        terminals="cursor'x",
        project="/tmp/p'x",
    )

    assert "$DEFAULT_TERMINALS = 'cursor''x'" in script
    assert "$DEFAULT_PROJECT = '/tmp/p''x'" in script
    assert "DEFAULT_AGENT" not in script


def test_powershell_project_scope_honours_an_explicitly_empty_env() -> None:
    """与 sh 安装器一致：显式设为空串 = 强制全局，不再交互提问。"""
    script = render_setup_ps1(mcp_url=_URL)
    assert "$projectSet = $null -ne $env:OCTOP_PROJECT_DIR" in script
    assert "if (-not $projectSet -and $interactive)" in script
    uninstall = render_uninstall_ps1()
    assert "$projectSet = $null -ne $env:OCTOP_PROJECT_DIR" in uninstall
    assert "if (-not $projectSet -and $interactive)" in uninstall


def test_powershell_installer_embeds_every_host_and_the_native_plugin() -> None:
    script = render_setup_ps1(mcp_url=_URL)

    assert "OCTOP_FILES_CLAUDE_CODE = " in script
    assert "OCTOP_FILES_KIRO = " in script
    assert "OCTOP_FILES_CODEX = " in script and "OCTOP_FILES_CURSOR = " in script
    assert "OCTOP_FILES_NATIVE = " in script
    assert "OCTOP_FILES_DSH = " not in script
    assert "OCTOP_FILES_PRESET = " not in script


def test_vendored_plugin_files_exist_for_every_entry_in_the_manifest() -> None:
    """清单与 vendored 目录必须一致（升级插件时同步两处）。"""
    missing = [name for name in _DSH_NATIVE_FILES if not (_DSH_NATIVE_SRC / name).is_file()]
    assert missing == []
    package = json.loads((_DSH_NATIVE_SRC / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == _DSH_NATIVE_NAME
