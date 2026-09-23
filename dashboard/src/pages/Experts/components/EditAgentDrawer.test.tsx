import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { request } from "../../../api/request";
import type { OctopAgent } from "../../../context/AgentContext";
import { useAgent } from "../../../context/AgentContext";
import EditAgentDrawer from "./EditAgentDrawer";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: vi.fn(),
}));

// The drawer's load effect keeps ``t`` in its dependency array, so ``t`` must
// keep one identity across renders (as it does with real i18next).
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  const t = (key: string) => key;
  return {
    ...actual,
    useTranslation: () => ({
      t,
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
  };
});

// The drawer renders the workspace file preview, and react-pdf's module body
// needs browser APIs jsdom does not provide.
vi.mock("react-pdf", async () => {
  const React = await import("react");
  return {
    Document: ({ children }: { children?: React.ReactNode }) => (
      <div>{children}</div>
    ),
    Page: () => null,
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
  };
});

const AGENT_ID = "AGT_LIMITS";

const DETAIL = {
  id: 7,
  agent_id: AGENT_ID,
  name: "Limits",
  description: null,
  default_model: null,
  config: { max_input_length: 64000, tools_disabled: ["bash"] },
  max_iters: 10,
  max_input_length: 64000,
  temperature: 0.3,
  top_p: 0.9,
  max_tokens: 4096,
};

const agent = {
  id: 7,
  agent_id: AGENT_ID,
  name: "Limits",
  description: null,
  persona_mbti: null,
  default_model: null,
  system_prompt: null,
  template_name: null,
  state: "stopped",
  last_error: null,
  icon: null,
  icon_name: null,
  icon_url: null,
  color: null,
  config: {},
} as unknown as OctopAgent;

function patchBody(): Record<string, unknown> | null {
  const call = vi
    .mocked(request)
    .mock.calls.find(
      ([path, init]) =>
        path === `/agents/${AGENT_ID}` && init?.method === "PATCH",
    );
  if (!call) return null;
  return JSON.parse(String(call[1]?.body)) as Record<string, unknown>;
}

async function waitForSaveButton() {
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "common.save" }),
    ).toBeInTheDocument();
  });
}

async function clickSave() {
  await waitForSaveButton();
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
}

async function savedBody(): Promise<Record<string, unknown>> {
  await waitFor(() => {
    expect(patchBody()).not.toBeNull();
  });
  return patchBody() as Record<string, unknown>;
}

async function expandAdvancedPanel() {
  fireEvent.click(await screen.findByText("experts.advancedOptions"));
  return screen.findByLabelText("agentConfig.maxIters");
}

describe("EditAgentDrawer runtime limits", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAgent).mockReturnValue({
      refresh: vi.fn(),
      agents: [],
    } as never);
    vi.mocked(request).mockImplementation((async (path: string) => {
      if (path === `/agents/${AGENT_ID}`) return DETAIL;
      return [];
    }) as never);
  });

  function openDrawer() {
    return render(
      <App>
        <EditAgentDrawer
          open
          agent={agent}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />
      </App>,
    );
  }

  it("keeps the stored limits when the advanced panel was never expanded (#810)", async () => {
    openDrawer();
    await clickSave();

    const body = await savedBody();
    expect(body).toMatchObject({
      max_iters: 10,
      max_input_length: 64000,
      temperature: 0.3,
      top_p: 0.9,
      max_tokens: 4096,
    });
    // The rest of the payload is untouched: opaque config keys survive a save.
    expect((body.config as Record<string, unknown>).tools_disabled).toEqual([
      "bash",
    ]);
  });

  it("still sends null for a limit the user cleared in the panel", async () => {
    openDrawer();
    const maxIters = await expandAdvancedPanel();
    fireEvent.change(maxIters, { target: { value: "" } });
    await clickSave();

    const body = await savedBody();
    expect(body.max_iters).toBeNull();
    expect(body.max_input_length).toBe(64000);
  });

  it("sends the limit the user typed into the panel", async () => {
    openDrawer();
    const maxIters = await expandAdvancedPanel();
    fireEvent.change(maxIters, { target: { value: "99" } });
    await clickSave();

    expect((await savedBody()).max_iters).toBe(99);
  });
});
