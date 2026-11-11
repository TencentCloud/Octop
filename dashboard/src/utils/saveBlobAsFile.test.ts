import { afterEach, describe, expect, it, vi } from "vitest";

import { shareDownloadLink } from "./downloadLink";
import { saveBlobAsFile } from "./saveBlobAsFile";

vi.mock("./downloadLink", () => ({
  shareDownloadLink: vi.fn(),
}));

type BridgeHost = Window & { octopDesktop?: unknown };

/** Intercept the synthetic <a download> click the helper appends to <body>. */
function stubDownloadAnchor(): ReturnType<typeof vi.fn> {
  const click = vi.fn();
  vi.spyOn(document, "createElement").mockImplementation(
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
  return click;
}

afterEach(() => {
  delete (window as BridgeHost).octopDesktop;
  vi.mocked(shareDownloadLink).mockReset();
  vi.restoreAllMocks();
});

describe("saveBlobAsFile", () => {
  it("uses a download anchor in the desktop shell", async () => {
    Object.defineProperty(window, "octopDesktop", {
      configurable: true,
      value: {},
    });
    const click = stubDownloadAnchor();

    await saveBlobAsFile(
      new Blob(["hello"], { type: "text/plain" }),
      "note.txt",
    );

    expect(click).toHaveBeenCalledTimes(1);
    expect(shareDownloadLink).not.toHaveBeenCalled();
  });

  it("uses a download anchor in the browser", async () => {
    const click = stubDownloadAnchor();

    await saveBlobAsFile(new Blob(["x"]), "file.bin");

    expect(click).toHaveBeenCalledTimes(1);
    expect(shareDownloadLink).not.toHaveBeenCalled();
  });

  it("hands in-app browsers a download link instead of a blob", async () => {
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) MicroMessenger/8.0.50",
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click");
    const blob = new Blob(["x"]);

    await saveBlobAsFile(blob, "report.docx");

    expect(shareDownloadLink).toHaveBeenCalledWith(blob, "report.docx");
    expect(click).not.toHaveBeenCalled();
  });
});
