import opencodeIcon from "../../../assets/acp/opencode.svg";
import codebuddyIcon from "../../../assets/acp/codebuddy.png";
import anthropicIcon from "../../../assets/providers/anthropic.png";
import openaiIcon from "../../../assets/providers/openai.png";
import moonshotIcon from "../../../assets/acp/moonshot.png";
import cursorIcon from "../../../assets/acp/cursor.png";
import piIcon from "../../../assets/acp/pi.png";
import qwenIcon from "../../../assets/acp/qwen.svg";
import customRunnerIcon from "../../../assets/providers/custom-provider.svg";

/** Built-in ACP runner ids (order preserved in the grid). */
export const BUILTIN_RUNNER_ORDER = [
  "opencode",
  "codebuddy",
  "claude_code",
  "codex",
  "kimi_code",
  "cursor_cli",
  "pi",
  "qwen_code",
] as const;

export type BuiltinRunnerKey = (typeof BUILTIN_RUNNER_ORDER)[number];

export function isBuiltinRunner(key: string): key is BuiltinRunnerKey {
  return (BUILTIN_RUNNER_ORDER as readonly string[]).includes(key);
}

export const RUNNER_ICONS: Record<string, string> = {
  opencode: opencodeIcon,
  codebuddy: codebuddyIcon,
  claude_code: anthropicIcon,
  codex: openaiIcon,
  kimi_code: moonshotIcon,
  cursor_cli: cursorIcon,
  pi: piIcon,
  qwen_code: qwenIcon,
};

export const RUNNER_LABEL_KEYS: Record<string, string> = {
  opencode: "acp.runner_opencode",
  codebuddy: "acp.runner_codebuddy",
  claude_code: "acp.runner_claude_code",
  codex: "acp.runner_codex",
  kimi_code: "acp.runner_kimi_code",
  cursor_cli: "acp.runner_cursor_cli",
  pi: "acp.runner_pi",
  qwen_code: "acp.runner_qwen_code",
};

export const RUNNER_INTRO_KEYS: Record<string, string> = {
  opencode: "acp.intro_opencode",
  codebuddy: "acp.intro_codebuddy",
  claude_code: "acp.intro_claude_code",
  codex: "acp.intro_codex",
  kimi_code: "acp.intro_kimi_code",
  cursor_cli: "acp.intro_cursor_cli",
  pi: "acp.intro_pi",
  qwen_code: "acp.intro_qwen_code",
};

export function runnerIcon(key: string): string {
  return RUNNER_ICONS[key] ?? customRunnerIcon;
}

export function runnerLabelKey(key: string): string {
  return RUNNER_LABEL_KEYS[key] ?? "acp.runner_custom";
}

export function runnerIntroKey(key: string): string {
  return RUNNER_INTRO_KEYS[key] ?? "acp.intro_custom";
}

/** One-line install for the host that runs `octop`. Same text in every locale. */
export const RUNNER_INSTALL_COMMANDS: Partial<
  Record<BuiltinRunnerKey, string>
> = {
  opencode: "curl -fsSL https://opencode.ai/v2/install | bash",
  codebuddy: "curl -fsSL https://www.codebuddy.cn/cli/install.sh | bash",
  claude_code: "curl -fsSL https://claude.ai/install.sh | bash",
  codex: "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
  kimi_code: "curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash",
  cursor_cli: "curl https://cursor.com/install -fsS | bash",
  pi: "curl -fsSL https://pi.dev/install.sh | sh",
  qwen_code: "npm install -g @qwen-code/qwen-code@latest",
};

export function runnerInstallCommand(key: string): string | null {
  if (!isBuiltinRunner(key)) return null;
  return RUNNER_INSTALL_COMMANDS[key] ?? null;
}
