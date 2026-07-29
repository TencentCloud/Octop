import openaiLogo from "./openai.png";
import anthropicLogo from "./anthropic.png";
import geminiLogo from "./gemini.png";
import deepseekLogo from "./deepseek.png";
import dashscopeLogo from "./dashscope.png";
import zhipuLogo from "./zhipu.png";
import moonshotLogo from "./moonshot.webp";
import siliconLogo from "./silicon.png";
import groqLogo from "./groq.png";
import modelscopeLogo from "./modelscope.png";
import ollamaLogo from "./ollama.png";
import tencentCodingPlanLogo from "./tencent-coding-plan.png";
import tencentTokenPlanLogo from "./tencent-token-plan.png";
import openrouterLogo from "./openrouter.png";
import mimoLogo from "./mimo.svg";
import minimaxLogo from "./minimax.png";
import volcesLogo from "./volces.svg";
import customProviderLogo from "./custom-provider.svg";
import opencodeLogo from "./opencode.svg";

export const PROVIDER_LOGOS: Record<string, string> = {
  openai: openaiLogo,
  anthropic: anthropicLogo,
  gemini: geminiLogo,
  deepseek: deepseekLogo,
  dashscope: dashscopeLogo,
  zhipu: zhipuLogo,
  moonshot: moonshotLogo,
  silicon: siliconLogo,
  groq: groqLogo,
  modelscope: modelscopeLogo,
  ollama: ollamaLogo,
  "tencent-coding-plan": tencentCodingPlanLogo,
  "tencent-token-plan": tencentTokenPlanLogo,
  "tencent-hai": tencentCodingPlanLogo,
  openrouter: openrouterLogo,
  mimo: mimoLogo,
  minimax: minimaxLogo,
  volces: volcesLogo,
  opencode: opencodeLogo,
};

export { customProviderLogo };

export function getProviderLogo(providerId: string): string | undefined {
  if (PROVIDER_LOGOS[providerId]) return PROVIDER_LOGOS[providerId];
  const base = providerId.split("-")[0];
  if (base !== providerId && PROVIDER_LOGOS[base]) return PROVIDER_LOGOS[base];
  const groupLogo: Record<string, string> = {
    kimi: moonshotLogo,
    minimax: minimaxLogo,
    zhipu: zhipuLogo,
    dashscope: dashscopeLogo,
    aliyun: dashscopeLogo,
    volcengine: volcesLogo,
    siliconflow: siliconLogo,
    tencent: tencentCodingPlanLogo,
    opencode: opencodeLogo,
  };
  return groupLogo[base];
}

/**
 * Documentation / API reference URLs for built-in providers.
 */
export const PROVIDER_DOCS: Record<string, string> = {
  ollama: "https://ollama.com/search",
  openai: "https://platform.openai.com/docs",
  anthropic: "https://docs.anthropic.com",
  gemini: "https://ai.google.dev/gemini-api/docs",
  deepseek: "https://api-docs.deepseek.com/",
  dashscope: "https://help.aliyun.com/zh/model-studio/",
  zhipu: "https://docs.bigmodel.cn/",
  moonshot: "https://platform.moonshot.cn/docs/overview",
  silicon: "https://docs.siliconflow.cn/cn/userguide/introduction",
  groq: "https://groq.com/",
  modelscope: "https://modelscope.cn/docs/model-service/API-Inference/intro",
  "tencent-coding-plan": "https://hunyuan.cloud.tencent.com/#/app/subscription",
  "tencent-token-plan": "https://hunyuan.cloud.tencent.com/#/app/subscription",
  "tencent-hai": "https://cloud.tencent.com/document/product/1721",
  openrouter: "https://openrouter.ai/docs/quickstart",
  mimo: "https://platform.xiaomimimo.com/",
  minimax: "https://platform.minimaxi.com/",
  volces: "https://www.volcengine.com/docs/82379/1399008",
  opencode: "https://opencode.ai/docs/zh-cn/zen/",
  "opencode-zen-openai": "https://opencode.ai/docs/zh-cn/zen/",
  "opencode-zen-anthropic": "https://opencode.ai/docs/zh-cn/zen/",
  "opencode-go-openai": "https://opencode.ai/docs/zh-cn/go/",
  "opencode-go-anthropic": "https://opencode.ai/docs/zh-cn/go/",
};

export function getProviderDocs(providerId: string): string | undefined {
  return PROVIDER_DOCS[providerId];
}

/**
 * Get provider name from i18n, falling back to the API-returned name.
 */
export function getProviderName(
  providerId: string,
  fallbackName: string,
  t: (key: string) => string,
): string {
  const key = `providers.${providerId}`;
  const translated = t(key);
  return translated === key ? fallbackName : translated;
}
