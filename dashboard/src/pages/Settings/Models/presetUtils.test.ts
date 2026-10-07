import { describe, expect, it } from "vitest";
import { isLocalProviderRow, isOllamaProviderRow } from "./presetUtils";

describe("isOllamaProviderRow", () => {
  it("does not treat Ollama Cloud endpoints as local", () => {
    expect(
      isOllamaProviderRow({ name: "oll", base_url: "https://ollama.com/v1" }),
    ).toBe(false);
    expect(
      isOllamaProviderRow({
        name: "oll",
        base_url: "https://www.ollama.com/v1",
      }),
    ).toBe(false);
  });

  it("still recognizes this-machine URLs as local", () => {
    expect(
      isOllamaProviderRow({
        name: "x",
        base_url: "http://localhost:11434/v1",
      }),
    ).toBe(true);
    expect(
      isOllamaProviderRow({ name: "x", base_url: "http://127.0.0.1:11434" }),
    ).toBe(true);
    expect(
      isOllamaProviderRow({
        name: "x",
        base_url: "http://192.168.1.10:11434/v1",
      }),
    ).toBe(true);
    expect(
      isOllamaProviderRow({ name: "x", base_url: "http://ollama:11434" }),
    ).toBe(true);
  });

  it("keeps exact preset identity regardless of URL", () => {
    expect(
      isOllamaProviderRow({
        name: "Ollama (Local)",
        base_url: "https://ollama.com/v1",
      }),
    ).toBe(true);
    expect(
      isLocalProviderRow({ name: "oll", base_url: "https://ollama.com/v1" }),
    ).toBe(false);
  });
});
