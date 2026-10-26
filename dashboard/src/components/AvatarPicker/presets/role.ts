import {
  Code2,
  Cog,
  Crown,
  Feather,
  Landmark,
  Megaphone,
  PieChart,
  Users,
} from "lucide-react";

import type { AvatarPreset } from "../types";

/** Prefabricated Lucide icons for admin roles. */
export const ROLE_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "member",
    labelKey: "adminUsers.avatarIconMember",
    Icon: Users,
    tone: "plain",
  },
  {
    id: "award",
    labelKey: "adminUsers.avatarIconAward",
    Icon: Crown,
    tone: "plain",
  },
  {
    id: "terminal",
    labelKey: "adminUsers.avatarIconTerminal",
    Icon: Code2,
    tone: "plain",
  },
  {
    id: "pen",
    labelKey: "adminUsers.avatarIconPen",
    Icon: Feather,
    tone: "plain",
  },
  {
    id: "chart",
    labelKey: "adminUsers.avatarIconChart",
    Icon: PieChart,
    tone: "plain",
  },
  {
    id: "headset",
    labelKey: "adminUsers.avatarIconHeadset",
    Icon: Megaphone,
    tone: "plain",
  },
  {
    id: "wrench",
    labelKey: "adminUsers.avatarIconWrench",
    Icon: Cog,
    tone: "plain",
  },
  {
    id: "scale",
    labelKey: "adminUsers.avatarIconScale",
    Icon: Landmark,
    tone: "plain",
  },
];
