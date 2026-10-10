/** Types for the Code Console (``/api/code/*``) surface. */

/** One ACP runner the current user may drive from the Code page. */
export interface CodeRunner {
  name: string;
  command: string;
  args: string[];
  trusted: boolean;
  tool_parse_mode: string;
  env_keys: string[];
  /**
   * Env var that receives the picked model, or ``null`` when the runner has no
   * mapping yet (picking a model cannot take effect for it).
   */
  model_env: string | null;
}

/** A selectable model for one runner. */
export interface CodeModelOption {
  id: string;
  label: string;
}

/** A coding session as returned by the list/create endpoints. */
export interface CodeSession {
  id: string;
  runner: string;
  model?: string | null;
  cwd: string;
  status: string;
  meta?: Record<string, unknown>;
}

/** One persisted turn event, replayed when a session is re-opened. */
export interface CodeEvent {
  seq: number;
  ts: number;
  kind: string;
  payload: Record<string, unknown>;
  turn_id?: string | null;
  is_error?: boolean;
}

/** A file living in the session worktree (``@``-mentionable). */
export interface CodeFileItem {
  name: string;
  path: string;
}

/** An uploaded file staged for the next prompt. */
export interface CodeAttachment {
  name: string;
  path: string;
  size?: number;
}

/** One option the harness offers for a permission prompt. */
export interface CodePermissionOption {
  id: string;
  name: string;
  kind: string;
}

/** A suspended tool call waiting for the user to pick an option. */
export interface CodePermission {
  title?: string;
  detail?: string;
  tool_name: string;
  tool_kind: string;
  options: CodePermissionOption[];
}

/**
 * A live event pushed over the SSE turn stream. ``type`` is one of
 * ``text_delta`` / ``text`` / ``thought`` / ``tool_start`` / ``tool_update`` /
 * ``error``.
 */
export interface CodeLiveEvent {
  type: string;
  text?: string;
  call_id?: string;
  title?: string;
  name?: string;
  kind?: string;
  status?: string;
  detail?: string;
  is_error?: boolean;
}

/** Terminal frame of the SSE turn stream. */
export interface CodeFinalEvent {
  status: string;
  text?: string;
  permission?: CodePermission;
  event?: { text?: string } | null;
}
