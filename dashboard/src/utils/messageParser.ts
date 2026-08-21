/**
 * Shared message-parsing helpers used by both chatStore.ts and useChat.ts.
 * Extracted to avoid code duplication and potential circular imports.
 */

import type {
  ChatAttachment,
  ToolCallData,
} from "../pages/Chat/hooks/sseHelpers";

// ── Shared types ──────────────────────────────────────────────────────────

export interface ContentBlock {
  type: string;
  text?: string;
  data?: {
    name?: string;
    call_id?: string;
    arguments?: string;
    output?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

// ── Helpers ──────────────────────────────────────────────────────────────

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export interface ContentBlockItem {
  type: "text" | "thinking";
  content: string;
}

function normalizeVisibleTextBlock(text: string | undefined): string {
  return text ?? "";
}

export function extractContentBlocks(
  content: unknown,
): ContentBlockItem[] | undefined {
  if (!Array.isArray(content)) return undefined;

  const blocks: ContentBlockItem[] = [];
  for (const block of content as ContentBlock[]) {
    if (block.type === "thinking") {
      const thinking = (block as Record<string, unknown>).thinking;
      if (typeof thinking === "string" && thinking.trim()) {
        blocks.push({ type: "thinking", content: thinking });
      }
      continue;
    }

    if (block.type === "text") {
      const text = normalizeVisibleTextBlock(block.text);
      if (text) {
        blocks.push({ type: "text", content: text });
      }
    }
  }

  return blocks.length > 0 ? blocks : undefined;
}

export function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return String(content || "");
  return (extractContentBlocks(content) || [])
    .filter((block) => block.type === "text")
    .map((block) => block.content)
    .join("\n");
}

/** Plain-text body for read-only history views (includes tool blocks). */
export function formatHistoryMessageText(content: unknown): string {
  const text = extractText(content).trim();
  if (text) return text;
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const block of content as ContentBlock[]) {
    const b = block as Record<string, unknown>;
    if (
      b.type === "thinking" &&
      typeof b.thinking === "string" &&
      b.thinking.trim()
    ) {
      parts.push(b.thinking.trim());
      continue;
    }
    if (b.type === "tool_result" && typeof b.output === "string") {
      parts.push(b.output);
      continue;
    }
    if (b.type === "tool_use") {
      const name = typeof b.name === "string" ? b.name : "tool";
      const input =
        b.input !== undefined ? JSON.stringify(b.input, null, 2) : "";
      parts.push(input ? `${name}\n${input}` : name);
      continue;
    }
    if (b.type === "image" || b.type === "file") {
      const filename = b.filename ?? b.name;
      parts.push(
        typeof filename === "string" && filename.trim()
          ? filename
          : `[${String(b.type)}]`,
      );
    }
  }
  return parts.join("\n\n");
}

export interface DialogueHistoryMessage {
  role: string;
  content: unknown;
  id?: string;
  timestamp?: number;
}

const DIALOGUE_EXCLUDED_BLOCK_TYPES = new Set([
  "tool_use",
  "tool_result",
  "thinking",
]);

function stripNonDialogueBlocks(content: unknown): unknown {
  if (!Array.isArray(content)) return content;
  return (content as ContentBlock[]).filter(
    (block) => !DIALOGUE_EXCLUDED_BLOCK_TYPES.has(String(block.type || "")),
  );
}

function hasDialogueContent(content: unknown): boolean {
  if (extractText(content).trim().length > 0) return true;
  if (!Array.isArray(content)) return false;
  return (content as ContentBlock[]).some((block) => {
    const type = String(block.type || "");
    return type === "image" || type === "file";
  });
}

/** User/assistant turns only — strips tool calls, tool results, and thinking. */
export function filterDialogueHistoryMessages<T extends DialogueHistoryMessage>(
  messages: T[],
): T[] {
  return messages
    .filter((msg) => {
      const role = msg.role || "";
      return role === "user" || role === "assistant";
    })
    .map((msg) => ({
      ...msg,
      content: stripNonDialogueBlocks(msg.content),
    }))
    .filter((msg) => hasDialogueContent(msg.content));
}

/**
 * Extract tool call / result data from a message's `content` array.
 */
export function extractToolData(
  content: unknown,
): { kind: "call" | "result"; data: ToolCallData } | undefined {
  if (!Array.isArray(content)) return undefined;
  const blocks = content as ContentBlock[];

  const dataBlock = blocks.find((c) => c.type === "data" && c.data);
  if (dataBlock?.data) {
    const d = dataBlock.data;
    if (d.name && d.arguments !== undefined) {
      return {
        kind: "call",
        data: { name: d.name, callId: d.call_id, arguments: d.arguments },
      };
    }
    if (d.output !== undefined) {
      return {
        kind: "result",
        data: {
          name: d.name,
          callId: d.call_id,
          output: d.output,
          errorCode:
            typeof d.error_code === "string" ? d.error_code : undefined,
          returnCode:
            typeof d.returncode === "number" ? d.returncode : undefined,
        },
      };
    }
  }

  const toolUseBlock = blocks.find((c) => c.type === "tool_use");
  if (toolUseBlock) {
    const b = toolUseBlock as Record<string, unknown>;
    return {
      kind: "call",
      data: {
        name: (b.name as string) || "",
        callId: (b.id as string) || "",
        arguments: b.input !== undefined ? JSON.stringify(b.input) : "{}",
      },
    };
  }

  const toolResultBlock = blocks.find((c) => c.type === "tool_result");
  if (toolResultBlock) {
    const b = toolResultBlock as Record<string, unknown>;
    return {
      kind: "result",
      data: {
        name: (b.name as string) || "",
        callId: (b.id as string) || "",
        output:
          typeof b.output === "string"
            ? b.output
            : JSON.stringify(b.output ?? ""),
        errorCode:
          typeof b.error_code === "string"
            ? (b.error_code as string)
            : undefined,
        returnCode:
          typeof b.returncode === "number"
            ? (b.returncode as number)
            : undefined,
      },
    };
  }

  return undefined;
}

/**
 * Extract image/file attachments from a message's `content` array.
 */
export function extractAttachmentsFromContent(
  content: unknown,
): ChatAttachment[] {
  if (!Array.isArray(content)) return [];
  return (content as ContentBlock[])
    .map((block) => {
      const anyBlock = block as Record<string, unknown>;
      const type = String(anyBlock.type || "");
      const workspacePath = String(
        anyBlock.workspace_path || anyBlock.workspacePath || "",
      ).trim();
      const filename =
        (anyBlock.filename as string | undefined) ||
        (anyBlock.name as string | undefined);

      if (type === "image_url") {
        const imageUrlField = anyBlock.image_url;
        const rawUrl =
          typeof imageUrlField === "string"
            ? imageUrlField
            : typeof imageUrlField === "object" && imageUrlField !== null
            ? String((imageUrlField as { url?: string }).url || "")
            : "";
        let url = rawUrl;
        let path: string | undefined = workspacePath;
        if (rawUrl.startsWith("workspace://")) {
          path =
            path ||
            rawUrl.slice("workspace://".length).replace(/^\/+/, "") ||
            undefined;
          url = "";
        }
        if (!url && !path) return null;
        const mediaType =
          (anyBlock.mime_type as string | undefined) ||
          (anyBlock.media_type as string | undefined) ||
          (url.startsWith("data:") ? url.slice(5).split(";")[0] : undefined);
        return {
          url,
          filename: filename || "image",
          mediaType,
          workspacePath: path || undefined,
          kind: "image",
        } satisfies ChatAttachment;
      }

      if (type !== "image" && type !== "file") return null;
      const source = anyBlock.source as
        | string
        | {
            type?: string;
            url?: string;
            media_type?: string;
            data?: string;
          }
        | undefined;
      const sourceUrl =
        typeof source === "string"
          ? source
          : source?.type === "url"
          ? source.url
          : undefined;
      const url =
        (anyBlock.preview_url as string | undefined) ||
        (anyBlock.image_url as string | undefined) ||
        (anyBlock.file_url as string | undefined) ||
        sourceUrl;
      if (!url && !workspacePath) return null;
      const mediaType =
        (typeof source === "string" ? undefined : source?.media_type) ||
        (anyBlock.media_type as string | undefined);
      return {
        url: url || "",
        filename,
        mediaType,
        workspacePath: workspacePath || undefined,
        kind:
          type === "image" || mediaType?.startsWith("image/")
            ? "image"
            : "file",
      } satisfies ChatAttachment;
    })
    .filter(Boolean) as ChatAttachment[];
}

/**
 * Merge incoming attachments into an existing list (de-duplicating by path / url).
 */
export function mergeAttachments(
  existing: ChatAttachment[] | undefined,
  incoming: ChatAttachment[],
): ChatAttachment[] | undefined {
  if (incoming.length === 0) return existing;
  const merged = [...(existing || [])];
  for (const attachment of incoming) {
    let matched = false;
    for (let i = 0; i < merged.length; i++) {
      const item = merged[i];
      const samePath =
        Boolean(attachment.workspacePath) &&
        item.workspacePath === attachment.workspacePath;
      const sameUrl = Boolean(attachment.url) && item.url === attachment.url;
      if (!samePath && !sameUrl) continue;
      merged[i] = {
        ...item,
        ...attachment,
        url:
          attachment.url && !attachment.url.startsWith("workspace://")
            ? attachment.url
            : item.url && !item.url.startsWith("workspace://")
            ? item.url
            : "",
        workspacePath: attachment.workspacePath || item.workspacePath,
        filename: attachment.filename || item.filename,
        mediaType: attachment.mediaType || item.mediaType,
        kind: attachment.kind || item.kind,
      };
      matched = true;
      break;
    }
    if (!matched) {
      merged.push(attachment);
    }
  }
  return merged.length > 0 ? merged : undefined;
}
