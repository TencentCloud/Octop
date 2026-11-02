import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/request", () => ({ request: vi.fn() }));

import { request } from "../../../api/request";
import { loadFormDraft, saveFormDraft } from "../../../utils/formDraft";
import ChannelsPanel from "./ChannelsPanel";

const api = vi.mocked(request, true);
let interval: ReturnType<typeof vi.spyOn>;
afterEach(() => interval?.mockRestore());

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.mockImplementation(async (_url, init) => {
    if (init?.method === "POST") return new Promise(() => {});
    return [];
  });
});

async function openDingtalkManual() {
  render(<ChannelsPanel agentId="ag1" />);
  await userEvent.click(
    (await screen.findAllByText("channels.label_dingtalk"))[0],
  );
  await userEvent.click(await screen.findByText("channels.manualConfig"));
}

async function selectKind(label: string) {
  await userEvent.click(screen.getByRole("combobox"));
  await userEvent.click(
    await screen.findByText(label, {
      selector: ".ant-select-item-option-content",
    }),
  );
}

describe("channel QR lifecycle (#2314)", () => {
  it("preserves per-kind drafts and allows switching back while QR generation is pending", async () => {
    await openDingtalkManual();
    await userEvent.type(screen.getByLabelText("Client ID"), "dingtalk-client");
    await selectKind("微信");
    expect(loadFormDraft("channel:new:dingtalk")).toMatchObject({
      kind: "dingtalk",
    });
    expect(loadFormDraft("channel:new:weixin")).toBeNull();
    await waitFor(() =>
      expect(
        api.mock.calls.filter(([url]) =>
          url.endsWith("weixin/qrcode/generate"),
        ),
      ).toHaveLength(1),
    );
    await selectKind("钉钉");
    expect(screen.getByLabelText("Client ID")).toHaveValue("dingtalk-client");
    expect(
      screen.queryByText("channels.weixinQrStep1"),
    ).not.toBeInTheDocument();
    expect(
      api.mock.calls.filter(([url]) => url.endsWith("weixin/qrcode/generate")),
    ).toHaveLength(1);
  });

  it("ignores a mismatched draft left by an earlier channel switch", async () => {
    saveFormDraft("channel:new:dingtalk", { kind: "weixin" });
    await openDingtalkManual();
    expect(screen.getByLabelText("Client ID")).toBeInTheDocument();
    expect(
      screen.queryByText("channels.weixinQrStep1"),
    ).not.toBeInTheDocument();
  });

  it.each(["resolve", "reject"])(
    "ignores a late QR generation %s after cancel and reopen",
    async (outcome) => {
      let resolve!: (value: {
        qrcode_token: string;
        qrcode_url: string;
      }) => void;
      let reject!: (reason: Error) => void;
      api.mockImplementation(async (url, init) => {
        if (url.endsWith("weixin/qrcode/generate"))
          return new Promise((res, rej) => {
            resolve = res;
            reject = rej;
          });
        if (init?.method === "POST") return new Promise(() => {});
        return [];
      });
      interval = vi.spyOn(globalThis, "setInterval");
      await openDingtalkManual();
      await selectKind("微信");
      await waitFor(() =>
        expect(
          api.mock.calls.filter(([url]) =>
            url.endsWith("weixin/qrcode/generate"),
          ),
        ).toHaveLength(1),
      );
      await userEvent.click(
        screen.getByRole("button", { name: "common.cancel" }),
      );
      await userEvent.click(
        (await screen.findAllByText("channels.label_dingtalk"))[0],
      );
      await act(async () => {
        if (outcome === "resolve")
          resolve({
            qrcode_token: "stale",
            qrcode_url: "https://example.com/stale",
          });
        else reject(new Error("stale QR failure"));
      });
      expect(screen.queryByText("stale QR failure")).not.toBeInTheDocument();
      expect(interval).not.toHaveBeenCalledWith(expect.any(Function), 3000);
      expect(
        screen.queryByText("channels.weixinQrStep1"),
      ).not.toBeInTheDocument();
    },
  );

  it("discards a pending poll success after switching back to manual DingTalk", async () => {
    let resolvePoll!: (value: { status: string; token: string }) => void;
    api.mockImplementation(async (url, init) => {
      if (url.endsWith("weixin/qrcode/generate"))
        return { qrcode_token: "qr1", qrcode_url: "https://example.com/qr1" };
      if (url.endsWith("weixin/qrcode/poll"))
        return new Promise((resolve) => {
          resolvePoll = resolve;
        });
      if (init?.method === "POST") return new Promise(() => {});
      return [];
    });
    interval = vi.spyOn(globalThis, "setInterval");
    await openDingtalkManual();
    await selectKind("微信");
    await waitFor(() =>
      expect(interval).toHaveBeenCalledWith(expect.any(Function), 3000),
    );
    const poll = interval.mock.calls.find(
      ([, delay]) => delay === 3000,
    )![0] as () => Promise<void>;
    let pending!: Promise<void>;
    act(() => {
      pending = poll();
    });
    await selectKind("钉钉");
    await act(async () => {
      resolvePoll({ status: "success", token: "stale-token" });
      await pending;
    });
    expect(screen.getByLabelText("Client ID")).toBeInTheDocument();
    expect(
      api.mock.calls.filter(
        ([url, init]) =>
          url === "/agents/ag1/channels" && init?.method === "POST",
      ),
    ).toHaveLength(0);
    const pollCalls = api.mock.calls.filter(([url]) =>
      url.endsWith("weixin/qrcode/poll"),
    ).length;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 3100));
    });
    expect(
      api.mock.calls.filter(([url]) => url.endsWith("weixin/qrcode/poll")),
    ).toHaveLength(pollCalls);
  });
});
