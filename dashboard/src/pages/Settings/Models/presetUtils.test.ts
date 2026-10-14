import { describe, expect, it } from "vitest";
import {
  isLocalProviderRow,
  isOllamaProviderRow,
  isOllamaRuntimeUrl,
  isOnnxProviderRow,
  looksLikeOllamaProvider,
} from "./presetUtils";

describe("isOnnxProviderRow", () => {
  it("matches the onboard ONNX placeholder key or exact name", () => {
    expect(isOnnxProviderRow({ name: "anything", api_key: "onnx" })).toBe(true);
    expect(isOnnxProviderRow({ name: "ONNX (Local)" })).toBe(true);
    expect(isOnnxProviderRow({ name: "  ONNX (Local)  " })).toBe(true);
    expect(
      isOnnxProviderRow({ name: "My ONNX Cloud Proxy", api_key: "sk-x" }),
    ).toBe(false);
  });
});

describe("isOllamaProviderRow", () => {
  it("matches onboard identity only — not a coincidental Ollama URL", () => {
    expect(isOllamaProviderRow({ name: "anything", api_key: "ollama" })).toBe(
      true,
    );
    expect(isOllamaProviderRow({ name: "Ollama (Local)" })).toBe(true);
    expect(isOllamaProviderRow({ name: "  ollama (local)  " })).toBe(true);
    expect(
      isOllamaProviderRow({
        name: "home-ollama",
        api_key: "sk-x",
        base_url: "http://127.0.0.1:11434",
      }),
    ).toBe(false);
    expect(
      isOllamaProviderRow({
        name: "docker-ollama",
        api_key: "sk-x",
        base_url: "http://ollama:11434",
      }),
    ).toBe(false);
  });

  it("does not treat custom local OpenAI-compat providers as onboard Ollama", () => {
    expect(
      isOllamaProviderRow({
        name: "my-local-llm",
        api_key: "sk-local",
        base_url: "http://127.0.0.1:8000/v1",
      }),
    ).toBe(false);
    expect(
      isLocalProviderRow({
        name: "lm-studio",
        api_key: "lm-studio",
        base_url: "http://localhost:1234/v1",
      }),
    ).toBe(false);
    expect(
      isLocalProviderRow({
        name: "company-ollama",
        api_key: "sk-x",
        base_url: "http://192.168.1.10:11434",
      }),
    ).toBe(false);
  });
});

describe("looksLikeOllamaProvider", () => {
  it("keeps URL hints for the Ollama management UI", () => {
    expect(isOllamaRuntimeUrl("http://127.0.0.1:11434")).toBe(true);
    expect(isOllamaRuntimeUrl("http://ollama")).toBe(true);
    expect(isOllamaRuntimeUrl("http://host/qwen11434")).toBe(false);
    expect(isOllamaRuntimeUrl("https://ollama.com/v1")).toBe(false);
    expect(
      looksLikeOllamaProvider({
        name: "company-ollama",
        api_key: "sk-x",
        base_url: "http://192.168.1.10:11434",
      }),
    ).toBe(true);
    expect(
      looksLikeOllamaProvider({
        name: "my-local-llm",
        api_key: "sk-local",
        base_url: "http://127.0.0.1:8000/v1",
      }),
    ).toBe(false);
  });
});
