const CJK_RE = /[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/;

/** Pick BCP-47 locale from message text (not browser UI language). */
export function detectSpeechLocale(text: string): string {
  if (/[\u3040-\u30ff]/.test(text)) return "ja-JP";
  if (CJK_RE.test(text)) return "zh-CN";
  if (/[\uac00-\ud7af]/.test(text)) return "ko-KR";
  return navigator.language || "en-US";
}

/** Whether speechSynthesis has any voice for the text's language. */
export function hasBrowserVoiceForText(
  text: string,
  voices: SpeechSynthesisVoice[],
): boolean {
  const locale = detectSpeechLocale(text);
  const prefix = locale.split("-")[0].toLowerCase();
  return voices.some((v) =>
    v.lang.replace("_", "-").toLowerCase().startsWith(prefix),
  );
}

const THINKING_TAG_RE = /<think>[\s\S]*?<\/think>/gi;

function stripThinkTags(raw: string): string {
  let result = raw.replace(THINKING_TAG_RE, "");
  const openIdx = result.search(/<think>/i);
  if (openIdx >= 0) result = result.slice(0, openIdx);
  return result.trim();
}

/**
 * Convert assistant markdown to text suitable for TTS (prose only).
 */
export function plainTextForSpeech(raw: string): string {
  let t = stripThinkTags(raw);
  t = t.replace(/```[\s\S]*?```/g, " ");
  t = t.replace(/`([^`]+)`/g, "$1");
  t = t.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
  t = t.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  t = t.replace(/<[^>]+>/g, " ");
  t = t.replace(/https?:\/\/\S+/g, " ");
  t = t.replace(/^\|.+\|$/gm, " ");
  t = t.replace(/^#{1,6}\s*/gm, "");
  t = t.replace(/(\*{1,3}|_{1,3})(.*?)\1/g, "$2");
  t = t.replace(/^[-*_]{3,}\s*$/gm, " ");
  t = t.replace(/^>\s?/gm, "");
  t = t.replace(/^\s*[-*+]\s+/gm, "");
  t = t.replace(/^\s*\d+\.\s+/gm, "");
  t = t.replace(/[#`_[\]()>|~]/g, " ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

/** Returns trimmed speakable text, or "" when nothing worth reading aloud. */
export function prepareSpeechText(raw: string): string {
  const plain = plainTextForSpeech(raw);
  if (plain.length < 2) return "";
  return plain;
}
