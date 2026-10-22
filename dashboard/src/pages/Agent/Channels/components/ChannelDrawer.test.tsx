import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Form } from "antd";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { channelApi } from "../../../../api/modules/channel";
import { draftStorageKey } from "../../../../utils/formDraft";
import { ChannelDrawer, type ChannelFormValues } from "./ChannelDrawer";
import type { ChannelKey } from "./constants";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const onSubmit = vi.fn().mockResolvedValue(true);
const onProvisioned = vi.fn();

function Harness({
  open = true,
  kind = "dingtalk",
}: {
  open?: boolean;
  kind?: ChannelKey;
}) {
  const [form] = Form.useForm<ChannelFormValues>();
  return (
    <ChannelDrawer
      open={open}
      editing={null}
      loadingConfig={false}
      initialValues={{ kind, enabled: true }}
      form={form}
      saving={false}
      onClose={vi.fn()}
      onSubmit={onSubmit}
      onProvisioned={onProvisioned}
      agentId="ag1"
    />
  );
}

let intervals: ReturnType<typeof vi.spyOn<typeof globalThis, "setInterval">>;

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  intervals = vi.spyOn(globalThis, "setInterval");
  vi.spyOn(channelApi, "dingtalkQrcodeGenerate").mockImplementation(
    () => new Promise(() => {}),
  );
  vi.spyOn(channelApi, "weixinQrcodeGenerate").mockImplementation(
    () => new Promise(() => {}),
  );
});

afterEach(() => {
  for (const result of intervals.mock.results) {
    if (result.type === "return") clearInterval(result.value);
  }
  intervals.mockRestore();
  for (const method of Object.values(channelApi)) {
    if (vi.isMockFunction(method)) method.mockRestore();
  }
});

async function selectKind(label: string) {
  fireEvent.mouseDown(screen.getByRole("combobox"));
  await userEvent.click(
    await screen.findByText(label, {
      selector: ".ant-select-item-option-content",
    }),
  );
}

describe("channel QR flow lifecycle", () => {
  it("ignores a draft whose kind does not match its storage scope", async () => {
    sessionStorage.setItem(
      draftStorageKey("channel:new:dingtalk"),
      JSON.stringify({ kind: "weixin", client_id: "wrong-kind" }),
    );
    render(<Harness />);
    await userEvent.click(screen.getByText("channels.manualConfig"));
    expect(screen.getByLabelText("Client ID")).toHaveValue("");
    expect(channelApi.weixinQrcodeGenerate).not.toHaveBeenCalled();
  });

  it("keeps drafts scoped to their kind when switching DingTalk to WeChat and back", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByText("channels.manualConfig"));
    await userEvent.type(
      screen.getByLabelText("Client ID"),
      "saved-dingtalk-id",
    );
    await selectKind("微信");

    expect(
      JSON.parse(
        sessionStorage.getItem(draftStorageKey("channel:new:dingtalk"))!,
      ),
    ).toMatchObject({
      kind: "dingtalk",
      client_id: "saved-dingtalk-id",
    });
    await waitFor(() =>
      expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(1),
    );
    await selectKind("钉钉");
    expect(await screen.findByLabelText("Client ID")).toHaveValue(
      "saved-dingtalk-id",
    );
    expect(channelApi.dingtalkQrcodeGenerate).toHaveBeenCalledTimes(1);
    expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(1);
  });

  it.each(["resolve", "reject"] as const)(
    "ignores a QR generation %s after the drawer closes",
    async (result) => {
      const generation =
        deferred<Awaited<ReturnType<typeof channelApi.weixinQrcodeGenerate>>>();
      vi.mocked(channelApi.weixinQrcodeGenerate).mockReturnValue(
        generation.promise,
      );
      const view = render(<Harness kind="weixin" />);
      await waitFor(() =>
        expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(1),
      );
      view.rerender(<Harness kind="weixin" open={false} />);
      await act(async () => {
        if (result === "resolve")
          generation.resolve({
            qrcode_token: "stale",
            qrcode_url: "https://example.com/stale",
          });
        else generation.reject(new Error("stale generation failure"));
      });

      expect(
        intervals.mock.calls.filter(([, delay]) => delay === 3000),
      ).toHaveLength(0);
      view.rerender(<Harness kind="weixin" />);
      await waitFor(() =>
        expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(2),
      );
    },
  );

  it("ignores a pending scan result after close and does not auto-save its credentials", async () => {
    vi.mocked(channelApi.weixinQrcodeGenerate).mockResolvedValue({
      qrcode_token: "scan",
      qrcode_url: "https://example.com/scan",
    });
    const scan =
      deferred<Awaited<ReturnType<typeof channelApi.weixinQrcodePoll>>>();
    vi.spyOn(channelApi, "weixinQrcodePoll").mockReturnValue(scan.promise);
    const view = render(<Harness kind="weixin" />);
    await waitFor(() =>
      expect(intervals.mock.calls.some(([, delay]) => delay === 3000)).toBe(
        true,
      ),
    );
    const callback = intervals.mock.calls.find(
      ([, delay]) => delay === 3000,
    )![0];
    expect(typeof callback).toBe("function");
    act(() => {
      if (typeof callback === "function") void callback();
    });
    view.rerender(<Harness kind="weixin" open={false} />);
    await act(async () => {
      scan.resolve({
        status: "success",
        account_id: "old-account",
        token: "old-token",
      });
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not start polling when generation finishes after unmount", async () => {
    const generation =
      deferred<Awaited<ReturnType<typeof channelApi.weixinQrcodeGenerate>>>();
    vi.mocked(channelApi.weixinQrcodeGenerate).mockReturnValue(
      generation.promise,
    );
    const view = render(<Harness kind="weixin" />);
    await waitFor(() =>
      expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(1),
    );
    view.unmount();
    await act(async () => {
      generation.resolve({
        qrcode_token: "unmounted",
        qrcode_url: "https://example.com/unmounted",
      });
    });
    expect(
      intervals.mock.calls.filter(([, delay]) => delay === 3000),
    ).toHaveLength(0);
  });

  it("discards a pending WeChat generation when switching back to manual DingTalk", async () => {
    const generation =
      deferred<Awaited<ReturnType<typeof channelApi.weixinQrcodeGenerate>>>();
    vi.mocked(channelApi.weixinQrcodeGenerate).mockReturnValue(
      generation.promise,
    );
    render(<Harness />);
    await userEvent.click(screen.getByText("channels.manualConfig"));
    await selectKind("微信");
    await waitFor(() =>
      expect(channelApi.weixinQrcodeGenerate).toHaveBeenCalledTimes(1),
    );
    await selectKind("钉钉");
    await act(async () => {
      generation.resolve({
        qrcode_token: "switched",
        qrcode_url: "https://example.com/switched",
      });
    });
    expect(screen.getByLabelText("Client ID")).toBeInTheDocument();
    expect(
      intervals.mock.calls.filter(([, delay]) => delay === 3000),
    ).toHaveLength(0);
  });

  it("still auto-saves a current scan once under Strict Mode and stops its timer", async () => {
    vi.mocked(channelApi.weixinQrcodeGenerate).mockResolvedValue({
      qrcode_token: "current-scan",
      qrcode_url: "https://example.com/current",
    });
    vi.spyOn(channelApi, "weixinQrcodePoll").mockResolvedValue({
      status: "success",
      account_id: "current-account",
      token: "current-token",
    });
    const clear = vi.spyOn(globalThis, "clearInterval");
    render(
      <StrictMode>
        <Harness kind="weixin" />
      </StrictMode>,
    );
    await waitFor(() =>
      expect(
        intervals.mock.calls.filter(([, delay]) => delay === 3000),
      ).toHaveLength(1),
    );
    const index = intervals.mock.calls.findIndex(([, delay]) => delay === 3000);
    const callback = intervals.mock.calls[index][0];
    await act(async () => {
      if (typeof callback === "function") await callback();
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(
      "weixin",
      "weixin",
      expect.objectContaining({ token: "current-token" }),
      true,
    );
    expect(clear).toHaveBeenCalledWith(intervals.mock.results[index].value);
    clear.mockRestore();
  });
});
