/**
 * Mirrors the backend guard in `src/octop/infra/gateway/slash/parser.py`: a
 * command name ends at whitespace, so a path like `/root/ddd` is plain text.
 */
const SLASH_COMMAND_RE = /^\/(?:[a-zA-Z][\w-]*(?:\s[\s\S]*)?)?$/;
const SLASH_NAME_RE = /^\/(?:[a-zA-Z][\w-]*)?$/;

/** True while the text reads as a command, with or without arguments. */
export function isSlashCommandText(text: string): boolean {
  return SLASH_COMMAND_RE.test(text);
}

/** True while the user is still typing the command name (menu is useful). */
export function isSlashNamePrefix(text: string): boolean {
  return SLASH_NAME_RE.test(text);
}
