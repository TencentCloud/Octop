import type { CSSProperties } from "react";
import { Button, Input, Modal, Select, Switch } from "antd";
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
import { accentForServerName, type ServerCardState } from "./customMcpUtils";
import styles from "./index.module.less";

interface CustomMcpServerCardProps {
  card: ServerCardState;
  probing: boolean;
  probeTools?: { name: string; description: string }[];
  transportOptions: { value: string; label: string }[];
  onUpdate: (key: string, patch: Partial<ServerCardState>) => void;
  onToggleEnabled: (enabled: boolean) => void;
  onRemove: () => void;
  onProbe: () => void;
}

export function CustomMcpServerCard({
  card,
  probing,
  probeTools,
  transportOptions,
  onUpdate,
  onToggleEnabled,
  onRemove,
  onProbe,
}: CustomMcpServerCardProps) {
  const { t } = useTranslation();
  const isHttp = card.transport === "streamable_http";
  const displayName =
    card.name.trim() || (isHttp ? "http-server" : "stdio-server");
  const accent = accentForServerName(displayName);
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
    Modal.confirm({
      title: t("connectors.customMcp.deleteConfirm", {
        name: displayName,
        defaultValue: `确定删除 MCP 服务器「${displayName}」？`,
      }),
      content: t(
        "connectors.customMcp.deleteConfirmHint",
        "删除后需点击保存才会生效。",
      ),
      okText: t("common.delete"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: onRemove,
    });
  };

  return (
    <div
      className={`${styles.customMcpServerCard}${
        card.collapsed ? "" : ` ${styles.customMcpServerCardOpen}`
      }${card.enabled ? "" : ` ${styles.customMcpServerCardDisabled}`}`}
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
            <span className={styles.customMcpServerName} title={displayName}>
              {displayName}
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
              {summary}
            </div>
          </div>
        </div>
        <div className={styles.customMcpServerControls}>
          <Switch
            checked={card.enabled}
            onChange={onToggleEnabled}
            size="small"
          />
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

      {!card.collapsed ? (
        <div className={styles.customMcpCardBody}>
          <div className={styles.customMcpField}>
            <label>{t("connectors.displayName", "显示名称")}</label>
            <Input
              value={card.name}
              onChange={(e) => onUpdate(card.key, { name: e.target.value })}
              placeholder={isHttp ? "http-server" : "stdio-server"}
            />
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

          <div className={styles.customMcpCardActions}>
            <Button
              icon={<Activity size={14} />}
              loading={probing}
              onClick={onProbe}
            >
              {t("connectors.probe", "探测")}
            </Button>
          </div>

          {probeTools !== undefined ? (
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
