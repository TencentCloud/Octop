import { beforeEach, describe, expect, it, vi } from "vitest";

const copyMock = vi.fn();

vi.mock("copy-to-clipboard", () => ({
  default: (text: string) => copyMock(text) as boolean,
}));

import { copyText } from "./copyText";

describe("copyText", () => {
  beforeEach(() => {
    copyMock.mockReset();
  });

  it("returns false for empty text without calling copy", async () => {
    expect(await copyText("")).toBe(false);
    expect(copyMock).not.toHaveBeenCalled();
  });

  it("delegates to copy-to-clipboard", async () => {
    copyMock.mockReturnValue(true);
    expect(await copyText("hello")).toBe(true);
    expect(copyMock).toHaveBeenCalledWith("hello");
  });

  it("returns false when copy-to-clipboard fails", async () => {
    copyMock.mockReturnValue(false);
    expect(await copyText("hello")).toBe(false);
  });
});
