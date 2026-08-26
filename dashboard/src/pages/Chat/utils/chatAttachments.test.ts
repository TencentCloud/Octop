import { describe, expect, it } from "vitest";
import {
  buildUserMessageContent,
  inferAttachmentKind,
} from "./chatAttachments";

describe("inferAttachmentKind", () => {
  it("returns video and audio kinds from the server MIME", () => {
    const video = new File([""], "clip.mp4", { type: "video/mp4" });
    const audio = new File([""], "track.mp3", { type: "audio/mpeg" });
    expect(inferAttachmentKind(video, "video/mp4")).toBe("video");
    expect(inferAttachmentKind(audio, "audio/mpeg")).toBe("audio");
  });

  it("classifies by filename when MIME is generic", () => {
    const mkv = new File([""], "clip.mkv", {
      type: "application/octet-stream",
    });
    expect(inferAttachmentKind(mkv, "application/octet-stream")).toBe("video");
  });
});

describe("buildUserMessageContent", () => {
  it("sends video and audio as file path-hint blocks, not vision", () => {
    const content = buildUserMessageContent("see this", [
      {
        url: "/api/agents/a1/media/preview?source=inbound%2Fclip.mp4",
        filename: "clip.mp4",
        mediaType: "video/mp4",
        workspacePath: "inbound/clip.mp4",
        kind: "video",
      },
      {
        url: "/api/agents/a1/media/preview?source=inbound%2Ftrack.mp3",
        filename: "track.mp3",
        mediaType: "audio/mpeg",
        workspacePath: "inbound/track.mp3",
        kind: "audio",
      },
    ]);
    expect(content).toEqual([
      { type: "text", text: "see this" },
      {
        type: "file",
        filename: "clip.mp4",
        media_type: "video/mp4",
        workspace_path: "inbound/clip.mp4",
      },
      {
        type: "file",
        filename: "track.mp3",
        media_type: "audio/mpeg",
        workspace_path: "inbound/track.mp3",
      },
    ]);
  });
});
