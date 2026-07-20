/**
 * iconForName — map an expert's ``icon_name`` (a free-form string from the
 * manifest, e.g. ``"cpu"``, ``"trending-up"``, ``"baby"``) to a lucide-react
 * icon node. Returns a sensible default (``Layers``) when the key is missing
 * or unknown so cards never render blank.
 *
 * Ported from finnie's SceneTabContent + Personalization page so the octop
 * Experts page presents the same colourful, themed iconography.
 */

import type { ReactNode } from "react";
import {
  Sparkles,
  Globe,
  BookOpen,
  User,
  Rocket,
  Fingerprint,
  FileText,
  Video,
  Palette,
  TrendingUp,
  PenTool,
  CandlestickChart,
  Home,
  Baby,
  MessageSquare,
  Cpu,
  Server,
  Wrench,
  Heart,
  Layers,
  Mail,
  Zap,
  Terminal,
  ListTodo,
  Presentation,
  Activity,
  HardDrive,
  Bell,
  BarChart3,
  Network,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";

const iconMap: Record<string, (size: number) => ReactNode> = {
  sparkles: (size) => <Sparkles size={size} />,
  globe: (size) => <Globe size={size} />,
  "book-open": (size) => <BookOpen size={size} />,
  user: (size) => <User size={size} />,
  rocket: (size) => <Rocket size={size} />,
  fingerprint: (size) => <Fingerprint size={size} />,
  "file-text": (size) => <FileText size={size} />,
  video: (size) => <Video size={size} />,
  palette: (size) => <Palette size={size} />,
  "trending-up": (size) => <TrendingUp size={size} />,
  "pen-tool": (size) => <PenTool size={size} />,
  "candlestick-chart": (size) => <CandlestickChart size={size} />,
  home: (size) => <Home size={size} />,
  baby: (size) => <Baby size={size} />,
  "message-square": (size) => <MessageSquare size={size} />,
  cpu: (size) => <Cpu size={size} />,
  server: (size) => <Server size={size} />,
  wrench: (size) => <Wrench size={size} />,
  heart: (size) => <Heart size={size} />,
  mail: (size) => <Mail size={size} />,
  zap: (size) => <Zap size={size} />,
  terminal: (size) => <Terminal size={size} />,
  "list-todo": (size) => <ListTodo size={size} />,
  presentation: (size) => <Presentation size={size} />,
  activity: (size) => <Activity size={size} />,
  "hard-drive": (size) => <HardDrive size={size} />,
  "bar-chart-3": (size) => <BarChart3 size={size} />,
  network: (size) => <Network size={size} />,
  "shield-check": (size) => <ShieldCheck size={size} />,
  "refresh-cw": (size) => <RefreshCw size={size} />,
};

export function iconForName(
  name: string | null | undefined,
  size = 22,
): ReactNode {
  if (!name) return <Layers size={size} />;
  const fn = iconMap[name];
  return fn ? fn(size) : <Layers size={size} />;
}

/**
 * Per-file icon + colour metadata, keyed by canonical filenames (SOUL.md,
 * IDENTITY.md, …). Mirrors finnie's ``CARD_META`` so the file list shows
 * the same colour-coded badges users already recognise from the
 * Personalization page.
 *
 * Unknown filenames render a neutral ``FileText`` badge.
 */
export interface FileMeta {
  icon: ReactNode;
  color: string;
  label: string;
}

type Translator = (key: string) => string;

const FILE_META_MAP: Record<
  string,
  { icon: ReactNode; color: string; labelKey: string }
> = {
  "SOUL.md": {
    icon: <Sparkles size={20} />,
    color: "#7c3aed",
    labelKey: "experts.fileLabel.soul",
  },
  "IDENTITY.md": {
    icon: <Fingerprint size={20} />,
    color: "#db2777",
    labelKey: "experts.fileLabel.identity",
  },
  "USER.md": {
    icon: <User size={20} />,
    color: "#2563eb",
    labelKey: "experts.fileLabel.user",
  },
  "AGENTS.md": {
    icon: <BookOpen size={20} />,
    color: "#059669",
    labelKey: "experts.fileLabel.agents",
  },
  "TOOLS.md": {
    icon: <Wrench size={20} />,
    color: "#f59e0b",
    labelKey: "experts.fileLabel.tools",
  },
  "BOOTSTRAP.md": {
    icon: <Rocket size={20} />,
    color: "#d97706",
    labelKey: "experts.fileLabel.bootstrap",
  },
  "HEARTBEAT.md": {
    icon: <Heart size={20} />,
    color: "#ef4444",
    labelKey: "experts.fileLabel.heartbeat",
  },
  "SKILL.md": {
    icon: <Zap size={20} />,
    color: "#8b5cf6",
    labelKey: "experts.fileLabel.skill",
  },
  "MEMORY.md": {
    icon: <Layers size={20} />,
    color: "#0891b2",
    labelKey: "experts.fileLabel.memory",
  },
  "PROACTIVE.md": {
    icon: <Bell size={20} />,
    color: "#f97316",
    labelKey: "experts.fileLabel.proactive",
  },
};

export function metaForFile(
  path: string,
  t: Translator,
  fallbackColor?: string | null,
): FileMeta {
  const hit = FILE_META_MAP[path];
  if (hit) return { icon: hit.icon, color: hit.color, label: t(hit.labelKey) };
  return {
    icon: <FileText size={20} />,
    color: fallbackColor || "#6366f1",
    label: path.replace(/\.md$/i, ""),
  };
}
