/**
 * BridgeSettings peer masking.
 *
 * The connection cards are the usual screen-share surface, so peer address and
 * account are masked by default, with a master switch and a per-card reveal.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../../api/modules/bridge", () => ({
  bridgeApi: {
    list: vi.fn(),
    listAgents: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    remove: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ refresh: refreshAgents }),
}));

// The shared setup mocks ``t`` as a fresh arrow per call; the panel keeps it in
// effect/callback deps, so an unstable ``t`` would re-run the polling effect on
// every render and replace the DOM nodes a click is aimed at.
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return {
    useTranslation: () => ({ t, i18n: { language: "zh" } }),
    Trans: ({ children }: { children?: React.ReactNode }) => children,
  };
});

import { bridgeApi } from "../../../api/modules/bridge";
import BridgeSettingsPanel from "./BridgeSettings";

const refreshAgents = vi.fn();
const api = vi.mocked(bridgeApi, true);

const OUTBOUND = {
  connection_id: "outbound-1",
  peer_base_url: "https://demo.octop.chat",
  peer_username: "alice",
  display_name: "demo",
  notes: null,
  icon_name: null,
  status: "connected",
  last_error: null,
  last_seen_at: null,
  auto_reconnect: false,
  created_at: 1,
  updated_at: 1,
  has_password: true,
  inbound: false,
};

const INBOUND = {
  connection_id: "inbound-1",
  peer_base_url: "http://127.0.0.1:8088",
  peer_username: "Deshun",
  display_name: "peer",
  notes: null,
  icon_name: null,
  status: "connected",
  last_error: null,
  last_seen_at: null,
  auto_reconnect: false,
  created_at: 1,
  updated_at: 1,
  has_password: false,
  inbound: true,
  peer_client_host: "203.0.113.8",
};

function renderPanel(initialEntry = "/bridge") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <BridgeSettingsPanel />
    </MemoryRouter>,
  );
}

function revealButtons() {
  return screen.findAllByRole("button", {
    name: "advancedSettings.bridge.revealPeerInfo",
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.list.mockResolvedValue([OUTBOUND, INBOUND] as never);
  api.listAgents.mockResolvedValue([] as never);
});

describe("<BridgeSettingsPanel /> create query", () => {
  it("opens the add drawer from ?create=1", async () => {
    renderPanel("/bridge?create=1");
    expect(
      await screen.findByText("advancedSettings.bridge.drawerHint"),
    ).toBeInTheDocument();
  });
});

describe("<BridgeSettingsPanel /> peer masking", () => {
  it("masks address and account by default", async () => {
    renderPanel();
    await waitFor(() => expect(api.list).toHaveBeenCalled());

    expect(await screen.findByText("de••••••at")).toBeInTheDocument();
    expect(screen.getByText("a••")).toBeInTheDocument();
    // Inbound cards mask the observed IP and the peer account too.
    expect(screen.getByText("203.•••.•••.8")).toBeInTheDocument();
    expect(screen.getByText("De••••••un")).toBeInTheDocument();

    // The raw values stay in the copy/tooltip layer only, never as text.
    expect(screen.queryByText("demo.octop.chat")).not.toBeInTheDocument();
    expect(screen.queryByText("alice")).not.toBeInTheDocument();
    expect(screen.queryByText("Deshun")).not.toBeInTheDocument();
  });

  it("reveals a single card and keeps the others masked", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(api.list).toHaveBeenCalled());

    const buttons = await revealButtons();
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "false");

    await user.click(buttons[0]);

    expect(await screen.findByText("demo.octop.chat")).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    // The other card stays masked.
    expect(screen.getByText("De••••••un")).toBeInTheDocument();
    expect(screen.getByText("203.•••.•••.8")).toBeInTheDocument();
  });

  it("unmasks every card when the master switch is turned off", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(api.list).toHaveBeenCalled());

    expect(await screen.findByText("de••••••at")).toBeInTheDocument();
    await user.click(
      screen.getByRole("switch", {
        name: "advancedSettings.bridge.peerPrivacy",
      }),
    );

    expect(await screen.findByText("demo.octop.chat")).toBeInTheDocument();
    expect(screen.getByText("Deshun")).toBeInTheDocument();
    expect(screen.queryByText("de••••••at")).not.toBeInTheDocument();
    // No per-card reveal while masking is off.
    expect(
      screen.queryByRole("button", {
        name: "advancedSettings.bridge.revealPeerInfo",
      }),
    ).not.toBeInTheDocument();
  });

  it("remembers the master switch for the next session", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(api.list).toHaveBeenCalled());
    expect(localStorage.getItem("octop:bridge:hide-peer-info")).toBeNull();

    await user.click(
      screen.getByRole("switch", {
        name: "advancedSettings.bridge.peerPrivacy",
      }),
    );

    expect(localStorage.getItem("octop:bridge:hide-peer-info")).toBe("0");
  });
});
