/**
 * Curated icons for knowledge bases (humanities, science, tech, …).
 * Separate from expert icons so the create form stays focused.
 */

import type { ReactNode } from "react";
import {
  Atom,
  BookOpen,
  Briefcase,
  Cpu,
  FlaskConical,
  GraduationCap,
  Landmark,
  Languages,
  Layers,
  Palette,
  Scale,
  Terminal,
  Users,
  Wrench,
} from "lucide-react";

import { useAuthImageSrc } from "../../hooks/useAuthImageSrc";

export const KNOWLEDGE_ICON_NAMES = [
  "book-open",
  "landmark",
  "users",
  "scale",
  "flask-conical",
  "atom",
  "wrench",
  "cpu",
  "terminal",
  "graduation-cap",
  "briefcase",
  "palette",
  "languages",
] as const;

export type KnowledgeIconName = (typeof KNOWLEDGE_ICON_NAMES)[number];

const iconMap: Record<KnowledgeIconName, (size: number) => ReactNode> = {
  "book-open": (size) => <BookOpen size={size} />,
  landmark: (size) => <Landmark size={size} />,
  users: (size) => <Users size={size} />,
  scale: (size) => <Scale size={size} />,
  "flask-conical": (size) => <FlaskConical size={size} />,
  atom: (size) => <Atom size={size} />,
  wrench: (size) => <Wrench size={size} />,
  cpu: (size) => <Cpu size={size} />,
  terminal: (size) => <Terminal size={size} />,
  "graduation-cap": (size) => <GraduationCap size={size} />,
  briefcase: (size) => <Briefcase size={size} />,
  palette: (size) => <Palette size={size} />,
  languages: (size) => <Languages size={size} />,
};

export function knowledgeIconForName(
  name: string | null | undefined,
  size = 18,
): ReactNode {
  if (!name) return <Layers size={size} />;
  const fn = iconMap[name as KnowledgeIconName];
  return fn ? fn(size) : <Layers size={size} />;
}

/** Portrait when ``iconUrl`` is set; otherwise the Lucide ``iconName`` glyph. */
export function KnowledgeBaseAvatar({
  iconUrl,
  iconName,
  size = 18,
  className,
}: {
  iconUrl?: string | null;
  iconName?: string | null;
  size?: number;
  className?: string;
}) {
  const trimmed = iconUrl?.trim() || "";
  const { src, loadState } = useAuthImageSrc(trimmed);
  if (trimmed && loadState === "ready" && src) {
    return (
      <img
        src={src}
        alt=""
        className={className}
        style={{
          width: size,
          height: size,
          borderRadius: Math.max(4, Math.round(size / 4)),
          objectFit: "cover",
          display: "block",
        }}
      />
    );
  }
  return knowledgeIconForName(iconName, size);
}
