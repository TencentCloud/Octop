import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { voiceApi, type VoiceProviderRow } from "../../../api/modules/voice";
import { invalidateVoiceConfigCache } from "../../../hooks/useVoiceConfig";
import { VoiceSettingsPanel } from "./index";
import { CustomVoiceProviderDrawer } from "./CustomVoiceProviderDrawer";

vi.mock("../../../api/modules/voice", () => ({
  voiceApi: {
    getPresets: vi.fn(),
    getProviders: vi.fn(),
    getActive: vi.fn(),
    setActive: vi.fn(),
    createProvider: vi.fn(),
    patchProvider: vi.fn(),
    deleteProvider: vi.fn(),
    testConfiguration: vi.fn(),
  },
}));
vi.mock("../../../hooks/useVoiceConfig", () => ({
  invalidateVoiceConfigCache: vi.fn(),
}));
vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const api = vi.mocked(voiceApi, true);
const browserGetComputedStyle = window.getComputedStyle.bind(window);

function provider(overrides: Partial<VoiceProviderRow> = {}): VoiceProviderRow {
  return {
    id: 12,
    name: "Qwen speech",
    kind: "dashscope",
    capability: "both",
    base_url: "https://dashscope.aliyuncs.com/api/v1",
    api_key: "test-key",
    extra: {
      stt_model: "qwen3-asr-flash",
      tts_model: "qwen3-tts-flash",
      voice_id: "Cherry",
    },
    note: null,
    enabled: true,
    ...overrides,
  };
}

function customCard(name: string, index = 0): HTMLElement {
  const cards = screen.getAllByText(name);
  const header = cards[index].closest("[class*='cardHeader']");
  return header!.parentElement!;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    browserGetComputedStyle(element),
  );
  api.getPresets.mockResolvedValue([
    {
      id: "browser",
      name: "Browser",
      kind: "browser",
      capability: "both",
      free: true,
      requires_key: false,
      description: "Browser speech",
    },
  ]);
  api.getProviders.mockResolvedValue([]);
  api.getActive.mockResolvedValue({ stt: "browser", tts: "browser" });
  api.setActive.mockResolvedValue({ stt: "Qwen speech", tts: "browser" });
  api.createProvider.mockResolvedValue(provider());
  api.patchProvider.mockResolvedValue(provider());
  api.deleteProvider.mockResolvedValue(undefined);
  api.testConfiguration.mockResolvedValue({ ok: true });
});

describe("custom voice providers", () => {
  it("shows custom providers in their capability sections and activates by their name", async () => {
    api.getProviders.mockResolvedValue([
      provider(),
      provider({ id: 13, name: "Recognition only", capability: "stt" }),
      provider({ id: 14, name: "mimo" }),
    ]);
    const user = userEvent.setup();
    render(<VoiceSettingsPanel />);

    await screen.findAllByText("Qwen speech");
    expect(screen.getAllByText("Qwen speech")).toHaveLength(2);
    expect(screen.getAllByText("Recognition only")).toHaveLength(1);
    expect(screen.queryByText("mimo")).not.toBeInTheDocument();
    await user.click(
      within(customCard("Qwen speech")).getByRole("button", {
        name: "voice.setActive",
      }),
    );

    expect(api.setActive).toHaveBeenCalledWith({ stt: "Qwen speech" });
    expect(invalidateVoiceConfigCache).toHaveBeenCalled();
  });

  it("prevents disabled providers from activation and active providers from deletion", async () => {
    api.getProviders.mockResolvedValue([
      provider({ capability: "tts" }),
      provider({
        id: 13,
        name: "Disabled speech",
        capability: "stt",
        enabled: false,
      }),
    ]);
    api.getActive.mockResolvedValue({ stt: "browser", tts: "Qwen speech" });
    render(<VoiceSettingsPanel />);

    await screen.findByText("Qwen speech");
    expect(
      within(customCard("Qwen speech")).getByRole("button", {
        name: "common.delete",
      }),
    ).toBeDisabled();
    expect(
      within(customCard("Disabled speech")).getByRole("button", {
        name: "voice.setActive",
      }),
    ).toBeDisabled();
  });

  it("keeps legacy custom protocols selectable without offering an incompatible editor", async () => {
    api.getProviders.mockResolvedValue([
      provider({ name: "Legacy MiMo", kind: "mimo", capability: "tts" }),
    ]);
    render(<VoiceSettingsPanel />);

    await screen.findByText("Legacy MiMo");
    const card = within(customCard("Legacy MiMo"));
    expect(
      card.queryByRole("button", { name: "common.edit" }),
    ).not.toBeInTheDocument();
    expect(card.getByRole("button", { name: "voice.setActive" })).toBeEnabled();
    expect(card.getByRole("button", { name: "common.delete" })).toBeEnabled();
    expect(api.patchProvider).not.toHaveBeenCalled();
  });

  it("creates a DashScope configuration with separate model and voice IDs", async () => {
    const user = userEvent.setup();
    render(<VoiceSettingsPanel />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "voice.addCustomProvider" }),
      ).toBeEnabled(),
    );
    await user.click(
      screen.getByRole("button", { name: "voice.addCustomProvider" }),
    );
    await user.type(screen.getByLabelText("models.nameLabel"), "Qwen speech");
    await user.click(screen.getByLabelText("voice.protocol"));
    await user.click(screen.getByText("voice.dashscopeProtocol"));
    await user.type(screen.getByLabelText("API Key"), "test-key");
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(api.createProvider).toHaveBeenCalled());
    const payload = api.createProvider.mock.calls[0][0];
    expect(payload).toMatchObject({
      name: "Qwen speech",
      kind: "dashscope",
      capability: "both",
      base_url: "https://dashscope.aliyuncs.com/api/v1",
      api_key: "test-key",
    });
    expect(JSON.parse(payload.extra_json!)).toEqual({
      stt_model: "qwen3-asr-flash",
      tts_model: "qwen3-tts-flash",
      voice_id: "Cherry",
    });
    expect(invalidateVoiceConfigCache).toHaveBeenCalled();
  });

  it("rejects names reserved for built-in providers before saving", async () => {
    const user = userEvent.setup();
    render(<VoiceSettingsPanel />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "voice.addCustomProvider" }),
      ).toBeEnabled(),
    );
    await user.click(
      screen.getByRole("button", { name: "voice.addCustomProvider" }),
    );
    await user.type(screen.getByLabelText("models.nameLabel"), "openai");
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await screen.findByText("voice.reservedProviderName");
    expect(api.createProvider).not.toHaveBeenCalled();
  });

  it("edits legacy TTS models without changing the provider name or extra options", async () => {
    const existing = provider({
      kind: "openai",
      capability: "tts",
      extra: {
        model: "custom-tts-model",
        voice_id: "custom-voice",
        speed: 1.2,
      },
    });
    const onSaved = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <CustomVoiceProviderDrawer
        open
        existing={existing}
        reservedNames={["openai"]}
        providers={[existing]}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    expect(screen.getByLabelText("models.nameLabel")).toBeDisabled();
    await waitFor(() =>
      expect(screen.getByLabelText("voice.ttsModel")).toHaveValue(
        "custom-tts-model",
      ),
    );
    expect(screen.queryByLabelText("voice.sttModel")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("voice.ttsModel"));
    await user.type(
      screen.getByLabelText("voice.ttsModel"),
      "updated-tts-model",
    );
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(api.patchProvider).toHaveBeenCalled());
    expect(api.patchProvider.mock.calls[0][0]).toBe(existing.id);
    expect(JSON.parse(api.patchProvider.mock.calls[0][1].extra_json!)).toEqual({
      model: "custom-tts-model",
      tts_model: "updated-tts-model",
      voice_id: "custom-voice",
      speed: 1.2,
    });
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it("probes both configured capabilities without creating a provider", async () => {
    const existing = provider();
    const user = userEvent.setup();
    render(
      <CustomVoiceProviderDrawer
        open
        existing={existing}
        reservedNames={[]}
        providers={[existing]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "voice.probe" }));

    await waitFor(() => expect(api.testConfiguration).toHaveBeenCalledTimes(2));
    expect(
      api.testConfiguration.mock.calls.map(([payload]) => payload.mode),
    ).toEqual(["stt", "tts"]);
    expect(api.createProvider).not.toHaveBeenCalled();
  });

  it("saves separate built-in OpenAI models and preserves existing voice settings", async () => {
    api.getPresets.mockResolvedValue([
      {
        id: "openai",
        name: "OpenAI",
        kind: "openai",
        capability: "both",
        free: false,
        requires_key: true,
        description: "OpenAI speech",
      },
    ]);
    api.getProviders.mockResolvedValue([
      provider({
        name: "openai",
        kind: "openai",
        extra: { model: "whisper-1", voice_id: "nova", speed: 1.2 },
      }),
    ]);
    const user = userEvent.setup();
    render(<VoiceSettingsPanel />);
    await screen.findAllByText("OpenAI");
    await user.click(
      within(customCard("OpenAI")).getByRole("button", { name: "common.edit" }),
    );
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(api.patchProvider).toHaveBeenCalled());
    expect(JSON.parse(api.patchProvider.mock.calls[0][1].extra_json!)).toEqual({
      model: "whisper-1",
      stt_model: "whisper-1",
      tts_model: "tts-1",
      voice_id: "nova",
      speed: 1.2,
    });
  });
});
