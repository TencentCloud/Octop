import { afterEach, describe, expect, it, vi } from "vitest";

import { message } from "@/utils/antdMessage";
import { requestUpload } from "../api/request";
import { saveBlobAsFile } from "./saveBlobAsFile";

vi.mock("../api/request", () => ({
  requestUpload: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

type DesktopWindow = Window & {
  _wails?: { invoke?: (message: string) => void };
};

afterEach(() => {
  delete (window as DesktopWindow)._wails;
  vi.mocked(requestUpload).mockReset();
  vi.mocked(message.success).mockReset();
});

describe("saveBlobAsFile", () => {
  it("posts the blob to the host Downloads API in the desktop shell", async () => {
    (window as DesktopWindow)._wails = { invoke: () => undefined };
    const blob = new Blob(["hello"], { type: "text/plain" });
    await saveBlobAsFile(blob, "note.txt");
    expect(requestUpload).toHaveBeenCalledTimes(1);
    const [path, body] = vi.mocked(requestUpload).mock.calls[0]!;
    expect(path).toBe("/downloads/local");
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBeInstanceOf(Blob);
    expect(message.success).toHaveBeenCalled();
  });

  it("uses a download anchor in the browser", async () => {
    const click = vi.fn();
    const createElement = vi.spyOn(document, "createElement");
    createElement.mockImplementation(
      () =>
        ({
          href: "",
          download: "",
          click,
          style: {},
        }) as unknown as HTMLElement,
    );
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    vi.spyOn(document.body, "removeChild").mockImplementation((node) => node);
    URL.createObjectURL = vi.fn(() => "blob:save");
    URL.revokeObjectURL = vi.fn();

    await saveBlobAsFile(new Blob(["x"]), "file.bin");
    expect(requestUpload).not.toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    createElement.mockRestore();
  });
});
