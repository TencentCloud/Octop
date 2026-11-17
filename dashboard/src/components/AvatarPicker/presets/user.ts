import { UserRound } from "lucide-react";

import adminPortrait from "../../../assets/avatars/admin.png";
import bossPortrait from "../../../assets/avatars/boss.png";
import doctorPortrait from "../../../assets/avatars/doctor.png";
import financePortrait from "../../../assets/avatars/finance.png";
import nursePortrait from "../../../assets/avatars/nurse.png";
import opsPortrait from "../../../assets/avatars/ops.png";
import staffPortrait from "../../../assets/avatars/staff.png";
import studentPortrait from "../../../assets/avatars/student.png";
import supportPortrait from "../../../assets/avatars/support.png";
import teacherPortrait from "../../../assets/avatars/teacher.png";
import type { AvatarPreset } from "../types";

/** Prefabricated portraits for users / groups (personal settings). */
export const USER_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "user",
    labelKey: "adminUsers.avatarIconUser",
    bg: "#e8f1ff",
    fg: "#175cd3",
    Icon: UserRound,
    tone: "tinted",
  },
  {
    id: "admin",
    labelKey: "adminUsers.avatarIconAdmin",
    src: adminPortrait,
  },
  {
    id: "staff",
    labelKey: "adminUsers.avatarIconStaff",
    src: staffPortrait,
  },
  {
    id: "doctor",
    labelKey: "adminUsers.avatarIconDoctor",
    src: doctorPortrait,
  },
  {
    id: "nurse",
    labelKey: "adminUsers.avatarIconNurse",
    src: nursePortrait,
  },
  {
    id: "student",
    labelKey: "adminUsers.avatarIconStudent",
    src: studentPortrait,
  },
  {
    id: "teacher",
    labelKey: "adminUsers.avatarIconTeacher",
    src: teacherPortrait,
  },
  {
    id: "support",
    labelKey: "adminUsers.avatarIconSupport",
    src: supportPortrait,
  },
  {
    id: "ops",
    labelKey: "adminUsers.avatarIconOps",
    src: opsPortrait,
  },
  {
    id: "finance",
    labelKey: "adminUsers.avatarIconFinance",
    src: financePortrait,
  },
  {
    id: "boss",
    labelKey: "adminUsers.avatarIconBoss",
    src: bossPortrait,
  },
];
