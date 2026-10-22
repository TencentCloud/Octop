import { request, requestStream } from "../request";

export interface DesignTask {
  task_id: string;
  instance_id: string;
  project: string;
  run_id: string | null;
  status: string;
  last_error: string | null;
  result: { previewUrl?: string; agentMessage?: string; entryFile?: string };
  revision: number;
  created_at: number;
  updated_at: number;
  anchor_message_ids?: string[];
}

const scope = (agent: string, thread: string) =>
  `/agents/${encodeURIComponent(agent)}/threads/${encodeURIComponent(
    thread,
  )}/open-design`;

export interface DesignSelection {
  agent?: string | null;
  model?: string | null;
  skills: string[];
  designSystem?: string | null;
}
export interface DesignResource {
  uri: string;
  name: string;
  description?: string;
  mimeType?: string;
}
export interface DesignAgent {
  id: string;
  name: string;
  version?: string;
  models?: (string | { id: string; name?: string })[];
  modelsCount?: number;
}
export interface DesignCatalog {
  resources: DesignResource[];
  next_cursor: string | null;
  agents: DesignAgent[];
  selection: DesignSelection;
}
export interface DesignHealth {
  levels: { level: string; ok: boolean; count?: number }[];
  agents: DesignAgent[];
  generation_verified: boolean;
}
export interface DesignSource {
  path: string;
  content: string;
  digest: string;
  truncated: boolean;
  previewUrl?: string;
}
const instanceScope = (instance: string, agent?: string, thread?: string) =>
  agent && thread
    ? `${scope(agent, thread)}/instances/${encodeURIComponent(instance)}`
    : `/connector-instances/${encodeURIComponent(instance)}/open-design`;

export const openDesignApi = {
  health: (instance: string) =>
    request<DesignHealth>(
      `/connector-instances/${encodeURIComponent(instance)}/open-design/health`,
    ),
  catalog: (
    instance: string,
    agent?: string,
    thread?: string,
    cursor?: string,
  ) =>
    request<DesignCatalog>(
      `${instanceScope(instance, agent, thread)}/catalog${
        cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""
      }`,
    ),
  select: (
    instance: string,
    selection: DesignSelection,
    agent?: string,
    thread?: string,
  ) =>
    request<DesignSelection>(
      `${instanceScope(instance, agent, thread)}/selection`,
      { method: "PUT", body: JSON.stringify(selection) },
    ),
  resource: (instance: string, uri: string, agent?: string, thread?: string) =>
    request<{ uri: string; text: string; truncated: boolean }>(
      `${instanceScope(
        instance,
        agent,
        thread,
      )}/resource?uri=${encodeURIComponent(uri)}`,
    ),
  search: (
    agent: string,
    thread: string,
    instance: string,
    project: string,
    query: string,
  ) =>
    request<{ matches?: { file: string; line: number; snippet: string }[] }>(
      `${instanceScope(instance, agent, thread)}/projects/${encodeURIComponent(
        project,
      )}/search?query=${encodeURIComponent(query)}`,
    ),
  file: (
    agent: string,
    thread: string,
    instance: string,
    project: string,
    path: string,
  ) =>
    request<DesignSource>(
      `${instanceScope(instance, agent, thread)}/projects/${encodeURIComponent(
        project,
      )}/file?path=${encodeURIComponent(path)}`,
    ),
  edit: (
    agent: string,
    thread: string,
    instance: string,
    project: string,
    file: { path: string; digest: string; content: string },
  ) =>
    request<DesignSource>(
      `${instanceScope(instance, agent, thread)}/projects/${encodeURIComponent(
        project,
      )}/file`,
      { method: "PUT", body: JSON.stringify(file) },
    ),
  cancel: (agent: string, thread: string, task: string) =>
    request<DesignTask[]>(
      `${scope(agent, thread)}/tasks/${encodeURIComponent(task)}/cancel`,
      { method: "POST" },
    ),
  tasks: (agent: string, thread: string) =>
    request<DesignTask[]>(`${scope(agent, thread)}/tasks`),
  refresh: (agent: string, thread: string, task: string) =>
    request<DesignTask[]>(
      `${scope(agent, thread)}/tasks/${encodeURIComponent(task)}/refresh`,
      { method: "POST" },
    ),
  watch: async (
    agent: string,
    thread: string,
    onTasks: (tasks: DesignTask[]) => void,
    signal: AbortSignal,
  ) => {
    const { body } = await requestStream(`${scope(agent, thread)}/events`, {
      signal,
    });
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer += decoder.decode(value, { stream: true });
        let end: number;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          if (frame.startsWith("data: "))
            onTasks(JSON.parse(frame.slice(6)) as DesignTask[]);
        }
      }
    } finally {
      await reader.cancel().catch(() => undefined);
      reader.releaseLock();
    }
  },
};
