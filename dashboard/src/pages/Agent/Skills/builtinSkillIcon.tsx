import type { ReactNode } from "react";

import cloudIcon from "../../../assets/skills/cloud.svg";
import codeIcon from "../../../assets/skills/code.svg";
import filesIcon from "../../../assets/skills/files.svg";
import genericIcon from "../../../assets/skills/generic.svg";
import installSkillIcon from "../../../assets/skills/install-skill.svg";
import memoryIcon from "../../../assets/skills/memory.svg";
import newsIcon from "../../../assets/skills/news.svg";
import settingsIcon from "../../../assets/skills/settings.svg";
import sheetsIcon from "../../../assets/skills/sheets.svg";
import shieldIcon from "../../../assets/skills/shield.svg";
import skillManagerIcon from "../../../assets/skills/skill-manager.svg";
import slidesIcon from "../../../assets/skills/slides.svg";
import webSearchIcon from "../../../assets/skills/web-search.svg";

const ICON_SIZE = 44;

export interface BuiltinSkillVisual {
  node: ReactNode;
  color: string;
  image: boolean;
}

const SLUG_ICONS: Record<string, string> = {
  "skill-manager": skillManagerIcon,
  "install-skill": installSkillIcon,
  "web-search": webSearchIcon,
  memory: memoryIcon,
  "memory-manager": memoryIcon,
  "memory-management": memoryIcon,
};

const EMOJI_ICONS: Record<string, string> = {
  "🧩": skillManagerIcon,
  "🧠": memoryIcon,
  "🔍": webSearchIcon,
  "📄": filesIcon,
  "📖": filesIcon,
  "📝": filesIcon,
  "📊": sheetsIcon,
  "📽️": slidesIcon,
  "📰": newsIcon,
  "✨": genericIcon,
  "⚙️": settingsIcon,
  "🛠️": settingsIcon,
  "🌐": webSearchIcon,
  "☁️": cloudIcon,
  "📈": sheetsIcon,
  "🔥": newsIcon,
  "🛡️": shieldIcon,
  "📋": filesIcon,
};

const SLUG_HINTS: Array<{ match: RegExp; src: string }> = [
  { match: /memory|remember|recall|memo|记忆/, src: memoryIcon },
  { match: /skill-manager|技能管理/, src: skillManagerIcon },
  { match: /search|browse|搜索/, src: webSearchIcon },
  { match: /xlsx|sheet|csv|excel|表格/, src: sheetsIcon },
  { match: /pptx|slide|present|幻灯|演示/, src: slidesIcon },
  { match: /docx|writer|pdf|reader|file|文件|文档/, src: filesIcon },
  { match: /code|script|代码/, src: codeIcon },
  { match: /news|新闻/, src: newsIcon },
  { match: /cloud|云/, src: cloudIcon },
  { match: /secur|shield|guard|安全/, src: shieldIcon },
  { match: /setting|config|设置/, src: settingsIcon },
  { match: /install|安装/, src: installSkillIcon },
];

const FALLBACK_ICONS = [
  genericIcon,
  skillManagerIcon,
  webSearchIcon,
  filesIcon,
  sheetsIcon,
  slidesIcon,
  newsIcon,
  codeIcon,
  cloudIcon,
  shieldIcon,
  settingsIcon,
  installSkillIcon,
];

function hashSlug(slug: string): number {
  let hash = 0;
  for (const char of slug) {
    hash = (hash * 31 + char.charCodeAt(0)) | 0;
  }
  return Math.abs(hash);
}

function matchSkillTile(
  slug: string,
  emoji?: string,
  name?: string,
): string | undefined {
  const haystack = `${slug} ${name ?? ""}`.toLowerCase();
  const hint = SLUG_HINTS.find((item) => item.match.test(haystack));
  return (
    SLUG_ICONS[slug] ?? (emoji ? EMOJI_ICONS[emoji] : undefined) ?? hint?.src
  );
}

function srcForSkill(slug: string, emoji?: string, name?: string): string {
  return (
    matchSkillTile(slug, emoji, name) ??
    FALLBACK_ICONS[hashSlug(slug) % FALLBACK_ICONS.length]
  );
}

function iconImage(src: string, size: number): ReactNode {
  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      draggable={false}
      style={{
        width: size,
        height: size,
        borderRadius: "var(--fn-radius-md)",
        objectFit: "cover",
        display: "block",
      }}
    />
  );
}

export function resolveBuiltinSkillIcon(
  slug: string,
  emoji?: string,
  size: number = ICON_SIZE,
  name?: string,
): BuiltinSkillVisual {
  return {
    node: iconImage(srcForSkill(slug, emoji, name), size),
    color: "transparent",
    image: true,
  };
}

/** Figurative tile when the slug/name is a known category; otherwise null. */
export function resolveFigurativeSkillIcon(
  slug: string,
  emoji?: string,
  name?: string,
  size: number = ICON_SIZE,
): BuiltinSkillVisual | null {
  const src = matchSkillTile(slug, emoji, name);
  if (!src) return null;
  return {
    node: iconImage(src, size),
    color: "transparent",
    image: true,
  };
}

export function builtinSkillIcon(
  slug: string,
  size: number = ICON_SIZE,
  emoji?: string,
): ReactNode {
  return resolveBuiltinSkillIcon(slug, emoji, size).node;
}
