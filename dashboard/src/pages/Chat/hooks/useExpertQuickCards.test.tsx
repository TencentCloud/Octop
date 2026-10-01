import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import {
  agentChatApi,
  type ChatWelcomeResponse,
} from "../../../api/modules/agentChat";
import type { OctopAgent } from "../../../context/AgentContext";
import { useExpertChatWelcome } from "./useExpertQuickCards";

const { i18n } = vi.hoisted(() => ({ i18n: { language: "en" } }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ i18n }) }));
vi.mock("../../../api/modules/agentChat", () => ({
  agentChatApi: { welcome: vi.fn() },
}));

function deferred() {
  let resolve!: (value: ChatWelcomeResponse) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<ChatWelcomeResponse>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const agent = (id: string) => ({ agent_id: id }) as OctopAgent;
const welcome = (name: string): ChatWelcomeResponse => ({
  welcome_message: { en: `${name} welcome`, zh: `${name} 欢迎` },
  quick_prompts: [
    {
      title: { en: name, zh: `${name} 中文` },
      description: { en: `${name} description` },
      prompt: { en: `${name} task`, zh: `${name} 任务` },
    },
  ],
});

beforeEach(() => {
  vi.clearAllMocks();
  i18n.language = "en";
});

it("clears the previous expert's actionable cards while the next welcome is pending", async () => {
  const first = deferred();
  const second = deferred();
  vi.mocked(agentChatApi.welcome)
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  const { result, rerender } = renderHook(
    ({ current }) => useExpertChatWelcome(current),
    {
      initialProps: { current: agent("a") },
    },
  );
  await act(async () => first.resolve(welcome("Alpha")));
  expect(result.current.quickCards[0].prompt).toBe("Alpha task");
  rerender({ current: agent("b") });
  expect(result.current).toEqual({ quickCards: [], welcomeSuffix: null });
  await act(async () => second.resolve(welcome("Beta")));
  expect(result.current.quickCards[0].prompt).toBe("Beta task");
  expect(result.current.welcomeSuffix).toBe("Beta welcome");
});

it("clears the previous language while the translated welcome is pending", async () => {
  const first = deferred();
  const second = deferred();
  vi.mocked(agentChatApi.welcome)
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  const { result, rerender } = renderHook(() =>
    useExpertChatWelcome(agent("a")),
  );
  await act(async () => first.resolve(welcome("Alpha")));
  i18n.language = "zh";
  rerender();
  expect(result.current).toEqual({ quickCards: [], welcomeSuffix: null });
  await act(async () => second.resolve(welcome("Alpha")));
  expect(result.current.quickCards[0].prompt).toBe("Alpha 任务");
  expect(result.current.welcomeSuffix).toBe("Alpha 欢迎");
});

it.each(["resolve", "reject"] as const)(
  "ignores a stale request that later %ss",
  async (settle) => {
    const first = deferred();
    const second = deferred();
    vi.mocked(agentChatApi.welcome)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(
      ({ current }) => useExpertChatWelcome(current),
      {
        initialProps: { current: agent("a") },
      },
    );
    rerender({ current: agent("b") });
    await act(async () => second.resolve(welcome("Beta")));
    await act(async () => {
      if (settle === "resolve") first.resolve(welcome("Alpha"));
      else first.reject(new Error("late failure"));
    });
    expect(result.current.quickCards[0].prompt).toBe("Beta task");
    expect(result.current.welcomeSuffix).toBe("Beta welcome");
  },
);

it("clears the welcome when no expert is selected", async () => {
  const first = deferred();
  vi.mocked(agentChatApi.welcome).mockReturnValueOnce(first.promise);
  const { result, rerender } = renderHook(
    ({ current }: { current: OctopAgent | null }) =>
      useExpertChatWelcome(current),
    {
      initialProps: { current: agent("a") },
    },
  );
  await act(async () => first.resolve(welcome("Alpha")));
  rerender({ current: null });
  expect(result.current).toEqual({ quickCards: [], welcomeSuffix: null });
  expect(agentChatApi.welcome).toHaveBeenCalledTimes(1);
});
