import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ResolvedModel } from "../../../api/types";
import ChatInputActionsRow from "./ChatInputActionsRow";

// `isSttAvailable()` runs at module load, so the browser APIs it probes must
// exist before this module graph is imported.
vi.hoisted(() => {
  vi.stubGlobal("MediaRecorder", class {});
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: () => Promise.resolve() },
    configurable: true,
  });
  return true;
});

vi.mock("./ContextWindowRing", () => ({
  default: () => null,
}));

const models: ResolvedModel[] = [
  {
    provider_id: 1,
    provider_name: "Provider",
    provider_kind: "openai",
    model: "compact-model",
    name: "Compact Model",
    context_window: 128_000,
  },
];

describe("ChatInputActionsRow compact pickers", () => {
  it("uses a popover instead of a full-width drawer on narrow desktop", async () => {
    const { container } = render(
      <MemoryRouter>
        <ChatInputActionsRow
          isMobile={false}
          isStreaming={false}
          canSend={false}
          text=""
          polishing={false}
          uploading={false}
          recording={false}
          transcribing={false}
          availableModels={models}
          onModelChange={vi.fn()}
          slashPickerGroups={null}
          slashMenuItems={[]}
          onSlashShortcutSelect={vi.fn()}
          onFileSelect={vi.fn()}
          onNewChat={vi.fn()}
          onPolish={vi.fn()}
          onToggleVoice={vi.fn()}
          onCancel={vi.fn()}
          onSubmit={vi.fn()}
        />
      </MemoryRouter>,
    );

    const modelButton = container
      .querySelector("svg.lucide-cpu")
      ?.closest("button");
    expect(modelButton).not.toBeNull();
    expect(modelButton).not.toHaveTextContent("Auto");
    expect(modelButton).not.toHaveTextContent("Compact Model");
    expect(modelButton).not.toHaveTextContent("compact-model");

    fireEvent.click(modelButton!);

    await waitFor(() => {
      expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    });
    const popover = document.querySelector(".ant-popover");
    expect(popover?.querySelector("svg.lucide-sparkles")).not.toBeNull();
    expect(popover?.querySelector("img")).not.toBeNull();
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
  });
});

function renderRow(overrides: Record<string, unknown> = {}) {
  const handlers = {
    onVoiceStart: vi.fn(),
    onVoiceStop: vi.fn(),
    onToggleVoice: vi.fn(),
  };
  const view = render(
    <MemoryRouter>
      <ChatInputActionsRow
        isMobile={false}
        isStreaming={false}
        canSend={false}
        text=""
        polishing={false}
        uploading={false}
        recording={false}
        transcribing={false}
        slashPickerGroups={null}
        slashMenuItems={[]}
        onSlashShortcutSelect={vi.fn()}
        onFileSelect={vi.fn()}
        onNewChat={vi.fn()}
        onPolish={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
        {...handlers}
        {...overrides}
      />
    </MemoryRouter>,
  );
  const mic = view.container
    .querySelector("svg.lucide-mic")
    ?.closest("button") as HTMLButtonElement;
  return { ...view, ...handlers, mic };
}

describe("ChatInputActionsRow voice button", () => {
  it("dictates while held down when realtime STT is on", () => {
    const { mic, onVoiceStart, onVoiceStop, onToggleVoice } = renderRow({
      voiceHoldToTalk: true,
    });

    fireEvent.pointerDown(mic);
    expect(onVoiceStart).toHaveBeenCalledTimes(1);

    fireEvent.pointerUp(mic);
    expect(onVoiceStop).toHaveBeenCalledTimes(1);

    // A plain click must not toggle the recorder in hold-to-talk mode.
    fireEvent.click(mic);
    expect(onToggleVoice).not.toHaveBeenCalled();
    expect(onVoiceStart).toHaveBeenCalledTimes(1);
  });

  it("finishes when the pointer slides off the button", () => {
    const { mic, onVoiceStop } = renderRow({ voiceHoldToTalk: true });

    fireEvent.pointerDown(mic);
    fireEvent.pointerLeave(mic);
    fireEvent.pointerUp(mic);

    expect(onVoiceStop).toHaveBeenCalledTimes(1);
  });

  it("keeps click-to-toggle when realtime STT is off", () => {
    const { mic, onToggleVoice, onVoiceStart } = renderRow();

    fireEvent.click(mic);
    expect(onToggleVoice).toHaveBeenCalledTimes(1);

    fireEvent.pointerDown(mic);
    expect(onVoiceStart).not.toHaveBeenCalled();
  });

  it("stays available while a reply is still streaming", () => {
    const { mic } = renderRow({ voiceHoldToTalk: true, isStreaming: true });

    expect(mic).not.toBeDisabled();
  });
});
