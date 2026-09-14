/** Catalog of App-ID OAuth providers shown under the admin SSO OAuth family. */

export type OauthAppKind = "feishu" | "dingtalk" | "wecom";

export interface OauthProviderDef {
  kind: OauthAppKind;
  /** When false, show a collapsed placeholder until the adapter ships. */
  available: boolean;
  titleKey: string;
  descKey: string;
  /** Fallback login button label when display_name is empty. */
  defaultNameKey: string;
  enabledAriaKey: string;
  /** Feishu/Lark region selector. */
  hasRegion?: boolean;
  /** WeCom CorpApp Agent ID in ``extra.agent_id``. */
  hasAgentId?: boolean;
  /** Override default App ID field label (e.g. WeCom CorpID). */
  clientIdKey?: string;
  /** Override default App Secret field label. */
  clientSecretKey?: string;
}

export const OAUTH_APP_PROVIDERS: OauthProviderDef[] = [
  {
    kind: "feishu",
    available: true,
    titleKey: "adminSso.feishuTitle",
    descKey: "adminSso.feishuDesc",
    defaultNameKey: "login.providerKind.feishu",
    enabledAriaKey: "adminSso.feishuEnabled",
    hasRegion: true,
  },
  {
    kind: "dingtalk",
    available: true,
    titleKey: "adminSso.dingtalkTitle",
    descKey: "adminSso.dingtalkDesc",
    defaultNameKey: "login.providerKind.dingtalk",
    enabledAriaKey: "adminSso.dingtalkEnabled",
  },
  {
    kind: "wecom",
    available: true,
    titleKey: "adminSso.wecomTitle",
    descKey: "adminSso.wecomDesc",
    defaultNameKey: "login.providerKind.wecom",
    enabledAriaKey: "adminSso.wecomEnabled",
    hasAgentId: true,
    clientIdKey: "adminSso.wecomCorpId",
    clientSecretKey: "adminSso.wecomSecret",
  },
];
