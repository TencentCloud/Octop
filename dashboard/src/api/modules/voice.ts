import { request, requestBlob, requestUpload } from "../request";

export interface VoicePreset {
  id: string;
  name: string;
  kind: string;
  capability: "stt" | "tts" | "both";
  free: boolean;
  requires_key: boolean;
  description: string;
}

export interface VoiceProviderRow {
  id: number;
  name: string;
  kind: string;
  capability: "stt" | "tts" | "both";
  base_url: string | null;
  api_key: string | null;
  extra: Record<string, unknown>;
  note: string | null;
  enabled: boolean;
}

export interface ActiveVoice {
  stt: string;
  tts: string;
}

function recordingFilename(type: string): string {
  const lower = type.toLowerCase();
  if (lower.includes("mp4")) return "recording.m4a";
  if (lower.includes("ogg")) return "recording.ogg";
  if (lower.includes("wav")) return "recording.wav";
  return "recording.webm";
}

export const voiceApi = {
  getPresets: () => request<VoicePreset[]>("/voice/presets"),
  getProviders: () => request<VoiceProviderRow[]>("/voice/providers"),
  adminListProviders: () =>
    request<VoiceProviderRow[]>("/admin/voice/providers"),
  getActive: () => request<ActiveVoice>("/voice/active"),
  setActive: (body: { stt?: string; tts?: string }) =>
    request<ActiveVoice>("/voice/active", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  transcribe: (audio: Blob, language = "zh-CN", provider?: string) => {
    const form = new FormData();
    form.append("audio", audio, recordingFilename(audio.type));
    form.append("language", language);
    if (provider) form.append("provider", provider);
    return requestUpload<{ text: string; confidence?: number | null }>(
      "/voice/stt",
      form,
    );
  },
  synthesize: (text: string, provider?: string) =>
    requestBlob("/voice/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        ...(provider ? { provider } : {}),
      }),
    }),
  createProvider: (body: {
    name: string;
    kind: string;
    capability: string;
    base_url?: string | null;
    api_key?: string | null;
    extra_json?: string | null;
    note?: string | null;
  }) =>
    request<VoiceProviderRow>("/admin/voice/providers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchProvider: (
    id: number,
    body: Partial<{
      kind: string;
      capability: string;
      base_url: string | null;
      api_key: string | null;
      extra_json: string | null;
      note: string | null;
      enabled: boolean;
    }>,
  ) =>
    request<VoiceProviderRow>(`/admin/voice/providers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteProvider: (id: number) =>
    request<void>(`/admin/voice/providers/${id}`, { method: "DELETE" }),
  testProvider: (id: number, mode: "stt" | "tts") =>
    request<{ ok: boolean; error?: string }>(
      `/admin/voice/providers/${id}/test`,
      {
        method: "POST",
        body: JSON.stringify({ mode }),
      },
    ),
};
