/**
 * 云服务器模块统一色彩语义：
 *   < 40%        → 绿
 *   40%–60%      → 蓝
 *   60%–80%      → 橙
 *   ≥ 80%        → 红
 *   无采样 / 离线 → 灰
 */

export type ToneKey = "good" | "normal" | "warn" | "alert" | "offline";

export type Tone = {
  key: ToneKey;
  /** 主色：圆环进度、进度条、热力格 */
  stroke: string;
  /** 轨道底色 */
  track: string;
  /** 文字色 */
  ink: string;
  /** 徽章底色 */
  bg: string;
  /** 中文标签 */
  label: string;
};

export const TONE: Record<ToneKey, Tone> = {
  good: {
    key: "good",
    stroke: "#2fae87",
    track: "#e4f4ee",
    ink: "#138c6b",
    bg: "#eaf8f1",
    label: "充足",
  },
  normal: {
    key: "normal",
    stroke: "#4a86d8",
    track: "#e6eefb",
    ink: "#2f6fb5",
    bg: "#e9f1fb",
    label: "正常",
  },
  warn: {
    key: "warn",
    stroke: "#e6862a",
    track: "#fdf1e4",
    ink: "#c56a12",
    bg: "#fdf3e8",
    label: "偏高",
  },
  alert: {
    key: "alert",
    stroke: "#df5665",
    track: "#fbe7e9",
    ink: "#c64756",
    bg: "#fdefef",
    label: "告警",
  },
  offline: {
    key: "offline",
    stroke: "#c7ced9",
    track: "#eef1f5",
    ink: "#8b939f",
    bg: "#f0f2f5",
    label: "无采样",
  },
};

/** 四档分界：蓝从 40 起，橙从 60 起，红从 80 起。 */
export const BLUE_MIN = 40;
export const WARN_MIN = 60;
export const ALERT_MIN = 80;

/** 按资源水位取色。缺测为灰，不把空值当成 0。 */
export function levelTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return TONE.offline;
  }
  if (value >= ALERT_MIN) return TONE.alert;
  if (value >= WARN_MIN) return TONE.warn;
  if (value >= BLUE_MIN) return TONE.normal;
  return TONE.good;
}

/** 与 levelTone 同一套分界，供热力格下标使用。 */
export function levelIndex(value: number | null | undefined): number | null {
  const key = levelTone(value).key;
  if (key === "offline") return null;
  if (key === "alert") return 3;
  if (key === "warn") return 2;
  if (key === "normal") return 1;
  return 0;
}

export const LEVEL_LABELS = ["<40%", "40–59%", "60–79%", "≥80%"] as const;

/**
 * 节点健康色：健康绿，关注（60%–80%）橙，异常 / 告警（≥80%）红，离线灰。
 */
export function healthTone(health: string): Tone {
  if (health === "offline" || health === "unknown") return TONE.offline;
  if (health === "critical" || health === "alert") return TONE.alert;
  if (health === "warning" || health === "warn" || health === "abnormal")
    return TONE.warn;
  return TONE.good;
}

/** 热力条四档，与资源水位同色。 */
export const HEAT_COLORS = [
  TONE.good.stroke,
  TONE.normal.stroke,
  TONE.warn.stroke,
  TONE.alert.stroke,
];

/** 趋势曲线配色：主色偏蓝，网络保留青/绿以区分上下行。 */
export const SERIES_COLOR = {
  cpu: "#4a86d8",
  mem: "#8b7fd4",
  load: "#5f7d99",
  net_in: "#4a9fc4",
  net_out: "#3fa98a",
} as const;
