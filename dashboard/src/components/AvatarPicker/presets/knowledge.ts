import {
  Atom,
  BookOpen,
  Briefcase,
  Cpu,
  FlaskConical,
  GraduationCap,
  Landmark,
  Languages,
  Palette,
  Scale,
  Terminal,
  Users,
  Wrench,
} from "lucide-react";

import type { AvatarPreset } from "../types";

/** Prefabricated Lucide icons for knowledge bases (``icon_name``). */
export const KNOWLEDGE_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "book-open",
    labelKey: "knowledgeBases.iconLabels.book-open",
    Icon: BookOpen,
    tone: "plain",
  },
  {
    id: "landmark",
    labelKey: "knowledgeBases.iconLabels.landmark",
    Icon: Landmark,
    tone: "plain",
  },
  {
    id: "users",
    labelKey: "knowledgeBases.iconLabels.users",
    Icon: Users,
    tone: "plain",
  },
  {
    id: "scale",
    labelKey: "knowledgeBases.iconLabels.scale",
    Icon: Scale,
    tone: "plain",
  },
  {
    id: "flask-conical",
    labelKey: "knowledgeBases.iconLabels.flask-conical",
    Icon: FlaskConical,
    tone: "plain",
  },
  {
    id: "atom",
    labelKey: "knowledgeBases.iconLabels.atom",
    Icon: Atom,
    tone: "plain",
  },
  {
    id: "wrench",
    labelKey: "knowledgeBases.iconLabels.wrench",
    Icon: Wrench,
    tone: "plain",
  },
  {
    id: "cpu",
    labelKey: "knowledgeBases.iconLabels.cpu",
    Icon: Cpu,
    tone: "plain",
  },
  {
    id: "terminal",
    labelKey: "knowledgeBases.iconLabels.terminal",
    Icon: Terminal,
    tone: "plain",
  },
  {
    id: "graduation-cap",
    labelKey: "knowledgeBases.iconLabels.graduation-cap",
    Icon: GraduationCap,
    tone: "plain",
  },
  {
    id: "briefcase",
    labelKey: "knowledgeBases.iconLabels.briefcase",
    Icon: Briefcase,
    tone: "plain",
  },
  {
    id: "palette",
    labelKey: "knowledgeBases.iconLabels.palette",
    Icon: Palette,
    tone: "plain",
  },
  {
    id: "languages",
    labelKey: "knowledgeBases.iconLabels.languages",
    Icon: Languages,
    tone: "plain",
  },
];
