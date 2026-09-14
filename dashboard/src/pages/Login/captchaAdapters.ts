export type CaptchaMode = "slider" | "checkbox" | "invisible" | "popup";

export type CaptchaWidgetAdapter = {
  slug: string;
  scriptSrc: string | ((siteKey: string) => string);
  globalName: string;
  onloadName?: string;
  mode: CaptchaMode;
};

export type PublicCaptchaConfig = {
  provider: string;
  site_key?: string;
};

export const CAPTCHA_WIDGETS: Record<string, CaptchaWidgetAdapter> = {
  slider: {
    slug: "slider",
    scriptSrc: "",
    globalName: "",
    mode: "slider",
  },
  turnstile: {
    slug: "turnstile",
    scriptSrc: "https://challenges.cloudflare.com/turnstile/v0/api.js",
    globalName: "turnstile",
    mode: "checkbox",
  },
  hcaptcha: {
    slug: "hcaptcha",
    scriptSrc:
      "https://js.hcaptcha.com/1/api.js?render=explicit&onload=__octopHcaptchaOnload",
    globalName: "hcaptcha",
    onloadName: "__octopHcaptchaOnload",
    mode: "checkbox",
  },
  recaptcha: {
    slug: "recaptcha",
    scriptSrc:
      "https://www.google.com/recaptcha/api.js?render=explicit&onload=__octopRecaptchaOnload",
    globalName: "grecaptcha",
    onloadName: "__octopRecaptchaOnload",
    mode: "checkbox",
  },
  "recaptcha-v3": {
    slug: "recaptcha-v3",
    scriptSrc: (siteKey: string) =>
      `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(
        siteKey,
      )}`,
    globalName: "grecaptcha",
    mode: "invisible",
  },
  tencent: {
    slug: "tencent",
    scriptSrc: "https://turing.captcha.qcloud.com/TJCaptcha.js",
    globalName: "TencentCaptcha",
    mode: "popup",
  },
};

export function loginCaptchaBody(
  username: string,
  password: string,
  token?: string,
): { username: string; password: string; captcha_token?: string } {
  if (token) {
    return { username, password, captcha_token: token };
  }
  return { username, password };
}
