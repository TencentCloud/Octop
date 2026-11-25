import {
  Bot,
  Cable,
  Cpu,
  Globe,
  Plug,
  Server,
  Sparkles,
  Terminal,
  Wrench,
} from "lucide-react";

import type { AvatarPreset } from "../types";

/** Prefabricated icons for a user-defined connector (``avatar_icon``). */
export const CONNECTOR_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "plug",
    labelKey: "connectors.customMcp.iconLabels.plug",
    Icon: Plug,
    tone: "plain",
  },
  {
    id: "cable",
    labelKey: "connectors.customMcp.iconLabels.cable",
    Icon: Cable,
    tone: "plain",
  },
  {
    id: "globe",
    labelKey: "experts.iconLabels.globe",
    Icon: Globe,
    tone: "plain",
  },
  {
    id: "server",
    labelKey: "experts.iconLabels.server",
    Icon: Server,
    tone: "plain",
  },
  {
    id: "bot",
    labelKey: "connectors.customMcp.iconLabels.bot",
    Icon: Bot,
    tone: "plain",
  },
  {
    id: "wrench",
    labelKey: "experts.iconLabels.wrench",
    Icon: Wrench,
    tone: "plain",
  },
  {
    id: "terminal",
    labelKey: "experts.iconLabels.terminal",
    Icon: Terminal,
    tone: "plain",
  },
  {
    id: "cpu",
    labelKey: "experts.iconLabels.cpu",
    Icon: Cpu,
    tone: "plain",
  },
  {
    id: "sparkles",
    labelKey: "experts.iconLabels.sparkles",
    Icon: Sparkles,
    tone: "plain",
  },
];
