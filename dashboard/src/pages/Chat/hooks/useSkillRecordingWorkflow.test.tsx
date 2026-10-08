import { act, renderHook, waitFor } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { browserApi } from "../../../api/modules/browser";
import { request } from "../../../api/request";
import en from "../../../locales/en.json";
import zh from "../../../locales/zh.json";
import { appendPushMessage } from "./chatStore";
import { useSkillRecordingWorkflow } from "./useSkillRecordingWorkflow";

vi.unmock("react-i18next");
vi.mock("../../../api/modules/browser", () => ({
  browserApi: { stopAndGenerateSkill: vi.fn() },
}));
vi.mock("../../../api/request", () => ({ request: vi.fn() }));
vi.mock("./chatStore", () => ({ appendPushMessage: vi.fn() }));
vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

async function setup(locale: "en" | "zh") {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: locale,
    fallbackLng: "en",
    resources: { en: { translation: en }, zh: { translation: zh } },
    interpolation: { escapeValue: false },
  });
  const hook = renderHook(
    () =>
      useSkillRecordingWorkflow({
        agentId: "agent-1",
        threadId: "thread-1",
        browserRecording: true,
        browserRecordingId: "recording-1",
        setBrowserRecording: vi.fn(),
        setBrowserRecordingId: vi.fn(),
        setBrowserLastRecordingId: vi.fn(),
      }),
    {
      wrapper: ({ children }: PropsWithChildren) => (
        <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
      ),
    },
  );
  return { ...hook, i18n };
}

beforeEach(() => vi.resetAllMocks());

describe("recording messages use the dashboard language", () => {
  it.each(["en", "zh"] as const)(
    "localizes the %s preview and follows a language switch before applying",
    async (locale) => {
      const script = Array.from(
        { length: 25 },
        (_, i) => "line-" + (i + 1),
      ).join("\n");
      vi.mocked(browserApi.stopAndGenerateSkill).mockResolvedValue({
        ok: true,
        recordingId: "recording-1",
        skillContent: script,
        skillName: "weather",
        steps: 3,
      });
      vi.mocked(request).mockResolvedValue({
        name: "weather",
        slug: "weather",
      });
      const { result, i18n } = await setup(locale);
      act(() => {
        expect(result.current.interceptUserMessage("end")).toBe(true);
      });
      await waitFor(() => expect(appendPushMessage).toHaveBeenCalledTimes(1));
      const preview = vi.mocked(appendPushMessage).mock.calls[0][0];
      expect(preview).toContain(
        locale === "en" ? "Recording finished" : "录制完成",
      );
      expect(preview).toContain("line-20");
      expect(preview).not.toContain("line-21");
      expect(preview).toContain(locale === "en" ? "25 lines" : "25 行");
      if (locale === "en") expect(preview).not.toMatch(/\p{Script=Han}/u);

      await act(() => i18n.changeLanguage(locale === "en" ? "zh" : "en"));
      act(() => {
        expect(result.current.interceptUserMessage("confirm")).toBe(true);
      });
      await waitFor(() => expect(appendPushMessage).toHaveBeenCalledTimes(2));
      const confirmation = vi.mocked(appendPushMessage).mock.calls[1][0];
      expect(confirmation).toContain(
        locale === "en" ? "已成功应用" : "applied",
      );
      if (locale === "zh") expect(confirmation).not.toMatch(/\p{Script=Han}/u);
      const body = JSON.parse(
        vi.mocked(request).mock.calls[0][1]!.body as string,
      );
      expect(body).toEqual({ name: "weather", content: script });
    },
  );

  it("localizes a missing generated script without sending a model message", async () => {
    vi.mocked(browserApi.stopAndGenerateSkill).mockResolvedValue({
      ok: true,
      steps: 2,
    });
    const { result } = await setup("en");
    act(() => {
      expect(result.current.interceptUserMessage("结束")).toBe(true);
    });
    await waitFor(() => expect(appendPushMessage).toHaveBeenCalledOnce());
    const content = vi.mocked(appendPushMessage).mock.calls[0][0];
    expect(content).toContain("Recording finished");
    expect(content).toContain("Failed to generate the skill script");
    expect(content).not.toMatch(/\p{Script=Han}/u);
    expect(request).not.toHaveBeenCalled();
  });
});
