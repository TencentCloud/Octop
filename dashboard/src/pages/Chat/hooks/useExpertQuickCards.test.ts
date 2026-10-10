import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { welcome, i18nState } = vi.hoisted(() => ({
  welcome: vi.fn(),
  i18nState: { language: "zh" },
}));

vi.mock("../../../api/modules/agentChat", () => ({
  agentChatApi: { welcome },
}));

// Local override of the shared react-i18next mock so one case can flip the
// active language and observe the welcome request that it triggers.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() {
        return i18nState.language;
      },
      changeLanguage: () => Promise.resolve(),
    },
  }),
  Trans: ({ children }: { children?: unknown }) => children,
}));

import type { ChatWelcomeResponse } from "../../../api/modules/agentChat";
import type { OctopAgent } from "../../../context/AgentContext";
import { useExpertChatWelcome } from "./useExpertQuickCards";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const agentA = { agent_id: "agent-a" } as unknown as OctopAgent;
const agentB = { agent_id: "agent-b" } as unknown as OctopAgent;

const ALPHA: ChatWelcomeResponse = {
  welcome_message: { zh: "Alpha欢迎", en: "Alpha welcome" },
  quick_prompts: [
    {
      title: { zh: "Alpha任务", en: "Alpha task" },
      description: { zh: "Alpha描述", en: "Alpha description" },
      prompt: { zh: "Alpha提示", en: "Alpha prompt" },
    },
  ],
};

const BETA: ChatWelcomeResponse = {
  welcome_message: { zh: "Beta欢迎", en: "Beta welcome" },
  quick_prompts: [
    {
      title: { zh: "Beta任务", en: "Beta task" },
      description: { zh: "Beta描述", en: "Beta description" },
      prompt: { zh: "Beta提示", en: "Beta prompt" },
    },
  ],
};

function renderWelcome(agent: OctopAgent | null) {
  return renderHook(
    ({ current }: { current: OctopAgent | null }) =>
      useExpertChatWelcome(current),
    { initialProps: { current: agent } },
  );
}

describe("useExpertChatWelcome", () => {
  beforeEach(() => {
    i18nState.language = "zh";
    welcome.mockReset();
  });

  it("drops the previous expert's welcome while the next request is pending", async () => {
    const alpha = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(alpha.promise);
    const { result, rerender } = renderWelcome(agentA);

    await act(async () => {
      alpha.resolve(ALPHA);
    });
    await waitFor(() => expect(result.current.quickCards).toHaveLength(1));
    expect(result.current.welcomeSuffix).toBe("Alpha欢迎");

    const beta = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(beta.promise);
    rerender({ current: agentB });

    expect(result.current.quickCards).toEqual([]);
    expect(result.current.welcomeSuffix).toBeNull();

    await act(async () => {
      beta.resolve(BETA);
    });
    await waitFor(() => expect(result.current.welcomeSuffix).toBe("Beta欢迎"));
    expect(result.current.quickCards[0]?.title).toBe("Beta任务");
  });

  it("drops the previous welcome while the request for a new language is pending", async () => {
    const alpha = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(alpha.promise);
    const { result, rerender } = renderWelcome(agentA);

    await act(async () => {
      alpha.resolve(ALPHA);
    });
    await waitFor(() => expect(result.current.welcomeSuffix).toBe("Alpha欢迎"));

    const translated = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(translated.promise);
    i18nState.language = "en";
    rerender({ current: agentA });

    expect(result.current.quickCards).toEqual([]);
    expect(result.current.welcomeSuffix).toBeNull();

    await act(async () => {
      translated.resolve(ALPHA);
    });
    await waitFor(() =>
      expect(result.current.welcomeSuffix).toBe("Alpha welcome"),
    );
    expect(result.current.quickCards[0]?.title).toBe("Alpha task");
  });

  it("ignores a late response from the expert it was switched away from", async () => {
    const alpha = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(alpha.promise);
    const { result, rerender } = renderWelcome(agentA);

    const beta = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(beta.promise);
    rerender({ current: agentB });

    await act(async () => {
      beta.resolve(BETA);
    });
    await waitFor(() => expect(result.current.welcomeSuffix).toBe("Beta欢迎"));

    await act(async () => {
      alpha.resolve(ALPHA);
    });
    expect(result.current.welcomeSuffix).toBe("Beta欢迎");
    expect(result.current.quickCards[0]?.title).toBe("Beta任务");
  });

  it("clears the welcome when no expert is selected", async () => {
    const alpha = deferred<ChatWelcomeResponse>();
    welcome.mockReturnValueOnce(alpha.promise);
    const { result, rerender } = renderWelcome(agentA);

    await act(async () => {
      alpha.resolve(ALPHA);
    });
    await waitFor(() => expect(result.current.quickCards).toHaveLength(1));

    rerender({ current: null });

    expect(result.current.quickCards).toEqual([]);
    expect(result.current.welcomeSuffix).toBeNull();
  });
});
