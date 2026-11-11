import {
  BookOpen,
  Cpu,
  Network,
  Package,
  Palette,
  PenTool,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wrench,
  Zap,
} from "lucide-react";

import type { AvatarPreset } from "../types";

/** Prefabricated Lucide icons for skill packages (``icon_name``). */
export const SKILL_PACKAGE_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "package",
    labelKey: "avatarPicker.presets.skill.package",
    Icon: Package,
    tone: "plain",
  },
  {
    id: "sparkles",
    labelKey: "experts.iconLabels.sparkles",
    Icon: Sparkles,
    tone: "plain",
  },
  {
    id: "zap",
    labelKey: "experts.iconLabels.zap",
    Icon: Zap,
    tone: "plain",
  },
  {
    id: "pen-tool",
    labelKey: "experts.iconLabels.pen-tool",
    Icon: PenTool,
    tone: "plain",
  },
  {
    id: "cpu",
    labelKey: "experts.iconLabels.cpu",
    Icon: Cpu,
    tone: "plain",
  },
  {
    id: "terminal",
    labelKey: "experts.iconLabels.terminal",
    Icon: Terminal,
    tone: "plain",
  },
  {
    id: "wrench",
    labelKey: "experts.iconLabels.wrench",
    Icon: Wrench,
    tone: "plain",
  },
  {
    id: "book-open",
    labelKey: "experts.iconLabels.book-open",
    Icon: BookOpen,
    tone: "plain",
  },
  {
    id: "palette",
    labelKey: "experts.iconLabels.palette",
    Icon: Palette,
    tone: "plain",
  },
  {
    id: "network",
    labelKey: "experts.iconLabels.network",
    Icon: Network,
    tone: "plain",
  },
  {
    id: "shield-check",
    labelKey: "experts.iconLabels.shield-check",
    Icon: ShieldCheck,
    tone: "plain",
  },
];
