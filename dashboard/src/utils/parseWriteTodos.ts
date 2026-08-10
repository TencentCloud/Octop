export type TodoItemStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "cancelled"
  | string;

export interface TodoListItem {
  id: string;
  content: string;
  status: TodoItemStatus;
}

export interface WriteTodosMessageSource {
  toolData?: {
    name?: string;
    arguments?: string;
    output?: string;
  };
  status?: string;
}

const STATUS_ORDER: Record<string, number> = {
  in_progress: 0,
  pending: 1,
  completed: 2,
  cancelled: 3,
};

function toolNameBase(name: string): string {
  const trimmed = name.trim();
  const slash = trimmed.lastIndexOf("/");
  return slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
}

export function isWriteTodosToolName(name: string | undefined): boolean {
  return toolNameBase(name ?? "") === "write_todos";
}

function normalizeStatus(raw: unknown): TodoItemStatus {
  const value = String(raw ?? "pending")
    .trim()
    .toLowerCase();
  if (
    value === "pending" ||
    value === "in_progress" ||
    value === "completed" ||
    value === "cancelled"
  ) {
    return value;
  }
  if (value === "done" || value === "complete") return "completed";
  if (value === "running" || value === "active") return "in_progress";
  return "pending";
}

function normalizeTodo(raw: unknown, index: number): TodoListItem | null {
  if (typeof raw === "string") {
    const content = raw.trim();
    if (!content) return null;
    return { id: String(index + 1), content, status: "pending" };
  }
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const content = String(
    row.content ?? row.text ?? row.title ?? row.description ?? "",
  ).trim();
  if (!content) return null;
  const id = String(row.id ?? row.key ?? index + 1);
  return { id, content, status: normalizeStatus(row.status) };
}

function parseTodoPayload(raw: unknown): TodoListItem[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((item, index) => normalizeTodo(item, index))
      .filter((item): item is TodoListItem => item !== null);
  }
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const candidates = obj.todos ?? obj.items ?? obj.tasks;
    if (Array.isArray(candidates)) {
      return candidates
        .map((item, index) => normalizeTodo(item, index))
        .filter((item): item is TodoListItem => item !== null);
    }
  }
  return [];
}

function parseJsonLoose(raw: string | undefined): unknown {
  if (!raw?.trim()) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Extract complete `{...}` todo objects from incomplete streamed JSON. */
export function parsePartialTodoPayload(raw: string): TodoListItem[] {
  const trimmed = raw.trim();
  if (!trimmed) return [];

  const byId = new Map<string, TodoListItem>();
  const stack: number[] = [];
  for (let i = 0; i < trimmed.length; i += 1) {
    const ch = trimmed[i];
    if (ch === "{") {
      stack.push(i);
    } else if (ch === "}" && stack.length > 0) {
      const start = stack.pop();
      if (start === undefined) continue;
      const slice = trimmed.slice(start, i + 1);
      try {
        const obj = JSON.parse(slice);
        const item = normalizeTodo(obj, byId.size);
        if (item) byId.set(item.id, item);
      } catch {
        // ignore incomplete objects
      }
    }
  }
  return [...byId.values()];
}

export function parseWriteTodosToolData(
  argumentsRaw: string | undefined,
  outputRaw: string | undefined,
  allowPartial = false,
): TodoListItem[] {
  const fromOutput = parseTodoPayload(parseJsonLoose(outputRaw));
  if (fromOutput.length > 0) return fromOutput;
  const fromArgs = parseTodoPayload(parseJsonLoose(argumentsRaw));
  if (fromArgs.length > 0) return fromArgs;
  if (allowPartial && argumentsRaw?.trim()) {
    return parsePartialTodoPayload(argumentsRaw);
  }
  return [];
}

/** Merge all `write_todos` calls in a turn; later updates win for the same id. */
export function collectWriteTodosFromMessages(
  messages: readonly WriteTodosMessageSource[],
): TodoListItem[] {
  const byId = new Map<string, TodoListItem>();
  for (const msg of messages) {
    const td = msg.toolData;
    if (!td || !isWriteTodosToolName(td.name)) continue;
    const allowPartial = msg.status === "streaming";
    const items = parseWriteTodosToolData(
      td.arguments,
      td.output,
      allowPartial,
    );
    for (const item of items) {
      byId.set(item.id, item);
    }
  }
  return sortTodoItems([...byId.values()]);
}

export function countCompletedTodos(items: readonly TodoListItem[]): number {
  return items.filter((item) => item.status === "completed").length;
}

export function sortTodoItems(items: TodoListItem[]): TodoListItem[] {
  return [...items].sort((a, b) => {
    const left = STATUS_ORDER[a.status] ?? 99;
    const right = STATUS_ORDER[b.status] ?? 99;
    if (left !== right) return left - right;
    return a.id.localeCompare(b.id);
  });
}
