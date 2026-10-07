import { getApiUrl } from "../config";
import { getAuthToken, request, requestUpload } from "../request";
import type { SkillPackage } from "../types/skillPackage";
import type {
  CodeAttachment,
  CodeEvent,
  CodeFileItem,
  CodeFinalEvent,
  CodeLiveEvent,
  CodeModelOption,
  CodeRunner,
  CodeSession,
} from "../types/code";

function sessionPath(sessionId: string, suffix = ""): string {
  return `/code/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export interface CodePromptBody {
  text: string;
  /** Set when the turn resumes from a permission prompt. */
  option_id?: string;
  /** Worktree-relative paths uploaded for this turn. */
  attachments?: string[];
}

/**
 * POST a turn and consume the SSE reply.
 *
 * ``fetch()`` is used instead of ``EventSource`` because the endpoint is a POST
 * (it carries the prompt body). Returns an abort handle.
 */
function streamPrompt(
  sessionId: string,
  body: CodePromptBody,
  onEvent: (event: CodeLiveEvent) => void,
  onFinal: (final: CodeFinalEvent) => void,
  onError: (err: Error) => void,
): () => void {
  const controller = new AbortController();
  const url = getApiUrl(sessionPath(sessionId, "/prompt"));
  const token = getAuthToken();

  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onError(new Error(`Request failed: ${res.status} ${res.statusText}`));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        // The last element may be an incomplete frame — keep it for the next read.
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(line.slice(6)) as Record<string, unknown>;
          } catch {
            continue;
          }
          // The server marks the terminal frame with `__final__`; every other
          // frame is a live turn event.
          if (payload.__final__) {
            onFinal(payload as unknown as CodeFinalEvent);
          } else {
            onEvent(payload as unknown as CodeLiveEvent);
          }
        }
      }
    })
    .catch((err: unknown) => {
      if (controller.signal.aborted) return;
      onError(err instanceof Error ? err : new Error(String(err)));
    });

  return () => controller.abort();
}

export const codeApi = {
  /** Enabled ACP runners plus the default working directory. */
  listRunners: () =>
    request<{ runners: CodeRunner[]; default_cwd: string }>("/code/runners"),

  /**
   * Selectable models per runner. ``model_env`` echoes which env var each
   * runner receives so the UI can flag runners that cannot switch models.
   */
  listModels: () =>
    request<{
      models: Record<string, CodeModelOption[]>;
      model_env: Record<string, string | null>;
    }>("/code/models"),

  listSessions: () => request<{ sessions: CodeSession[] }>("/code/sessions"),

  getSession: (sessionId: string) =>
    request<CodeSession>(sessionPath(sessionId)),

  createSession: (body: {
    runner: string;
    model?: string;
    cwd?: string;
    repo_path?: string;
  }) =>
    request<CodeSession>("/code/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  closeSession: (sessionId: string) =>
    request<{ ok: boolean }>(sessionPath(sessionId), { method: "DELETE" }),

  /** Replay persisted events so a re-opened session shows its history. */
  listEvents: (sessionId: string, afterSeq = 0, limit = 500) =>
    request<{ session_id: string; events: CodeEvent[] }>(
      `${sessionPath(
        sessionId,
        "/events",
      )}?after_seq=${afterSeq}&limit=${limit}`,
    ),

  /** Unified diff of everything the agent changed in the worktree. */
  getPatch: (sessionId: string) =>
    request<{ session_id: string; patch: string }>(
      sessionPath(sessionId, "/patch"),
    ),

  listFiles: (sessionId: string, query = "") =>
    request<{ cwd: string; files: CodeFileItem[] }>(
      `${sessionPath(sessionId, "/files")}?q=${encodeURIComponent(query)}`,
    ),

  /** Stage text files under ``uploads/`` for the next prompt. */
  uploadFiles: (sessionId: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return requestUpload<{ files: CodeAttachment[] }>(
      sessionPath(sessionId, "/files"),
      form,
      { method: "POST" },
    );
  },

  /**
   * Installed skill packages, offered as ``@`` mentions in the composer.
   * Reuses the skill-package registry the rest of the dashboard reads.
   */
  listSkills: () => request<SkillPackage[]>("/skill-packages"),

  /** Ask the backend to abort the running turn. */
  cancel: (sessionId: string) =>
    request<{ ok: boolean }>(sessionPath(sessionId, "/cancel"), {
      method: "POST",
    }),

  /** Start a streaming turn. Returns an abort handle. */
  streamPrompt,
};
