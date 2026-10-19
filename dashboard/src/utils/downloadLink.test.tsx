import { afterEach, describe, expect, it, vi } from "vitest";

import { requestUpload } from "../api/request";
import { modal } from "./antdModal";
import { copyText } from "./copyText";
import { shareDownloadLink } from "./downloadLink";

vi.mock("../api/config", () => ({
  getApiUrl: (path: string) => `/api${path}`,
}));
vi.mock("../api/request", () => ({ requestUpload: vi.fn() }));
vi.mock("./antdModal", () => ({ modal: { confirm: vi.fn() } }));
vi.mock("./copyText", () => ({ copyText: vi.fn() }));
vi.mock("./antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

afterEach(() => {
  vi.mocked(requestUpload).mockReset();
  vi.mocked(modal.confirm).mockReset();
  vi.mocked(copyText).mockReset();
});

describe("shareDownloadLink", () => {
  it("uploads the blob and offers an absolute link to copy", async () => {
    vi.mocked(requestUpload).mockResolvedValue({
      url: "/api/downloads/link/tok123",
      filename: "报告.docx",
      expires_in: 600,
    });
    vi.mocked(copyText).mockResolvedValue(true);

    await shareDownloadLink(new Blob(["x"]), "报告.docx");

    const [path, body] = vi.mocked(requestUpload).mock.calls[0]!;
    expect(path).toBe("/downloads/link");
    expect(((body as FormData).get("file") as File).name).toBe("报告.docx");

    expect(modal.confirm).toHaveBeenCalledTimes(1);
    const props = vi.mocked(modal.confirm).mock.calls[0]![0];
    await props.onOk?.();
    expect(copyText).toHaveBeenCalledWith(
      `${window.location.origin}/api/downloads/link/tok123`,
    );
  });
});
