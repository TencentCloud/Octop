import type { ChatMessage } from "../pages/Chat/hooks/useChat";
import type { AssistantTurnSplit } from "../pages/Chat/utils/messageContent";
import {
  collectToolMediaFromToolData,
  type ToolMediaItem,
} from "./toolMediaBlocks";

export type TurnToolMedia = {
  images: ToolMediaItem[];
  videos: ToolMediaItem[];
  files: Array<{ url: string; filename?: string }>;
};

export function collectTurnToolMedia(
  split: AssistantTurnSplit,
  agentId?: string | null,
): TurnToolMedia {
  const images: ToolMediaItem[] = [];
  const videos: ToolMediaItem[] = [];
  const files: Array<{ url: string; filename?: string }> = [];

  for (const msg of split?.tools ?? []) {
    const owner = msg.speakerAgentId?.trim() || agentId;
    const batch = collectToolMediaFromToolData(
      msg.toolData,
      owner,
      msg.attachments,
    );
    images.push(...batch.images);
    videos.push(...batch.videos);
    files.push(...batch.files);
  }

  return { images, videos, files };
}

export function collectMessageToolMedia(
  message: ChatMessage,
  agentId?: string | null,
): TurnToolMedia {
  return collectToolMediaFromToolData(
    message.toolData,
    agentId,
    message.attachments,
  );
}
