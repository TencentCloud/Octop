"""Hook scripts are data files, but their layout and write locations are a contract."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_HOOKS = Path(__file__).parents[3] / "src" / "octop" / "infra" / "agents" / "hook_scripts"
_LIB = _HOOKS / "lib" / "octop-memory-client.mjs"
_NODE = shutil.which("node") or shutil.which("nodejs")
node_required = pytest.mark.skipif(_NODE is None, reason="需要 node 才能执行 .mjs 断言")
_HOSTS = {
    "claude-code": ("stop-capture.mjs", "user-prompt-recall.mjs"),
    "kiro": ("stop-capture.mjs",),
    "dsh": ("stop-capture.mjs", "user-prompt-recall.mjs", "memory-target.mjs"),
    "codex": ("stop-capture.mjs", "user-prompt-recall.mjs"),
    "cursor": ("stop-capture.mjs", "user-prompt-recall.mjs"),
}


def test_every_host_has_its_own_entry_scripts() -> None:
    """每个宿主一个入口脚本：一个宿主的改动不会碰到别人。"""
    for host, names in _HOSTS.items():
        for name in names:
            assert (_HOOKS / host / name).exists(), f"{host}/{name} 缺失"


def test_entries_do_not_detect_the_host_at_runtime() -> None:
    """宿主差异体现在安装时选的脚本里，脚本内部不再做宿主嗅探。"""
    for host, names in _HOSTS.items():
        if not (_HOOKS / host).exists():
            continue
        for name in names:
            path = _HOOKS / host / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for sniff in ("findDshSessionFile", "kiroRoot", "dshRoot", "sourceOverride"):
                assert sniff not in text, f"{host}/{name} 仍在运行时探测宿主（{sniff}）"


def test_transport_module_is_host_agnostic() -> None:
    """共享模块只做传输（配置/鉴权/偏移/日志/压缩），不认识任何宿主。"""
    text = _LIB.read_text(encoding="utf-8")

    assert "export async function capture" in text
    assert "export async function callTool" in text
    assert "decompressZstdContainer" in text
    # 认证是用户级 token：token 走 Authorization: Bearer，专家身份只走 X-Octop-Agent-Id，
    # 不再有 userId / X-Octop-User-Id 这套旧标识。
    assert '"X-Octop-Agent-Id"' in text
    assert "`Bearer ${config.token}`" in text
    assert "X-Octop-User-Id" not in text
    assert "OCTOP_USER_ID" not in text
    assert "userId" not in text
    for host_word in ("claude-code", "kiro", "dsh", "codex", "cursor", "transcript_path"):
        assert host_word not in text, f"共享模块不应出现宿主细节：{host_word}"


def test_no_hook_sends_a_user_identity() -> None:
    """用户身份由 token 表达，任何宿主都不再读/发 X-Octop-User-Id。"""
    for path in sorted(_HOOKS.rglob("*.mjs")):
        text = path.read_text(encoding="utf-8")
        for stale in ("X-Octop-User-Id", "OCTOP_USER_ID", "userId"):
            assert stale not in text, f"{path.relative_to(_HOOKS)} 仍在用旧用户标识（{stale}）"


def test_every_entry_uses_the_shared_configured_guard() -> None:
    """「有没有配好」只由共享模块的 isConfigured() 判，入口脚本别各写一套。"""
    assert "export function isConfigured" in _LIB.read_text(encoding="utf-8")
    for host, names in _HOSTS.items():
        for name in names:
            text = (_HOOKS / host / name).read_text(encoding="utf-8")
            if "not configured" not in text:
                continue
            assert "isConfigured(config)" in text, f"{host}/{name} 没用共享守卫"
            assert "!config.token" not in text, f"{host}/{name} 自己拼了 token 判断"


def test_scratch_dir_prefers_the_hook_directory() -> None:
    """日志/增量状态默认写 hooks 目录，不可写才退到临时目录。"""
    text = _LIB.read_text(encoding="utf-8")
    assert "for (const dir of [HOOK_DIR," in text
    assert "${scratchDir}/octop-hook.log" in text


def test_falling_back_to_tmp_is_announced() -> None:
    """DSH 的 workspace-write 沙盒里 $HOME 只读，回退必须可见而不是静默。"""
    text = _LIB.read_text(encoding="utf-8")
    assert "if (scratchDir !== HOOK_DIR)" in text
    assert "不可写，日志与增量状态改写到" in text


def test_claude_code_capture_defers_to_a_detached_worker() -> None:
    """Stop 时本轮还没落盘：后台脱离 + 轮询到「最后一条 user 之后有 assistant」。"""
    text = (_HOOKS / "claude-code" / "stop-capture.mjs").read_text(encoding="utf-8")

    assert "OCTOP_CAPTURE_DELAY_MS" in text and "const IS_WORKER" in text
    assert 'spawn(process.execPath, [fileURLToPath(import.meta.url), "--worker"]' in text
    assert "detached: true" in text and "worker.unref()" in text
    assert "OCTOP_HOOK_PAYLOAD_B64" in text
    assert "turnLanded" in text
    assert '"cc:"' in text or 'sessionPrefix: "cc:"' in text


def test_kiro_and_dsh_capture_are_self_contained() -> None:
    """Kiro 只认 messages.jsonl；DSH 只认 session*.jsonl.zstd 且自带解压。"""
    kiro = (_HOOKS / "kiro" / "stop-capture.mjs").read_text(encoding="utf-8")
    dsh = (_HOOKS / "dsh" / "stop-capture.mjs").read_text(encoding="utf-8")

    assert "messages.jsonl" in kiro and '"kiro:"' in kiro
    assert "/.kiro/sessions" in kiro
    assert "decompressZstdContainer" in dsh and '"dsh:"' in dsh
    assert "/.dsh/sessions" in dsh and "session.*\\.jsonl\\.zstd" in dsh


def test_dsh_recall_answers_in_the_bridge_dialect() -> None:
    """DSH 桥只从 hookSpecificOutput.additionalContext 取上下文：纯 stdout 会被丢弃。"""
    text = (_HOOKS / "dsh" / "user-prompt-recall.mjs").read_text(encoding="utf-8")

    assert "hookSpecificOutput" in text
    assert 'hookEventName: "UserPromptSubmit"' in text
    assert "additionalContext" in text


def test_dsh_capture_probes_the_endpoint_before_sending_turns() -> None:
    """能分开角色就按轮上报（content + assistant），否则退回服务端解析的 transcript 模式。"""
    text = (_HOOKS / "dsh" / "stop-capture.mjs").read_text(encoding="utf-8")

    assert "supportsAssistant" in text and "captureTurns" in text
    assert "OCTOP_CAPTURE_MODE" in text and "OCTOP_CAPTURE_MAX_TURNS" in text
    assert 'kind && kind !== "user"' in text  # 插件注入/系统提醒不算用户提问
    assert 'source: "dsh"' in text


# ── 用户级 token 的真实行为（直接 import 共享模块跑一遍，而不是只读文本） ──────────

_PROBE = """
import { authHeaders, isConfigured, loadConfig } from __LIB__;
process.env.OCTOP_MEMORY_MCP_URL = "https://memory.example.com/mcp/memory/";
process.env.OCTOP_MEMORY_MCP_TOKEN = "omcp_env_token";
process.env.OCTOP_AGENT_ID = "expert-1";
process.env.OCTOP_USER_ID = "should-be-ignored";
const config = loadConfig();
const withToken = (token, tokenHeader) => ({ ...config, token, tokenHeader });
process.stdout.write(JSON.stringify({
  config,
  bearer: authHeaders(withToken("omcp_abc123", "Authorization")),
  custom: authHeaders(withToken("shared-token", "X-Octop-Memory-Token")),
  configured: isConfigured(config),
  tokenlessConfigured: isConfigured(withToken("", "Authorization")),
}));
"""


@pytest.fixture(scope="module")
def probe() -> dict[str, object]:
    """在一个 node 进程里跑 loadConfig + authHeaders，返回真实结果。"""
    script = _PROBE.replace("__LIB__", json.dumps(_LIB.as_uri()))
    result = subprocess.run(
        [_NODE or "node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


@node_required
def test_config_no_longer_reads_a_user_id(probe: dict[str, object]) -> None:
    """config 里没有 userId：OCTOP_USER_ID / config.json 的 userId 一律不再读。"""
    config = probe["config"]

    assert isinstance(config, dict)
    assert "userId" not in config
    assert config["endpoint"] == "https://memory.example.com/mcp/memory/"
    assert config["agentId"] == "expert-1"


@node_required
def test_auth_headers_send_a_user_token_and_the_agent_id(probe: dict[str, object]) -> None:
    """Authorization 带 Bearer <token>，专家身份走 X-Octop-Agent-Id，没有用户头。"""
    headers = probe["bearer"]

    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer omcp_abc123"
    assert headers["X-Octop-Agent-Id"] == "expert-1"
    assert not [name for name in headers if name.lower() == "x-octop-user-id"]


@node_required
def test_a_custom_token_header_is_written_verbatim(probe: dict[str, object]) -> None:
    """tokenHeader 可改名：非 Authorization 时原样写该头（不加 Bearer 前缀）。"""
    headers = probe["custom"]

    assert isinstance(headers, dict)
    assert headers["X-Octop-Memory-Token"] == "shared-token"
    assert "Authorization" not in headers


@node_required
def test_a_tokenless_config_is_not_configured(probe: dict[str, object]) -> None:
    """没配 token 时 isConfigured 为 false：入口脚本在本轮直接跳过，不会发请求。"""
    assert probe["configured"] is True
    assert probe["tokenlessConfigured"] is False
