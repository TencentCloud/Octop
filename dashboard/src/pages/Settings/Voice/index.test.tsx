import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});
vi.mock("../../../api/modules/voice", () => ({
  voiceApi: {
    getPresets: vi.fn(),
    getProviders: vi.fn(),
    getActive: vi.fn(),
    createProvider: vi.fn(),
    patchProvider: vi.fn(),
    setActive: vi.fn(),
    testConfiguration: vi.fn(),
  },
}));
vi.mock("../../../hooks/useVoiceConfig", () => ({
  invalidateVoiceConfigCache: vi.fn(),
}));

import { voiceApi } from "../../../api/modules/voice";
import VoiceSettingsPanel from "./index";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(voiceApi.getPresets).mockResolvedValue([]);
  vi.mocked(voiceApi.getProviders).mockResolvedValue([]);
  vi.mocked(voiceApi.getActive).mockResolvedValue({
    stt: "browser",
    tts: "browser",
  });
  vi.mocked(voiceApi.setActive).mockResolvedValue({
    stt: "custom-voice",
    tts: "custom-voice",
  });
});

it("preserves the legacy model when editing a custom TTS provider", async () => {
  vi.mocked(voiceApi.getProviders).mockResolvedValue([
    {
      id: 1,
      name: "legacy",
      kind: "openai",
      capability: "tts",
      base_url: "https://voice.example/v1",
      api_key: "key",
      extra: { model: "legacy-tts" },
      note: null,
      enabled: true,
    },
  ]);
  render(<VoiceSettingsPanel />);
  fireEvent.click(await screen.findByText("common.edit"));
  expect(await screen.findByDisplayValue("legacy-tts")).toBeInTheDocument();
});

it("saves and activates a named custom voice provider with independent models", async () => {
  render(<VoiceSettingsPanel />);
  await waitFor(() => expect(voiceApi.getProviders).toHaveBeenCalled());
  fireEvent.click(screen.getByText("voice.addCustom"));
  fireEvent.change(await screen.findByPlaceholderText("voice.providerName"), {
    target: { value: "custom-voice" },
  });
  fireEvent.change(screen.getByPlaceholderText("API Key"), {
    target: { value: "test-key" },
  });
  fireEvent.change(screen.getByDisplayValue("https://api.openai.com/v1"), {
    target: { value: "https://voice.example/v1" },
  });
  fireEvent.change(screen.getByDisplayValue("whisper-1"), {
    target: { value: "my-stt" },
  });
  fireEvent.change(screen.getByDisplayValue("tts-1"), {
    target: { value: "my-tts" },
  });
  fireEvent.click(screen.getByText("common.save"));
  await waitFor(() =>
    expect(voiceApi.createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "custom-voice",
        kind: "openai",
        capability: "both",
        base_url: "https://voice.example/v1",
        api_key: "test-key",
      }),
    ),
  );
  expect(
    JSON.parse(vi.mocked(voiceApi.createProvider).mock.calls[0][0].extra_json!),
  ).toEqual({ stt_model: "my-stt", tts_model: "my-tts", voice_id: "alloy" });
  await waitFor(() => {
    expect(voiceApi.setActive).toHaveBeenCalledWith({ stt: "custom-voice" });
    expect(voiceApi.setActive).toHaveBeenCalledWith({ tts: "custom-voice" });
  });
});
