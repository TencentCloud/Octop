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
  sessionStorage.clear();
  // GET list -> empty; POST create -> server-echoed row with enabled=1
  api.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return { id: "c1", kind: "telegram", name: "telegram", enabled: true };
    }
    return [];
  });
});

describe("<ChannelsPanel /> create-flow default", () => {
  it("defaults Discord to all channels and saves without channel IDs", async () => {
    render(<ChannelsPanel agentId="ag1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: /channels\.showMoreChannels/ }),
    );
    await userEvent.click(
      (await screen.findAllByText("channels.label_discord"))[0],
    );
    expect(
      await screen.findByLabelText("channels.discordAllowAllChannels"),
    ).toBeChecked();
    expect(
      screen.getByLabelText("channels.discordAllowedChannels"),
    ).toBeDisabled();
    expect(screen.getByLabelText("channels.discordAllowedUsers")).toBeEnabled();
    await userEvent.type(
      screen.getByLabelText(/Bot Token/i),
      "fake-discord-token",
    );
    await userEvent.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() => {
      const post = api.mock.calls.find(([, init]) => init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(String(post![1]!.body)).config).toMatchObject({
        bot_token: "fake-discord-token",
        allow_all_channels: true,
      });
    });
  });

  it.each([undefined, true, false])(
    "loads and saves Discord all-channels setting %s without losing boolean false",
    async (allowAll) => {
      const row = { id: "d1", kind: "discord", name: "discord", enabled: true };
      api.mockImplementation(async (url, init) => {
        if (init?.method === "PATCH") return row;
        if (url.endsWith("/d1"))
          return {
            ...row,
            config: {
              bot_token: "fake",
              ...(allowAll === undefined
                ? {}
                : { allow_all_channels: allowAll }),
              allowed_channel_ids: ["1234567890123456789"],
            },
          };
        return [row];
      });
      render(<ChannelsPanel agentId="ag1" />);
      await userEvent.click(
        (await screen.findAllByText("channels.label_discord"))[0],
      );
      const toggle = await screen.findByLabelText(
        "channels.discordAllowAllChannels",
      );
      expect(toggle.getAttribute("aria-checked")).toBe(
        String(allowAll ?? true),
      );
      const ids = screen.getByLabelText("channels.discordAllowedChannels");
      expect(ids).toHaveValue("1234567890123456789");
      if (allowAll === false) expect(ids).toBeEnabled();
      else expect(ids).toBeDisabled();
      await userEvent.click(
        screen.getByRole("button", { name: "common.save" }),
      );
      await waitFor(() => {
        const patch = api.mock.calls.find(
          ([, init]) => init?.method === "PATCH",
        );
        expect(patch).toBeDefined();
        expect(JSON.parse(String(patch![1]!.body)).config).toMatchObject({
          allow_all_channels: allowAll ?? true,
          allowed_channel_ids: ["1234567890123456789"],
        });
      });
    },
  );

  it("opens Discord and saves the token with exact channel/user IDs", async () => {
    render(<ChannelsPanel agentId="ag1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: /channels\.showMoreChannels/ }),
    );
    await userEvent.click(
      (await screen.findAllByText("channels.label_discord"))[0],
    );
    expect(
      await screen.findByText("channels.discordSetupHelp"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByLabelText("channels.discordAllowAllChannels"),
    );
    expect(
      screen.getByLabelText("channels.discordAllowedChannels"),
    ).toBeEnabled();
    await userEvent.type(
      await screen.findByLabelText(/Bot Token/i),
      "fake-discord-token",
    );
    await userEvent.type(
      screen.getByLabelText("channels.discordAllowedChannels"),
      "1234567890123456789,2345678901234567890",
    );
    await userEvent.type(
      screen.getByLabelText("channels.discordAllowedUsers"),
      "3456789012345678901",
    );
    await userEvent.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() => {
      const post = api.mock.calls.find(([, init]) => init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({
        kind: "discord",
        config: {
          bot_token: "fake-discord-token",
          allow_all_channels: false,
          allowed_channel_ids: ["1234567890123456789", "2345678901234567890"],
          allowed_user_ids: ["3456789012345678901"],
        },
      });
    });
  });

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
