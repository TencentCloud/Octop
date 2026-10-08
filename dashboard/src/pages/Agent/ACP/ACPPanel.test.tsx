/**
 * ACPPanel.test.tsx — re-adding a disabled runner key.
 *
 * Regression test for the "disabled runner cannot be re-created" bug: the
 * save guard rejected any existing runner key, so a custom runner the user
 * had disabled could never be added again under the same name.
 *
 * Contract under test (create drawer):
 *   - a disabled custom key is overwritable; saving re-enables it (PUT)
 *   - an enabled custom key still collides (error toast, no PUT)
 *   - a disabled builtin key still collides (error toast, no PUT)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

import { request } from "../../../api/request";
import type { ACPRunnerConfig } from "../../../api/types/acp";
import { ACPPanel } from "./index";

const api = vi.mocked(request, true);

function runnerConfig(enabled: boolean): ACPRunnerConfig {
  return {
    enabled,
    command: "minimax-acp",
    args: [],
    env: {},
    trusted: true,
    tool_parse_mode: "update_detail",
    stdio_buffer_limit_bytes: 50 * 1024 * 1024,
  };
}

function mockApi(runners: Record<string, ACPRunnerConfig>) {
  api.mockImplementation(async (url, init) => {
    if (url === "/acp") {
      if (init?.method === "PUT") {
        return { runners: JSON.parse(String(init.body)).runners };
      }
      return { runners };
    }
    if (url.startsWith("/agents/ag1/acp")) {
      return { tool_enabled: false };
    }
    return {};
  });
}

/** Render the panel, wait for the seeded runner card, open the create
 * drawer and fill the runner key + command. */
async function openCreateDrawerWith(cardText: string, runnerKey: string) {
  render(
    <App>
      <ACPPanel agentId="ag1" />
    </App>,
  );
  await screen.findByText(cardText);
  await userEvent.click(screen.getByRole("button", { name: "acp.create" }));
  await userEvent.type(await screen.findByLabelText("acp.runnerKey"), runnerKey);
  await userEvent.type(screen.getByLabelText("acp.command"), "minimax-acp");
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<ACPPanel /> runner key guard", () => {
  it("re-adds a disabled custom runner and re-enables it", async () => {
    mockApi({ minimax_code: runnerConfig(false) });
    await openCreateDrawerWith("acp.runner_custom", "minimax_code");

    await userEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      const put = api.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
      );
      expect(put).toBeDefined();
      const body = JSON.parse(String((put![1] as RequestInit).body));
      expect(body.runners.minimax_code).toMatchObject({
        enabled: true,
        command: "minimax-acp",
      });
    });
  });

  it("still rejects saving over an enabled custom runner", async () => {
    mockApi({ minimax_code: runnerConfig(true) });
    await openCreateDrawerWith("acp.runner_custom", "minimax_code");

    await userEvent.click(screen.getByRole("button", { name: "common.save" }));

    expect(await screen.findByText("acp.runnerKeyExists")).toBeInTheDocument();
    expect(
      api.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
      ),
    ).toBeUndefined();
  });

  it("still rejects saving over a disabled builtin runner", async () => {
    mockApi({ opencode: runnerConfig(false) });
    await openCreateDrawerWith("acp.runner_opencode", "opencode");

    await userEvent.click(screen.getByRole("button", { name: "common.save" }));

    expect(await screen.findByText("acp.runnerKeyExists")).toBeInTheDocument();
    expect(
      api.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
      ),
    ).toBeUndefined();
  });
});
