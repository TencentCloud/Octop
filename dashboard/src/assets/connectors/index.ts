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
  return CONNECTOR_LOGOS[kind];
}
