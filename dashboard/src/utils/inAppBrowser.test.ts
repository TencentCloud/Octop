import { describe, expect, it } from "vitest";

import { isInAppBrowser } from "./inAppBrowser";

const WECHAT_ANDROID =
  "Mozilla/5.0 (Linux; Android 14; V2307A Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.6723.103 Mobile Safari/537.36 XWEB/1300333 MMWEBSDK/20240802 MMWEBID/8650 MicroMessenger/8.0.51.2720(0x28003336) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64";
const WECHAT_IOS =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.50(0x1800323c) NetType/WIFI Language/zh_CN";
const MOBILE_QQ =
  "Mozilla/5.0 (Linux; Android 13; PHB110 Build/TP1A.220905.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.168 Mobile Safari/537.36 V1_AND_SQ_9.0.65_6298_YYB_D QQ/9.0.65.17090 NetType/WIFI WebP/0.3.0 AppId/537224486";
const DINGTALK =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 AliApp(DingTalk/7.5.20) com.laiwang.DingTalk/34389442 Channel/201200 language/zh-Hans-CN UT4Aplus/0.0.6 WK";
const FEISHU =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Lark/7.14.6 LarkLocale/zh_CN ChannelName/Feishu TTWebView/1121";
const QQ_BROWSER =
  "Mozilla/5.0 (Linux; U; Android 13; zh-cn; PHB110 Build/TP1A.220905.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.86 MQQBrowser/14.8 Mobile Safari/537.36";
const CHROME_ANDROID =
  "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36";
const SAFARI_IOS =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";

describe("isInAppBrowser", () => {
  it.each([WECHAT_ANDROID, WECHAT_IOS, MOBILE_QQ, DINGTALK, FEISHU])(
    "detects chat-app WebViews: %s",
    (ua) => {
      expect(isInAppBrowser(ua)).toBe(true);
    },
  );

  it.each([QQ_BROWSER, CHROME_ANDROID, SAFARI_IOS])(
    "leaves real browsers alone: %s",
    (ua) => {
      expect(isInAppBrowser(ua)).toBe(false);
    },
  );
});
