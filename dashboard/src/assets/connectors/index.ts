import baiduMap from "./baidu-map.png";
import ctripWendao from "./ctrip-wendao.png";
import fliggy from "./fliggy.png";
import meituanTravel from "./meituan-travel.png";
import notion from "./notion.png";
import qqMail from "./qq-mail.png";
import qqMusic from "./qq-music.png";
import tencentDocs from "./tencent-docs.png";
import tencentIma from "./tencent-ima.png";
import tencentMeeting from "./tencent-meeting.png";
import tencentNews from "./tencent-news.png";
import tencentLexiang from "./tencent-lexiang.png";
import tencentWeiyun from "./tencent-weiyun.png";
import wechatReading from "./wechat-reading.png";
import youdaoNote from "./youdao-note.png";
import yuandian from "./yuandian.png";

export const CONNECTOR_LOGOS: Record<string, string> = {
  "tencent-docs": tencentDocs,
  "baidu-map": baiduMap,
  "qq-mail": qqMail,
  "qq-music": qqMusic,
  fliggy,
  "ctrip-wendao": ctripWendao,
  "meituan-travel": meituanTravel,
  yuandian,
  "tencent-ima": tencentIma,
  "tencent-lexiang": tencentLexiang,
  "tencent-meeting": tencentMeeting,
  notion,
  "tencent-news": tencentNews,
  "wechat-reading": wechatReading,
  "youdao-note": youdaoNote,
  "tencent-weiyun": tencentWeiyun,
};

export function getConnectorLogo(kind: string): string | undefined {
  if (!kind) return undefined;
  const direct = CONNECTOR_LOGOS[kind];
  if (direct) return direct;
  // Tolerate minor kind drift between a connector instance and the catalog
  // (e.g. a dev-era "baidu_map" persisted on an instance vs the finalized
  // "baidu-map" used as the logo key). Without this, the chat connector
  // picker (which renders instance.kind) falls back to a placeholder while
  // the catalog grid (entry.kind) still shows the logo.
  const normalized = kind.toLowerCase().replace(/[_\s]+/g, "-");
  if (normalized !== kind) {
    const fallback = CONNECTOR_LOGOS[normalized];
    if (fallback) return fallback;
  }
  return undefined;
}
