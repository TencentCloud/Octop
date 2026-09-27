import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectorConfigDrawer } from "./index";
import {
  connectorsApi,
  type ConnectorCatalogEntry,
} from "../../../api/modules/connectors";

vi.mock("./oauthCallback", () => ({ oauthCallbackSupported: () => true }));
vi.mock("../../../api/modules/connectors", () => ({
  connectorsApi: {
    authInfo: vi.fn(),
    oauthStart: vi.fn(),
    oauthPending: vi.fn(),
    createInstance: vi.fn(),
    authorizeUrl: vi.fn(),
  },
}));
const entry: ConnectorCatalogEntry = {
  kind: "qcc",
  name: "企查查",
  description: "test",
  auth_kind: "oauth2",
  oauth_ready: true,
  doc_url: "",
  icon: "",
  color: "",
  phase: "available",
  mcp_mode: "internal",
  category: "professional",
};
const url = "https://auth.example.test/start?state=catalog-test";
const invoke = vi.fn();
const onSaved = vi.fn();
const props = { open: true, entry, instance: null, onClose: vi.fn(), onSaved };
const flush = () =>
  act(async () => {
    await Promise.resolve();
  });

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  (window as Window & { _wails?: unknown })._wails = { invoke };
  vi.spyOn(window, "open").mockReturnValue(null);
  vi.mocked(connectorsApi.authInfo).mockResolvedValue({
    authorize_url: url,
    login_url: null,
    guide_url: null,
    manual_url: null,
    auth_hint: null,
  });
  vi.mocked(connectorsApi.oauthStart).mockResolvedValue({
    authorize_url: url,
    state_id: "catalog-state",
  });
  vi.mocked(connectorsApi.oauthPending).mockRejectedValue(new Error("pending"));
  vi.mocked(connectorsApi.createInstance).mockResolvedValue({} as never);
});
afterEach(() => {
  delete (window as Window & { _wails?: unknown })._wails;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("catalog OAuth in the desktop shell", () => {
  it.each(["qcc", "notion"])(
    "polls and saves %s without a popup or postMessage",
    async (kind) => {
      render(<ConnectorConfigDrawer {...props} entry={{ ...entry, kind }} />);
      await flush();
      fireEvent.click(screen.getByRole("button", { name: "一键授权" }));
      await flush();
      expect(connectorsApi.oauthStart).toHaveBeenCalledWith(
        { type: "catalog", kind },
        "/connectors",
      );
      expect(window.open).not.toHaveBeenCalled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(onSaved).not.toHaveBeenCalled();
      vi.mocked(connectorsApi.oauthPending).mockResolvedValue({
        kind,
        tokens: { access_token: "test-access", refresh_token: "test-refresh" },
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(connectorsApi.createInstance).toHaveBeenCalledWith(
        expect.objectContaining({
          kind,
          credentials: {
            access_token: "test-access",
            refresh_token: "test-refresh",
          },
        }),
      );
      expect(onSaved).toHaveBeenCalledOnce();
      const count = vi.mocked(connectorsApi.oauthPending).mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(connectorsApi.oauthPending).toHaveBeenCalledTimes(count);
    },
  );

  it("opens the alternate authorization page with the desktop browser bridge", async () => {
    vi.mocked(connectorsApi.authorizeUrl).mockResolvedValue({
      authorize_url: url + "&manual=1",
    });
    render(<ConnectorConfigDrawer {...props} />);
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "打开授权页" }));
    await flush();
    expect(invoke).toHaveBeenCalledWith(
      "wails:event:emit:desktop:open-url:" +
        encodeURIComponent(url + "&manual=1"),
    );
    expect(window.open).not.toHaveBeenCalled();
  });

  it("does not save an in-flight pending result after the drawer closes", async () => {
    let resolve!: (value: {
      kind: string;
      tokens: Record<string, unknown>;
    }) => void;
    vi.mocked(connectorsApi.oauthPending).mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const { rerender } = render(<ConnectorConfigDrawer {...props} />);
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "一键授权" }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(connectorsApi.oauthPending).toHaveBeenCalledOnce();
    rerender(<ConnectorConfigDrawer {...props} open={false} />);
    await act(async () =>
      resolve({ kind: "qcc", tokens: { access_token: "late-token" } }),
    );
    expect(connectorsApi.createInstance).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("clears polling and recovery links when authorization times out", async () => {
    render(<ConnectorConfigDrawer {...props} />);
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "一键授权" }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300_000);
    });
    expect(
      screen.queryByText("connectors.authLinkCopy"),
    ).not.toBeInTheDocument();
    const count = vi.mocked(connectorsApi.oauthPending).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(connectorsApi.oauthPending).toHaveBeenCalledTimes(count);
    expect(connectorsApi.createInstance).not.toHaveBeenCalled();
  });
});
