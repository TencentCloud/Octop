import { describe, expect, it } from "vitest";
import { expandOllamaDownloadedIds } from "./ollamaNames";

describe("expandOllamaDownloadedIds", () => {
  it("aliases :latest with the untagged name", () => {
    expect(expandOllamaDownloadedIds(["llama3:latest"]).sort()).toEqual(
      ["llama3", "llama3:latest"].sort(),
    );
    expect(expandOllamaDownloadedIds(["llama3"]).sort()).toEqual(
      ["llama3", "llama3:latest"].sort(),
    );
  });

  it("does not alias a specific tag to the bare name", () => {
    expect(expandOllamaDownloadedIds(["qwen2.5:7b"])).toEqual(["qwen2.5:7b"]);
  });
});
