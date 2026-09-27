import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AuthorizationPageNotice,
  useAuthorizationPage,
} from "./useAuthorizationPage";
import { copyText } from "../../../utils/copyText";

vi.mock("../../../utils/copyText", () => ({ copyText: vi.fn() }));
const url =
  "https://auth.example.test/authorize?state=test-state&code_challenge=test-pkce";
type DesktopWindow = Window & { _wails?: { invoke: (value: string) => void } };

afterEach(() => {
  delete (window as DesktopWindow)._wails;
  vi.restoreAllMocks();
});

describe("connector authorization browser handoff", () => {
  it("opens the real URL via the native bridge without a blank WebView popup", () => {
    const invoke = vi.fn();
    (window as DesktopWindow)._wails = { invoke };
    const open = vi.spyOn(window, "open");
    const { result } = renderHook(() => useAuthorizationPage());
    act(() => result.current.begin().navigate(url));
    expect(open).not.toHaveBeenCalled();
    expect(invoke).toHaveBeenCalledWith(
      "wails:event:emit:desktop:open-url:" + encodeURIComponent(url),
    );
    expect(result.current.notice).not.toBeNull();
    render(result.current.notice);
    expect(screen.getByRole("link")).not.toHaveAttribute("target");
  });

  it("reserves a browser popup before the asynchronous authorization URL arrives", async () => {
    const replace = vi.fn();
    const close = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({
      closed: false,
      location: { replace },
      close,
    } as unknown as Window);
    const { result } = renderHook(() => useAuthorizationPage());
    let page!: ReturnType<typeof result.current.begin>;
    act(() => {
      page = result.current.begin();
    });
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalled();
    await act(async () => {
      await Promise.resolve();
      page.navigate(url);
    });
    expect(replace).toHaveBeenCalledWith(url);
    act(() => page.close());
    expect(close).toHaveBeenCalledOnce();
    expect(result.current.notice).toBeNull();
  });

  it("keeps a clickable URL and copy control when the popup is blocked", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { result } = renderHook(() => useAuthorizationPage());
    act(() => result.current.begin().navigate(url));
    render(result.current.notice);
    expect(
      screen.getByText("connectors.authBrowserBlocked"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", url);
    expect(screen.getByRole("link")).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    vi.mocked(copyText).mockResolvedValue(true);
    await act(async () =>
      fireEvent.click(
        screen.getByRole("button", { name: "connectors.authLinkCopy" }),
      ),
    );
    expect(copyText).toHaveBeenCalledWith(url);
    expect(screen.getByText("connectors.authLinkCopied")).toBeInTheDocument();
  });

  it("offers recovery when native browser dispatch throws", () => {
    (window as DesktopWindow)._wails = {
      invoke: () => {
        throw new Error("bridge unavailable");
      },
    };
    const { result } = renderHook(() => useAuthorizationPage());
    act(() => result.current.begin().navigate(url + "&retry=1"));
    render(result.current.notice);
    expect(
      screen.getByText("connectors.authBrowserBlocked"),
    ).toBeInTheDocument();
  });

  it("exposes a selectable link if clipboard access fails", async () => {
    vi.mocked(copyText).mockResolvedValue(false);
    render(<AuthorizationPageNotice url={url} blocked />);
    await act(async () =>
      fireEvent.click(
        screen.getByRole("button", { name: "connectors.authLinkCopy" }),
      ),
    );
    expect(screen.getByRole("textbox")).toHaveValue(url);
  });

  it.each(["close", "unmount", "cancel"])(
    "stops the caller and ignores delayed URL responses on %s",
    (mode) => {
      const popupClose = vi.fn();
      const replace = vi.fn();
      vi.spyOn(window, "open").mockReturnValue({
        close: popupClose,
        location: { replace },
      } as unknown as Window);
      const cleanup = vi.fn();
      const { result, rerender, unmount } = renderHook(
        ({ enabled }) => useAuthorizationPage(enabled),
        { initialProps: { enabled: true } },
      );
      let page!: ReturnType<typeof result.current.begin>;
      act(() => {
        page = result.current.begin(cleanup);
      });
      if (mode === "unmount") unmount();
      else if (mode === "close") rerender({ enabled: false });
      else {
        act(() => page.navigate(url));
        render(result.current.notice);
        fireEvent.click(
          screen.getByRole("button", { name: "connectors.authBrowserCancel" }),
        );
      }
      expect(cleanup).toHaveBeenCalledOnce();
      expect(popupClose).toHaveBeenCalledOnce();
      expect(page.active).toBe(false);
      act(() => page.navigate(url));
      expect(replace).toHaveBeenCalledTimes(mode === "cancel" ? 1 : 0);
    },
  );

  it("never exposes executable authorization URLs", () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { result } = renderHook(() => useAuthorizationPage());
    let page!: ReturnType<typeof result.current.begin>;
    act(() => {
      page = result.current.begin();
    });
    expect(() => page.navigate("javascript:alert(1)")).toThrow();
    expect(result.current.notice).toBeNull();
  });
});
