/**
 * ChannelsPanel.test.tsx — manual create-flow default enablement.
 *
 * Regression test for the "channel born disabled" bug: the create drawer's
 * enable switch used to default OFF while the server-side create always
 * writes enabled=1. Saving then fired a follow-up PATCH {enabled: false},
 * producing a born-disabled row (created_at == updated_at) with no warning —
 * the bot looked "muted" from then on.
 *
 * Contract under test:
 *   - create drawer opens with the enable switch ON
 *   - saving a new channel sends exactly one POST (no PATCH churn)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

import { request } from "../../../api/request";
import ChannelsPanel from "./ChannelsPanel";

const api = vi.mocked(request, true);

beforeEach(() => {
  vi.clearAllMocks();
  // GET list -> empty; POST create -> server-echoed row with enabled=1
  api.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return { id: "c1", kind: "telegram", name: "telegram", enabled: true };
    }
    return [];
  });
});

describe("<ChannelsPanel /> create-flow default", () => {
  async function openTelegramCreateDrawer() {
    render(<ChannelsPanel agentId="ag1" />);
    // Telegram is collapsed behind "更多通道" until expanded.
    await userEvent.click(
      await screen.findByRole("button", {
        name: /channels\.showMoreChannels/,
      }),
    );
    // telegram has no quick-config path -> clicking its card opens the
    // manual create drawer directly.
    const card = (await screen.findAllByText("channels.label_telegram"))[0];
    await userEvent.click(card);
  }

  it("opens the create drawer with the enable switch ON", async () => {
    await openTelegramCreateDrawer();

    // the drawer's "Enable channel" switch (Form.Item wires label<->control)
    const sw = await screen.findByLabelText("channels.enableChannel");
    expect(sw.getAttribute("aria-checked")).toBe("true");
  });

  it("saves a new channel with a single POST and no follow-up PATCH", async () => {
    await openTelegramCreateDrawer();

    await userEvent.type(
      await screen.findByLabelText(/Bot Token/i),
      "123456:ABC-token",
    );
    await userEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      const post = api.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeDefined();
    });

    // server echoes the created row, enabled=1 == requested true ->
    // the "align enablement" PATCH must NOT fire
    const patch = api.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patch).toBeUndefined();

    const [, init] = api.mock.calls.find(
      ([, i]) => (i as RequestInit | undefined)?.method === "POST",
    ) as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      kind: "telegram",
      name: "telegram",
      config: expect.objectContaining({ bot_token: "123456:ABC-token" }),
    });
  });

  it("still honors a deliberate opt-out: unchecking fires the alignment PATCH", async () => {
    await openTelegramCreateDrawer();

    await userEvent.type(
      await screen.findByLabelText(/Bot Token/i),
      "123456:ABC-token",
    );
    // user explicitly turns the switch off before saving
    await userEvent.click(screen.getByLabelText("channels.enableChannel"));
    await userEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      const patch = api.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
      );
      expect(patch).toBeDefined();
      expect(String((patch![1] as RequestInit).body)).toBe(
        JSON.stringify({ enabled: false }),
      );
    });
  });
});
