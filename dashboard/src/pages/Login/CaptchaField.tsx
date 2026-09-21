import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import SlideCaptcha from "./SlideCaptcha";
import {
  CAPTCHA_WIDGETS,
  type CaptchaWidgetAdapter,
  type PublicCaptchaConfig,
} from "./captchaAdapters";

export type CaptchaFieldHandle = {
  getToken: () => Promise<string | undefined>;
};

export type CaptchaFieldProps = {
  config: PublicCaptchaConfig;
  resetKey?: number;
  slideHint: string;
  slideVerifiedLabel: string;
  unsupportedLabel: string;
  onReadyChange: (ready: boolean) => void;
};

type VendorApi = {
  render?: (
    host: HTMLElement,
    options: {
      sitekey: string;
      callback: (token: string) => void;
      "expired-callback": () => void;
      "error-callback": () => void;
      language?: string;
    },
  ) => string | number;
  remove?: (id: string | number) => void;
  reset?: (id?: string | number) => void;
  ready?: (cb: () => void) => void;
  execute?: (siteKey: string, opts: { action: string }) => Promise<string>;
};

function vendorGlobal(name: string): VendorApi | undefined {
  const value = (window as unknown as Record<string, unknown>)[name];
  if (value && typeof value === "object") {
    return value as VendorApi;
  }
  return undefined;
}

/** Widget language follows the dashboard UI locale, not the browser's. */
function vendorLang(lng: string): string {
  return lng.startsWith("zh") ? "zh-CN" : "en";
}

function loadVendorScript(
  adapter: CaptchaWidgetAdapter,
  siteKey: string,
  hl: string,
): Promise<VendorApi> {
  const src =
    typeof adapter.scriptSrc === "function"
      ? adapter.scriptSrc(siteKey, hl)
      : adapter.scriptSrc;
  return new Promise((resolve, reject) => {
    const existing = vendorGlobal(adapter.globalName);
    if (existing) {
      resolve(existing);
      return;
    }
    if (adapter.onloadName) {
      (window as unknown as Record<string, unknown>)[adapter.onloadName] =
        () => {
          const api = vendorGlobal(adapter.globalName);
          if (api) resolve(api);
          else reject(new Error("captcha global missing"));
        };
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.dataset.octopCaptcha = adapter.slug;
    if (!adapter.onloadName) {
      script.onload = () => {
        const api = vendorGlobal(adapter.globalName);
        if (api) resolve(api);
        else reject(new Error("captcha global missing"));
      };
    }
    script.onerror = () => reject(new Error("captcha script failed"));
    document.head.appendChild(script);
  });
}

type TencentCaptchaResult = {
  ret: number;
  ticket?: string;
  randstr?: string;
};

type TencentCaptchaCtor = new (
  appId: string,
  callback: (res: TencentCaptchaResult) => void,
  options?: Record<string, unknown>,
) => { show: () => void };

function tencentPopupToken(
  siteKey: string,
  hl: string,
): Promise<string | undefined> {
  const Ctor = (window as unknown as Record<string, unknown>).TencentCaptcha as
    | TencentCaptchaCtor
    | undefined;
  if (!Ctor) return Promise.resolve(undefined);
  return new Promise((resolve) => {
    try {
      const captcha = new Ctor(
        siteKey,
        (res) => {
          resolve(
            res && res.ret === 0 && res.ticket
              ? `${res.ticket}:${res.randstr ?? ""}`
              : undefined,
          );
        },
        { userLanguage: hl },
      );
      captcha.show();
    } catch {
      resolve(undefined);
    }
  });
}

type GeeTest4Init = (
  options: Record<string, unknown>,
  callback: (captcha: {
    onReady: (cb: () => void) => void;
    onSuccess: (cb: () => void) => void;
    onError: (cb: () => void) => void;
    onClose: (cb: () => void) => void;
    showCaptcha: () => void;
    getValidate: () =>
      | {
          lot_number: string;
          captcha_output: string;
          pass_token: string;
          gen_time: string;
        }
      | false
      | undefined;
  }) => void,
) => void;

/** GeeTest v4 bind-mode popup: token = JSON of getValidate() for the server. */
function geetestPopupToken(
  siteKey: string,
  hl: string,
): Promise<string | undefined> {
  const init = (window as unknown as Record<string, unknown>).initGeetest4 as
    | GeeTest4Init
    | undefined;
  if (!init) return Promise.resolve(undefined);
  return new Promise((resolve) => {
    let settled = false;
    const done = (token?: string) => {
      if (!settled) {
        settled = true;
        resolve(token);
      }
    };
    try {
      init(
        {
          captchaId: siteKey,
          product: "bind",
          protocol: "https://",
          language: hl.startsWith("zh") ? "zho" : "eng",
        },
        (captcha) => {
          captcha.onSuccess(() => {
            const validate = captcha.getValidate();
            done(
              validate && validate.captcha_output
                ? JSON.stringify({
                    lot_number: validate.lot_number,
                    captcha_output: validate.captcha_output,
                    pass_token: validate.pass_token,
                    gen_time: validate.gen_time,
                  })
                : undefined,
            );
          });
          captcha.onError(() => done(undefined));
          captcha.onClose(() => done(undefined));
          captcha.onReady(() => captcha.showCaptcha());
        },
      );
    } catch {
      done(undefined);
    }
  });
}

const CaptchaField = forwardRef<CaptchaFieldHandle, CaptchaFieldProps>(
  function CaptchaField(
    {
      config,
      resetKey = 0,
      slideHint,
      slideVerifiedLabel,
      unsupportedLabel,
      onReadyChange,
    },
    ref,
  ) {
    const adapter = CAPTCHA_WIDGETS[config.provider];
    const { i18n } = useTranslation();
    const hl = vendorLang(i18n.language);
    const hostRef = useRef<HTMLDivElement>(null);
    const widgetId = useRef<string | number | null>(null);
    const tokenRef = useRef<string | null>(null);
    const [slideVerified, setSlideVerified] = useState(false);

    useEffect(() => {
      setSlideVerified(false);
      tokenRef.current = null;
    }, [resetKey, config.provider]);

    useEffect(() => {
      if (!adapter || adapter.mode === "slider") {
        onReadyChange(slideVerified);
        return;
      }
      if (adapter.mode === "invisible" || adapter.mode === "popup") {
        onReadyChange(true);
        return;
      }
      onReadyChange(Boolean(tokenRef.current));
    }, [adapter, slideVerified, onReadyChange, resetKey, config.provider]);

    useEffect(() => {
      if (!adapter || adapter.mode !== "checkbox" || !config.site_key) {
        return;
      }
      let cancelled = false;
      const host = hostRef.current;
      void loadVendorScript(adapter, config.site_key, hl)
        .then((api) => {
          if (cancelled || !host || !api.render || !config.site_key) return;
          widgetId.current = api.render(host, {
            sitekey: config.site_key,
            ...(adapter.slug === "turnstile" ? { language: hl } : {}),
            callback: (token) => {
              tokenRef.current = token;
              onReadyChange(true);
            },
            "expired-callback": () => {
              tokenRef.current = null;
              onReadyChange(false);
            },
            "error-callback": () => {
              tokenRef.current = null;
              onReadyChange(false);
            },
          });
        })
        .catch(() => {
          if (!cancelled) onReadyChange(false);
        });
      return () => {
        cancelled = true;
        const api = vendorGlobal(adapter.globalName);
        if (widgetId.current != null && api) {
          if (typeof api.remove === "function") {
            api.remove(widgetId.current);
          } else if (typeof api.reset === "function") {
            api.reset(widgetId.current);
          }
        }
        widgetId.current = null;
        tokenRef.current = null;
        if (host) host.replaceChildren();
      };
    }, [adapter, config.site_key, hl, resetKey, onReadyChange]);

    useEffect(() => {
      if (
        !adapter ||
        (adapter.mode !== "invisible" && adapter.mode !== "popup") ||
        !config.site_key
      ) {
        return;
      }
      void loadVendorScript(adapter, config.site_key, hl).catch(
        () => undefined,
      );
    }, [adapter, config.site_key, hl, resetKey]);

    useImperativeHandle(
      ref,
      () => ({
        getToken: async () => {
          if (!adapter || adapter.mode === "slider") return undefined;
          if (adapter.mode === "checkbox") {
            return tokenRef.current ?? undefined;
          }
          if (adapter.mode === "popup") {
            if (!config.site_key) return undefined;
            return adapter.slug === "geetest-v4"
              ? geetestPopupToken(config.site_key, hl)
              : tencentPopupToken(config.site_key, hl);
          }
          const api = vendorGlobal(adapter.globalName);
          const siteKey = config.site_key;
          if (!api?.execute || !siteKey) return undefined;
          if (api.ready) {
            await new Promise<void>((resolve) => {
              api.ready!(resolve);
            });
          }
          return api.execute(siteKey, { action: "login" });
        },
      }),
      [adapter, config.site_key, hl],
    );

    if (!adapter) {
      return (
        <div data-testid="captcha-unsupported" role="alert">
          {unsupportedLabel}
        </div>
      );
    }

    if (adapter.mode === "slider") {
      return (
        <SlideCaptcha
          hint={slideHint}
          verifiedLabel={slideVerifiedLabel}
          onVerified={() => setSlideVerified(true)}
          resetKey={resetKey}
        />
      );
    }

    if (adapter.mode === "invisible") {
      return <div data-testid="captcha-invisible" hidden />;
    }

    if (adapter.mode === "popup") {
      return <div data-testid="captcha-popup" hidden />;
    }

    return <div data-testid="captcha-widget" ref={hostRef} />;
  },
);

export default CaptchaField;
