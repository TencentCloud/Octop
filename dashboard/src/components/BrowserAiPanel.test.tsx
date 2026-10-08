import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createInstance } from "i18next";
import { useState } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { browserApi } from "../api/modules/browser";
import { request } from "../api/request";
import type { OctopAgent } from "../context/AgentContext";
import en from "../locales/en.json";
import zh from "../locales/zh.json";
import { appendPushMessage } from "../pages/Chat/hooks/chatStore";
import { message } from "../utils/antdMessage";
import BrowserAiPanel from "./BrowserAiPanel";

const { send } = vi.hoisted(() => ({ send: vi.fn() }));
vi.unmock("react-i18next");
vi.mock("../hooks/useAgentThreadChat", () => ({
  useAgentThreadChat: () => ({
    threadId: "thread-1",
    booting: false,
    bootError: null,
    messages: [],
    isStreaming: false,
    send,
    cancelStream: vi.fn(),
  }),
}));
vi.mock("./AgentSelector", () => ({ default: () => null }));
vi.mock("../pages/Chat/components/MessageList", () => ({
  default: () => null,
}));
vi.mock("../pages/Chat/hooks/chatStore", () => ({
  appendPushMessage: vi.fn(),
}));
vi.mock("../api/modules/browser", () => ({
  browserApi: { stopAndGenerateSkill: vi.fn(), replayRecording: vi.fn() },
}));
vi.mock("../api/request", () => ({ request: vi.fn() }));
vi.mock("../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

const agent: OctopAgent = {
  id: 1,
  agent_id: "agent-1",
  name: "Test agent",
  description: null,
  persona_mbti: null,
  default_model: null,
  system_prompt: null,
  template_name: null,
  state: "running",
  last_error: null,
  icon: null,
  icon_name: null,
  icon_url: null,
  color: null,
  config: {},
};

async function setup(recording = false) {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: "zh",
    fallbackLng: "en",
    resources: { en: { translation: en }, zh: { translation: zh } },
    interpolation: { escapeValue: false },
  });
  function Panel() {
    const [isRecording, setRecording] = useState(recording);
    return (
      <BrowserAiPanel
        activeAgent={agent}
        tabs={[]}
        currentUrl="https://example.com"
        onClose={vi.fn()}
        browserRecording={isRecording}
        browserRecordingId="recording-1"
        setBrowserRecording={setRecording}
      />
    );
  }
  render(
    <I18nextProvider i18n={i18n}>
      <Panel />
    </I18nextProvider>,
  );
  await act(async () => {
    await i18n.changeLanguage("en");
  });
}

function submit(text: string) {
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
}

beforeEach(() => vi.resetAllMocks());

describe("browser assistant language", () => {
  it("localizes recording controls and messages after switching to English, preserving the script", async () => {
    const script = "# 搜索天气\nrecording_id: recording-1";
    vi.mocked(request)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ slug: "weather" });
    vi.mocked(browserApi.stopAndGenerateSkill).mockResolvedValue({
      ok: true,
      recordingId: "recording-1",
      skillContent: script,
      steps: 3,
    });
    await setup(true);
    expect(screen.getByRole("textbox")).toHaveAttribute(
      "placeholder",
      "Enter task objective...",
    );
    submit("weather");
    expect(appendPushMessage).toHaveBeenLastCalledWith(
      expect.stringContaining("Task objective set: **weather**"),
    );
    expect(vi.mocked(appendPushMessage).mock.calls[0][0]).not.toMatch(
      /\p{Script=Han}/u,
    );

    submit("搜索天气");
    expect(send).toHaveBeenCalledExactlyOnceWith("搜索天气");
    submit("end");
    await waitFor(() => expect(appendPushMessage).toHaveBeenCalledTimes(2));
    const preview = vi.mocked(appendPushMessage).mock.calls[1][0];
    expect(preview).toContain("Recording finished! 3 replay steps generated.");
    expect(preview).toContain(script);
    expect(screen.getByRole("textbox")).toHaveAttribute(
      "placeholder",
      'Type "confirm" to apply',
    );

    submit("confirm");
    await waitFor(() => expect(appendPushMessage).toHaveBeenCalledTimes(3));
    expect(appendPushMessage).toHaveBeenLastCalledWith(
      expect.stringContaining('Skill **"weather"** applied successfully!'),
    );
    expect(request).toHaveBeenLastCalledWith("/agents/agent-1/skills", {
      method: "POST",
      body: JSON.stringify({ name: "weather", content: script }),
    });
    expect(message.success).toHaveBeenLastCalledWith('Skill "weather" applied');
    expect(send).toHaveBeenCalledTimes(1);
  });

  it.each(["passed", "failed"])(
    "localizes a %s replay without calling the model",
    async (status) => {
      vi.mocked(request)
        .mockResolvedValueOnce([{ slug: "weather" }])
        .mockResolvedValueOnce({ raw: "recording_id: recording-1" });
      vi.mocked(browserApi.replayRecording).mockResolvedValue({
        status,
        steps: [{ id: 1, kind: "click", status: "failed" }],
      });
      await setup();
      await waitFor(() =>
        expect(screen.getByRole("textbox")).toHaveAttribute(
          "placeholder",
          "Type skill to replay, or chat",
        ),
      );
      submit("weather");
      await waitFor(() => expect(appendPushMessage).toHaveBeenCalledTimes(2));
      const contents = vi
        .mocked(appendPushMessage)
        .mock.calls.map(([content]) => content);
      expect(contents[0]).toContain('Replaying with skill "weather"');
      expect(contents[1]).toContain(
        status === "passed" ? "replay finished" : "Step 1 (click): failed",
      );
      expect(contents.join("\n")).not.toMatch(/\p{Script=Han}/u);
      expect(send).not.toHaveBeenCalled();
    },
  );
});
