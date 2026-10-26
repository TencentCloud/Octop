#!/usr/bin/env python3
"""从 lobehub/icons 抓取模型品牌图标，生成 ui/model-icons.js。

用法：
    python3 tools/gen_model_icons.py

生成物是一行 `const MODEL_ICONS = {...}`：每个品牌两个 data URI（浅色 / 深色），
保留厂牌 SVG 原始 fill/stroke，避免把多色品牌图标烤成黑白；浅深色只通过透明背景与尺寸保证清晰。
图标总量大，单独成文件、由 build.py 内联进 index.js，模板本身保持可读。
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

CDN = "https://unpkg.com/@lobehub/icons-static-svg@1.98.0/icons/{slug}.svg"
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "ui" / "model-icons.js"

# key 是 modelBrand() 返回的品牌名，value 是 lobehub 的图标 slug
BRANDS = [
    ("OpenAI", "openai"),
    ("Codex", "codex"),
    ("Anthropic", "anthropic"),
    ("Claude", "claude"),
    ("Google Gemini", "gemini"),
    ("Gemma", "gemma"),
    ("Google", "google"),
    ("DeepMind", "deepmind"),
    ("xAI Grok", "grok"),
    ("xAI", "xai"),
    ("DeepSeek", "deepseek"),
    ("Qwen", "qwen"),
    ("Alibaba", "alibaba"),
    ("Kimi", "kimi"),
    ("Moonshot", "moonshot"),
    ("Zhipu", "zhipu"),
    ("ChatGLM", "chatglm"),
    ("Doubao", "doubao"),
    ("Volcano Engine", "volcengine"),
    ("ByteDance", "bytedance"),
    ("Hunyuan", "hunyuan"),
    ("Tencent Cloud", "tencentcloud"),
    ("Wenxin", "wenxin"),
    ("Baidu", "baidu"),
    ("Spark", "spark"),
    ("iFlytek", "iflytekcloud"),
    ("MiniMax", "minimax"),
    ("Xiaomi MiMo", "xiaomimimo"),
    ("StepFun", "stepfun"),
    ("Yi", "yi"),
    ("ZeroOne", "zeroone"),
    ("Baichuan", "baichuan"),
    ("InternLM", "internlm"),
    ("Tiangong", "tiangong"),
    ("SenseNova", "sensenova"),
    ("Mistral", "mistral"),
    ("Meta", "meta"),
    ("Cohere", "cohere"),
    ("Nvidia", "nvidia"),
    ("Perplexity", "perplexity"),
    ("Groq", "groq"),
    ("OpenRouter", "openrouter"),
    ("SiliconFlow", "siliconcloud"),
    ("ModelScope", "modelscope"),
    ("Agnes", "agnesai"),
    ("Together", "together"),
    ("Fireworks", "fireworks"),
    ("Cerebras", "cerebras"),
    ("Novita", "novita"),
    ("Hyperbolic", "hyperbolic"),
    ("Vertex AI", "vertexai"),
    ("Bedrock", "bedrock"),
    ("Azure", "azure"),
    ("Ollama", "ollama"),
    ("Copilot", "copilot"),
    ("LM Studio", "lmstudio"),
    ("vLLM", "vllm"),
    ("HuggingFace", "huggingface"),
    ("OpenCode", "opencode"),
    ("Gitee AI", "giteeai"),
    ("LongCat", "longcat"),
    ("Ling", "ling"),
    ("Reka", "reka"),
    ("AI21", "ai21"),
    ("Upstage", "upstage"),
    ("TII", "tii"),
    ("Sakana", "sakana"),
    ("Liquid", "liquid"),
    ("RWKV", "rwkv"),
]

# Brand-accent palette for upstream monochrome glyphs. This keeps the official
# SVG geometry intact while avoiding currentColor becoming black in CSS data URLs.
BRAND_COLORS = {
    "OpenAI": "#10A37F",
    "Codex": "#6E56CF",
    "Anthropic": "#D97757",
    "Claude": "#D97757",
    "Google Gemini": "#8E75B2",
    "Gemma": "#4285F4",
    "Google": "#4285F4",
    "DeepMind": "#4285F4",
    "xAI Grok": "#111827",
    "xAI": "#111827",
    "DeepSeek": "#4D6BFE",
    "Qwen": "#615CED",
    "Alibaba": "#FF6A00",
    "Kimi": "#5B6CFF",
    "Moonshot": "#5B6CFF",
    "Zhipu": "#3B82F6",
    "ChatGLM": "#3B82F6",
    "Doubao": "#4D6BFE",
    "Volcano Engine": "#4D6BFE",
    "ByteDance": "#111827",
    "Hunyuan": "#6C5CE7",
    "Tencent Cloud": "#00A4FF",
    "Wenxin": "#2468F2",
    "Baidu": "#2468F2",
    "Spark": "#4B7BFF",
    "iFlytek": "#2878FF",
    "MiniMax": "#6D5CE8",
    "Xiaomi MiMo": "#FF6900",
    "StepFun": "#5B5CE2",
    "Yi": "#6A5AE0",
    "ZeroOne": "#6B5CE7",
    "Baichuan": "#20A37F",
    "InternLM": "#0F766E",
    "Tiangong": "#4F46E5",
    "SenseNova": "#6254E8",
    "Mistral": "#F97316",
    "Meta": "#0866FF",
    "Cohere": "#39594D",
    "Nvidia": "#76B900",
    "Perplexity": "#20B8A9",
    "Groq": "#F55036",
    "OpenRouter": "#6366F1",
    "SiliconFlow": "#615CED",
    "ModelScope": "#6246EA",
    "Azure": "#0078D4",
    "Bedrock": "#FF9900",
    "Vertex AI": "#4285F4",
    "Ollama": "#111827",
    "Copilot": "#7C3AED",
    "LM Studio": "#536DFE",
    "vLLM": "#00A67E",
    "HuggingFace": "#F4A261",
}
_FALLBACK_COLORS = ("#0F766E", "#4F46E5", "#0891B2", "#7C3AED", "#2563EB", "#C2410C", "#059669")


def brand_color(name: str, index: int) -> str:
    return BRAND_COLORS.get(name, _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)])


# 只转义会截断 URI / 结束属性的字符，空格也编掉（url() 里留裸空格不稳）
_ESCAPE = {"%": "%25", "#": "%23", "<": "%3C", ">": "%3E", '"': "%22", " ": "%20"}


def encode(svg: str) -> str:
    out = "".join(_ESCAPE.get(ch, ch) for ch in svg)
    return "data:image/svg+xml," + out


def fetch(slug: str) -> str:
    req = urllib.request.Request(CDN.format(slug=slug), headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        svg = resp.read().decode("utf-8")
    svg = re.sub(r">\s+<", "><", svg).strip()
    if "currentColor" not in svg and "fill=" not in svg and "stroke=" not in svg:
        raise SystemExit(f"{slug}: 意料之外的 SVG，缺 fill/stroke")
    return svg


def main() -> int:
    icons: dict[str, dict[str, str]] = {}
    for index, (name, slug) in enumerate(BRANDS):
        svg = fetch(slug)
        # Keep upstream vector geometry and any path-specific colors; resolve only
        # currentColor to the known brand accent for CSS data-URL contexts.
        svg = svg.replace("currentColor", brand_color(name, index))
        icons[name] = {"light": encode(svg), "dark": encode(svg)}
        print(f"{name:16s} {slug:16s} {brand_color(name, index)} {len(svg):5d} bytes svg")
    payload = json.dumps(icons, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(
        "/* 自动生成，勿手改：python3 tools/gen_model_icons.py\n"
        "   图标来源 https://lobehub.com/zh/icons（@lobehub/icons-static-svg，MIT） */\n"
        f"const MODEL_ICONS = {payload};\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT} ({OUT.stat().st_size} bytes, {len(icons)} brands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
