import type { CSSProperties } from "react";
import { Alert, App, Button, Input, Select, Switch } from "antd";
import {
  Activity,
  Cable,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CustomMcpTransport } from "../../../api/modules/connectors";
import {
  accentForServerName,
  friendlyServerLabel,
  type ServerCardState,
} from "./customMcpUtils";
import styles from "./index.module.less";

interface CustomMcpServerCardProps {
  card: ServerCardState;
  probing: boolean;
  authorizing?: boolean;
  oauthAvailable?: boolean;
  probeTools?: { name: string; description: string }[];
  transportOptions: { value: string; label: string }[];
  onUpdate: (key: string, patch: Partial<ServerCardState>) => void;
  onToggleEnabled: (enabled: boolean) => void;
  onRemove: () => void | Promise<void>;
  onProbe: () => void;
  onAuthorize?: () => void;
  onDefaultOpenChange?: (defaultOpen: boolean) => void;
}

export function CustomMcpServerCard({
  card,
  probing,
  authorizing = false,
  oauthAvailable = false,
  probeTools,
  transportOptions,
  onUpdate,
  onToggleEnabled,
  onRemove,
  onProbe,
  onAuthorize,
  onDefaultOpenChange,
}: CustomMcpServerCardProps) {
  const { t } = useTranslation();
  const { modal } = App.useApp();
  const isHttp = card.transport === "streamable_http";
  const label = friendlyServerLabel(card);
  const accent = accentForServerName(card.name.trim() || label);
  const summary = isHttp
    ? card.url.trim() || "https://…"
    : [
        card.command.trim(),
        ...card.argsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      ]
        .filter(Boolean)
        .join(" ") || "npx / uvx / python";

  const handleRemove = () => {
    modal.confirm({
      title: t("connectors.customMcp.deleteConfirm", {
        name: label,
        defaultValue: `确定删除 MCP 服务器「${label}」？`,
      }),
      content: t(
        "connectors.customMcp.deleteConfirmHint",
        "已保存的服务器将立即删除；尚未保存的配置只会从当前编辑中移除。",
      ),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: () => Promise.resolve(onRemove()),
    });
  };

  const authPending = isHttp && oauthAvailable && !card.oauthConfigured;
  const effectiveEnabled = !authPending && card.enabled;
  const showOAuthConnectLink =
    isHttp && card.collapsed && authPending && onAuthorize;
  const connectLabel = t("connectors.clickToConnect", "点击连接");

  const handleConnectClick = () => {
    if (oauthAvailable && onAuthorize) {
      onAuthorize();
    }
  };

  return (
    <div
      className={`${styles.customMcpServerCard}${
        card.collapsed ? "" : ` ${styles.customMcpServerCardOpen}`
      }${
        card.enabled && !authPending
          ? ""
          : ` ${styles.customMcpServerCardDisabled}`
      }`}
      style={
        {
          "--mcp-accent": accent,
        } as CSSProperties
      }
    >
      <div className={styles.customMcpServerTop}>
        <div className={styles.customMcpServerIdentity}>
          <span className={styles.customMcpServerIcon}>
            <Cable size={22} aria-hidden />
          </span>
          <div className={styles.customMcpServerMeta}>
            <span className={styles.customMcpServerName} title={label}>
              {label}
            </span>
            <span
              className={`${styles.customMcpTransportBadge} ${
                isHttp
                  ? styles.customMcpTransportHttp
                  : styles.customMcpTransportStdio
              }`}
            >
              {isHttp
                ? t("connectors.customMcp.transportHttp", "HTTP")
                : t("connectors.customMcp.transportStdio", "Stdio")}
            </span>
            <div className={styles.customMcpServerSummary} title={summary}>
              {card.displayName.trim() && card.name.trim()
                ? `${card.name.trim()} · ${summary}`
                : summary}
            </div>
          </div>
        </div>
        <div className={styles.customMcpServerControls}>
          <div className={styles.customMcpEnableControl}>
            <span className={styles.customMcpEnableLabel}>
              {t("connectors.customMcp.enable", "启用连接器")}
            </span>
            <Switch
              checked={authPending ? false : card.enabled}
              disabled={authPending}
              onChange={onToggleEnabled}
              size="small"
            />
          </div>
          <Button
            type="text"
            size="small"
            icon={
              card.collapsed ? (
                <ChevronDown size={16} />
              ) : (
                <ChevronUp size={16} />
              )
            }
            onClick={() => onUpdate(card.key, { collapsed: !card.collapsed })}
          />
          <Button
            type="text"
            size="small"
            danger
            icon={<Trash2 size={16} />}
            onClick={handleRemove}
          />
        </div>
      </div>

      {showOAuthConnectLink ? (
        <div className={styles.customMcpCardFooter}>
          <button
            type="button"
            className={styles.customMcpConnectLink}
            onClick={handleConnectClick}
            disabled={authorizing}
          >
            {authorizing
              ? t("connectors.customMcp.authorizing", "授权中…")
              : connectLabel}
          </button>
        </div>
      ) : null}

      {!card.collapsed ? (
        <div className={styles.customMcpCardBody}>
          <div className={styles.customMcpField}>
            <label>{t("connectors.customMcp.displayName", "显示名称")}</label>
            <Input
              value={card.displayName}
              onChange={(e) =>
                onUpdate(card.key, { displayName: e.target.value })
              }
              placeholder={t(
                "connectors.customMcp.displayNamePlaceholder",
                "例如：我的知识库",
              )}
              maxLength={64}
            />
            <div className={styles.customMcpFieldHint}>
              {t(
                "connectors.customMcp.displayNameHint",
                "在对话连接器选择中显示的名称，可使用中文。",
              )}
            </div>
          </div>
          <div className={styles.customMcpField}>
            <label>
              {t("connectors.customMcp.serverId", "服务器 ID")}{" "}
              <span className={styles.requiredMark}>*</span>
            </label>
            <Input
              value={card.name}
              onChange={(e) => onUpdate(card.key, { name: e.target.value })}
              placeholder={isHttp ? "http-server" : "stdio-server"}
            />
            <div className={styles.customMcpFieldHint}>
              {t(
                "connectors.customMcp.serverIdHint",
                "技术标识，仅支持字母、数字、下划线与连字符。",
              )}
            </div>
          </div>
          <div className={styles.customMcpField}>
            <label>Transport</label>
            <Select
              value={card.transport}
              options={transportOptions}
              onChange={(value: CustomMcpTransport) =>
                onUpdate(card.key, { transport: value })
              }
              style={{ width: "100%" }}
            />
          </div>

          {isHttp ? (
            <>
              <div className={styles.customMcpField}>
                <label>
                  URL <span className={styles.requiredMark}>*</span>
                </label>
                <Input
                  value={card.url}
                  onChange={(e) => onUpdate(card.key, { url: e.target.value })}
                  placeholder="https://mcp.example.com/mcp"
                />
              </div>
              <div className={styles.customMcpField}>
                <label>
                  {t(
                    "connectors.customMcp.headers",
                    "Headers（每行 Key: Value，可选 Bearer）",
                  )}
                </label>
                <Input.TextArea
                  value={card.headersText}
                  onChange={(e) =>
                    onUpdate(card.key, { headersText: e.target.value })
                  }
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  placeholder={"Authorization: Bearer sk-..."}
                />
              </div>
            </>
          ) : (
            <>
              <div className={styles.customMcpField}>
                <label>
                  Command <span className={styles.requiredMark}>*</span>
                </label>
                <Input
                  value={card.command}
                  onChange={(e) =>
                    onUpdate(card.key, { command: e.target.value })
                  }
                  placeholder="npx / uvx / python"
                />
              </div>
              <div className={styles.customMcpField}>
                <label>
                  {t("connectors.customMcp.args", "Args（一行一个参数）")}
                </label>
                <Input.TextArea
                  value={card.argsText}
                  onChange={(e) =>
                    onUpdate(card.key, { argsText: e.target.value })
                  }
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  placeholder={"-y\nsome-mcp-package"}
                />
              </div>
              <div className={styles.customMcpField}>
                <label>
                  {t("connectors.customMcp.env", "Env（每行 KEY=VALUE）")}
                </label>
                <Input.TextArea
                  value={card.envText}
                  onChange={(e) =>
                    onUpdate(card.key, { envText: e.target.value })
                  }
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  placeholder={"API_KEY=..."}
                />
              </div>
            </>
          )}

          <div className={styles.customMcpField}>
            <label>
              {t("connectors.customMcp.defaultOpen", "对话默认选中")}
            </label>
            <div className={styles.customMcpDefaultOpenRow}>
              <Switch
                checked={card.defaultOpen}
                disabled={!effectiveEnabled}
                onChange={(checked) => {
                  if (onDefaultOpenChange) {
                    onDefaultOpenChange(checked);
                    return;
                  }
                  onUpdate(card.key, { defaultOpen: checked });
                }}
              />
              {!effectiveEnabled ? (
                <span className={styles.customMcpFieldHint}>
                  {t(
                    "connectors.customMcp.defaultOpenRequiresEnable",
                    "需先启用连接器。",
                  )}
                </span>
              ) : !card.defaultOpen ? (
                <span className={styles.customMcpFieldHint}>
                  {t(
                    "connectors.customMcp.defaultOpenHint",
                    "开启后，你的 Dashboard、IM 与 Cron（未手动选连接器时）会默认带上此 MCP。",
                  )}
                </span>
              ) : null}
            </div>
            {effectiveEnabled && card.defaultOpen ? (
              <Alert
                type="warning"
                showIcon
                message={t(
                  "connectors.defaultOpenWarning",
                  "开启后默认会在你的 Dashboard、IM 与 Cron（未特殊选连接器时）携带该工具（额外消耗 token）。Dashboard 可关本轮；Cron 若显式选择连接器则以选择为准。",
                )}
              />
            ) : null}
          </div>

          {isHttp && card.oauthConfigured ? (
            <Alert
              type="success"
              showIcon
              message={t(
                "connectors.customMcp.oauthConfigured",
                "已完成 OAuth 授权",
              )}
            />
          ) : null}

          {isHttp && oauthAvailable && !card.oauthConfigured ? (
            <Alert
              type="warning"
              showIcon
              message={t(
                "connectors.customMcp.probeNeedsOAuth",
                "此 MCP 需要 OAuth 授权才能访问",
              )}
              description={t(
                "connectors.customMcp.oauthAuthorizeHint",
                "点击「一键授权」完成登录；完成后我们会自动再次验证连接。",
              )}
              action={
                onAuthorize ? (
                  <Button
                    size="small"
                    type="primary"
                    loading={authorizing}
                    onClick={onAuthorize}
                  >
                    {t("connectors.oneClickOAuth", "一键授权")}
                  </Button>
                ) : undefined
              }
            />
          ) : null}

          {isHttp ? (
            <div className={styles.customMcpCardActions}>
              <Button
                icon={<Activity size={14} />}
                loading={probing}
                onClick={onProbe}
              >
                {t("connectors.probe", "探测")}
              </Button>
            </div>
          ) : null}

          {isHttp && probeTools !== undefined ? (
            <div className={styles.probeResult}>
              <div className={styles.probeResultHeader}>
                <CheckCircle2
                  size={18}
                  className={styles.probeResultIcon}
                  aria-hidden
                />
                <div className={styles.probeResultMeta}>
                  <div className={styles.probeResultTitle}>
                    {t("connectors.probeToolsTitle", "探测成功")}
                  </div>
                  <div className={styles.probeResultSubtitle}>
                    {probeTools.length > 0
                      ? t("connectors.probeToolsHint", {
                          count: probeTools.length,
                          defaultValue: `连接正常，获取以下工具列表（共 ${probeTools.length} 个）`,
                        })
                      : t(
                          "connectors.probeToolsEmpty",
                          "连接正常，但未发现可用工具",
                        )}
                  </div>
                </div>
              </div>
              {probeTools.length > 0 ? (
                <ul className={styles.probeToolList}>
                  {probeTools.map((tool, index) => (
                    <li key={tool.name} className={styles.probeToolItem}>
                      <span className={styles.probeToolIndex}>{index + 1}</span>
                      <div className={styles.probeToolBody}>
                        <div className={styles.probeToolName}>{tool.name}</div>
                        {tool.description ? (
                          <div className={styles.probeToolDesc}>
                            {tool.description}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
