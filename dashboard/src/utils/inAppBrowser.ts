/**
 * Chat / social app WebViews (WeChat, WeCom, QQ, DingTalk, Feishu, Weibo,
 * Alipay) refuse to save `blob:` downloads and only tell the user to open the
 * page in a browser, which has no Octop session.
 */
const IN_APP_BROWSER_UA =
  /MicroMessenger|wxwork|\bQQ\/|DingTalk|Lark\/|Feishu|Weibo|AlipayClient/i;

export function isInAppBrowser(userAgent = navigator.userAgent): boolean {
  return IN_APP_BROWSER_UA.test(userAgent);
}
