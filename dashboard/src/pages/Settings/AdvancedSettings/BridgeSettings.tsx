import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  Button,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Segmented,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { message } from "@/utils/antdMessage";
import {
  Activity,
  CheckCircle,
  Globe,
  LayoutGrid,
  List,
  Lock,
  Cloudy,
  Plus,
  Pencil,
  RefreshCw,
  Share2,
  Tag as TagIcon,
  Trash2,
  Unplug,
  User,
  AlertCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { OctopEmptyMascot } from "../../../components/EmptyState";
import StreamSetupGuide from "../../../components/StreamSetupGuide/StreamSetupGuide";
import { useAgent } from "../../../context/AgentContext";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { apiErrorMessage } from "../../../utils/apiError";
import { ExpertIcon, iconForName } from "../../Experts/components/iconForName";
import {
  bridgeApi,
  type BridgeConnection,
  type BridgeProbeAgent,
  type BridgeProbeResult,
  type BridgeRemoteAgent,
} from "../../../api/modules/bridge";
import {
  inboundPeerAddress,
  inboundSourceIp,
  peerHostLabel,
} from "./bridgePeerLabel";
import { TabPanelHeader } from "./TabPanelHeader";
import styles from "./BridgeSettings.module.less";

const BRIDGE_ACCENT = "var(--fn-color-brand)";
const DEFAULT_BRIDGE_ICON = "cloudy";
const MAX_BRIDGE_CONNECTIONS = 10;
const BRIDGE_ICON_OPTIONS = [
  "cloudy",
  "cloud",
  "cloud-cog",
  "globe",
  "home",
  "laptop",
  "monitor",
  "server",
  "radio-tower",
  "wifi",
  "satellite",
  "map-pin",
] as const;

const FIELD_ICON = {
  size: 16 as const,
  style: { color: "var(--fn-text-tertiary)" },
};

function BridgeIconPicker({
  value,
  onChange,
}: {
  value?: string;
  onChange?: (value?: string) => void;
}) {
  const { t } = useTranslation();
  const current = (value || DEFAULT_BRIDGE_ICON).trim() || DEFAULT_BRIDGE_ICON;
  return (
    <div className={styles.iconPicker}>
      {BRIDGE_ICON_OPTIONS.map((name) => {
        const selected = current === name;
        return (
          <button
            key={name}
            type="button"
            title={t(`advancedSettings.bridge.iconLabels.${name}`)}
            className={
              styles.iconOption +
              (selected ? ` ${styles.iconOptionActive}` : "")
            }
            onClick={() => onChange?.(name)}
          >
            {iconForName(name, 16)}
          </button>
        );
      })}
    </div>
  );
}

function statusColor(status: string): string {
  if (status === "connected") return "success";
  if (status === "connecting" || status === "error") return "warning";
  return "default";
}

function isInboundConnection(row: BridgeConnection): boolean {
  return Boolean(row.inbound) || !row.has_password;
}

function connectionStatusText(
  row: BridgeConnection,
  t: (key: string) => string,
): string {
  if (isInboundConnection(row) && row.status !== "connected") {
    return t("advancedSettings.bridge.status.offline");
  }
  return t(`advancedSettings.bridge.status.${row.status}`);
}

function InboundPeerFacts({ row }: { row: BridgeConnection }) {
  const { t } = useTranslation();
  const address = inboundPeerAddress(row);
  const sourceIp = inboundSourceIp(row);
  return (
    <>
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>
          {t("advancedSettings.bridge.peerUrl")}:
        </span>
        <span className={styles.infoValue} title={address || undefined}>
          {address ? peerHostLabel(address) : "—"}
        </span>
      </div>
      {sourceIp ? (
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>
            {t("advancedSettings.bridge.peerIp")}:
          </span>
          <span className={styles.infoValue}>{sourceIp}</span>
        </div>
      ) : null}
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>
          {t("advancedSettings.bridge.peerAccount")}:
        </span>
        <span
          className={styles.infoValue}
          title={t("advancedSettings.bridge.peerAccountHint")}
        >
          {row.peer_username}
        </span>
      </div>
    </>
  );
}

function InboundLockedControl({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <Tooltip title={t("advancedSettings.bridge.inboundActionDisabled")}>
      <span className={styles.inboundLocked}>{children}</span>
    </Tooltip>
  );
}

const CARD_AGENT_PREVIEW_LIMIT = 4;

function AgentAvatar({
  name,
  iconUrl,
  iconName,
  color,
}: {
  name: string;
  iconUrl?: string | null;
  iconName?: string | null;
  color?: string | null;
}) {
  return (
    <span
      className={styles.probeAvatar}
      style={{ color: color || "var(--fn-color-brand, #e85d75)" }}
      aria-label={name}
    >
      <ExpertIcon
        iconUrl={iconUrl}
        iconName={iconName}
        size={40}
        className={styles.probeAvatarImg}
      />
    </span>
  );
}

function KindTag({ kind }: { kind?: string | null }) {
  const { t } = useTranslation();
  const isTeam = kind === "team";
  return (
    <Tag color={isTeam ? "purple" : "blue"} style={{ marginInlineEnd: 0 }}>
      {isTeam
        ? t("advancedSettings.bridge.kindTeam")
        : t("advancedSettings.bridge.kindExpert")}
    </Tag>
  );
}

function AgentListItem({
  agentId,
  name,
  description,
  iconUrl,
  iconName,
  color,
  kind,
  onClick,
  flat,
}: {
  agentId: string;
  name: string;
  description?: string | null;
  iconUrl?: string | null;
  iconName?: string | null;
  color?: string | null;
  kind?: string | null;
  onClick?: () => void;
  flat?: boolean;
}) {
  const text = description?.trim();
  const body = (
    <>
      <AgentAvatar
        name={name}
        iconUrl={iconUrl}
        iconName={iconName}
        color={color}
      />
      <div className={styles.probeBody}>
        <div className={styles.probeNameRow}>
          <div className={styles.probeName}>{name}</div>
          <KindTag kind={kind} />
        </div>
        {text ? <div className={styles.probeDesc}>{text}</div> : null}
      </div>
    </>
  );
  if (onClick) {
    return (
      <li>
        <button
          type="button"
          className={flat ? styles.agentRowBtn : styles.connectedAgentBtn}
          onClick={onClick}
          data-agent-id={agentId}
        >
          {body}
        </button>
      </li>
    );
  }
  return <li className={styles.probeItem}>{body}</li>;
}

function AgentListToggle({
  total,
  expanded,
  onToggle,
}: {
  total: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const hidden = total - CARD_AGENT_PREVIEW_LIMIT;
  if (hidden <= 0) return null;
  return (
    <Button
      type="link"
      size="small"
      className={styles.probeMoreBtn}
      onClick={onToggle}
    >
      {expanded
        ? t("advancedSettings.bridge.showLessExperts")
        : t("advancedSettings.bridge.showMoreExperts", { count: hidden })}
    </Button>
  );
}

function ProbeAgentList({ agents }: { agents: BridgeProbeAgent[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (agents.length === 0) {
    return (
      <p className={styles.probeEmpty}>
        {t("advancedSettings.bridge.noAgents")}
      </p>
    );
  }
  const visible =
    expanded || agents.length <= CARD_AGENT_PREVIEW_LIMIT
      ? agents
      : agents.slice(0, CARD_AGENT_PREVIEW_LIMIT);
  return (
    <>
      <ul className={styles.probeList}>
        {visible.map((agent) => (
          <AgentListItem
            key={agent.agent_id}
            agentId={agent.agent_id}
            name={agent.name}
            description={agent.description}
            iconUrl={agent.icon_url}
            iconName={agent.icon_name}
            color={agent.color}
            kind={agent.kind}
          />
        ))}
      </ul>
      <AgentListToggle
        total={agents.length}
        expanded={expanded}
        onToggle={() => setExpanded((open) => !open)}
      />
    </>
  );
}

function RemoteAgentsBlock({
  row,
  agents,
  onOpen,
}: {
  row: BridgeConnection;
  agents: BridgeRemoteAgent[];
  onOpen: (agentId: string) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (agents.length > 0) {
    const visible =
      expanded || agents.length <= CARD_AGENT_PREVIEW_LIMIT
        ? agents
        : agents.slice(0, CARD_AGENT_PREVIEW_LIMIT);
    return (
      <>
        <ul className={styles.agentList}>
          {visible.map((agent) => (
            <AgentListItem
              key={agent.id}
              agentId={agent.id}
              name={String(agent.name || agent.remote_agent_id || agent.id)}
              description={
                typeof agent.description === "string" ? agent.description : null
              }
              iconUrl={
                typeof agent.icon_url === "string" ? agent.icon_url : null
              }
              iconName={
                typeof agent.icon_name === "string" ? agent.icon_name : null
              }
              color={typeof agent.color === "string" ? agent.color : null}
              kind={typeof agent.kind === "string" ? agent.kind : null}
              onClick={() => onOpen(agent.id)}
              flat
            />
          ))}
        </ul>
        <AgentListToggle
          total={agents.length}
          expanded={expanded}
          onToggle={() => setExpanded((open) => !open)}
        />
      </>
    );
  }
  if (row.status === "connected") {
    return (
      <p className={styles.meta}>{t("advancedSettings.bridge.noAgents")}</p>
    );
  }
  return null;
}

interface ConnectionActions {
  busyId: string | null;
  onConnect: (row: BridgeConnection) => Promise<void>;
  onDisconnect: (row: BridgeConnection) => Promise<void>;
  onDelete: (row: BridgeConnection) => Promise<void>;
  onEdit: (row: BridgeConnection) => void;
  onToggleAutoReconnect: (
    row: BridgeConnection,
    enabled: boolean,
  ) => Promise<void>;
  onOpenAgent: (agentId: string) => void;
}

function BridgeDisconnectButton({
  row,
  connected,
  link,
  busy,
  onDisconnect,
  onConnect,
}: {
  row: BridgeConnection;
  connected: boolean;
  link?: boolean;
  busy?: boolean;
  onDisconnect: (row: BridgeConnection) => Promise<void>;
  onConnect: (row: BridgeConnection) => Promise<void>;
}) {
  const { t } = useTranslation();
  const inbound = isInboundConnection(row);
  const buttonType = link ? "link" : "text";
  if (inbound) {
    return (
      <InboundLockedControl>
        <Button
          size="small"
          type={buttonType}
          disabled
          icon={connected ? <Unplug size={14} /> : <Cloudy size={14} />}
        >
          {t(
            connected
              ? "advancedSettings.bridge.disconnect"
              : "advancedSettings.bridge.connect",
          )}
        </Button>
      </InboundLockedControl>
    );
  }
  if (!connected) {
    return (
      <Button
        size="small"
        type={buttonType}
        icon={<Cloudy size={14} />}
        loading={busy}
        disabled={busy}
        onClick={() => void onConnect(row)}
      >
        {t("advancedSettings.bridge.connect")}
      </Button>
    );
  }
  return (
    <Popconfirm
      title={t("advancedSettings.bridge.disconnectTitle")}
      description={t("advancedSettings.bridge.disconnectDesc", {
        name: row.display_name,
      })}
      okText={t("advancedSettings.bridge.disconnect")}
      cancelText={t("common.cancel")}
      okButtonProps={{ danger: true }}
      onConfirm={() => void onDisconnect(row)}
    >
      <Button
        size="small"
        type={buttonType}
        icon={<Unplug size={14} />}
        loading={busy}
        disabled={busy}
      >
        {t("advancedSettings.bridge.disconnect")}
      </Button>
    </Popconfirm>
  );
}

function BridgeDeleteButton({
  row,
  connected,
  link,
  busy,
  onDelete,
}: {
  row: BridgeConnection;
  connected: boolean;
  link?: boolean;
  busy?: boolean;
  onDelete: (row: BridgeConnection) => Promise<void>;
}) {
  const { t } = useTranslation();
  const inbound = isInboundConnection(row);
  const locked = inbound && connected;
  const button = (
    <Button
      size="small"
      type={link ? "link" : "text"}
      danger
      disabled={locked || busy}
      loading={busy}
      icon={<Trash2 size={14} />}
      aria-label={t("advancedSettings.bridge.delete")}
    >
      {link ? t("common.delete") : null}
    </Button>
  );
  const trigger = link ? (
    button
  ) : (
    <Tooltip title={t("advancedSettings.bridge.delete")}>{button}</Tooltip>
  );
  if (locked) {
    return <InboundLockedControl>{button}</InboundLockedControl>;
  }
  return (
    <Popconfirm
      title={t("advancedSettings.bridge.deleteConfirmTitle")}
      description={t(
        inbound
          ? "advancedSettings.bridge.deleteConfirmDescInboundOffline"
          : "advancedSettings.bridge.deleteConfirmDesc",
        { name: row.display_name },
      )}
      okText={t("common.delete")}
      cancelText={t("common.cancel")}
      okButtonProps={{ danger: true }}
      onConfirm={() => void onDelete(row)}
    >
      {trigger}
    </Popconfirm>
  );
}

function AutoReconnectControl({
  row,
  labeled,
  busy,
  onToggle,
}: {
  row: BridgeConnection;
  labeled?: boolean;
  busy?: boolean;
  onToggle: (row: BridgeConnection, enabled: boolean) => Promise<void>;
}) {
  const { t } = useTranslation();
  const inbound = isInboundConnection(row);
  const control = (
    <span className={labeled ? styles.autoReconnectInline : undefined}>
      <Switch
        size="small"
        disabled={inbound || busy}
        loading={busy}
        checked={inbound ? false : row.auto_reconnect !== false}
        onChange={(checked) => void onToggle(row, checked)}
      />
      {labeled ? (
        <span>{t("advancedSettings.bridge.autoReconnect")}</span>
      ) : null}
    </span>
  );
  if (inbound) {
    return <InboundLockedControl>{control}</InboundLockedControl>;
  }
  return (
    <Tooltip title={t("advancedSettings.bridge.autoReconnectHint")}>
      {control}
    </Tooltip>
  );
}

function BridgeConnectionCard({
  row,
  agents,
  actions,
}: {
  row: BridgeConnection;
  agents: BridgeRemoteAgent[];
  actions: ConnectionActions;
}) {
  const { t } = useTranslation();
  const connected = row.status === "connected";
  return (
    <section
      className={styles.backendCard}
      style={{ "--catalog-accent": BRIDGE_ACCENT } as CSSProperties}
    >
      <div className={styles.backendCardHeader}>
        <div className={styles.backendCardTitle}>
          <div className={styles.backendCardIcon}>
            {iconForName(row.icon_name || DEFAULT_BRIDGE_ICON, 18)}
          </div>
          <div className={styles.backendCardName}>
            <span className={styles.backendCardNameText}>
              {row.display_name}
            </span>
            {isInboundConnection(row) ? (
              <Tag style={{ marginInlineEnd: 0 }}>
                {t("advancedSettings.bridge.inboundTag")}
              </Tag>
            ) : null}
          </div>
        </div>
        <div
          className={connected ? styles.statusBadgeOk : styles.statusBadgeWarn}
        >
          {connected ? <CheckCircle size={11} /> : <AlertCircle size={11} />}
          <span>{connectionStatusText(row, t)}</span>
        </div>
      </div>

      {row.notes?.trim() ? (
        <div className={styles.backendCardNote}>{row.notes}</div>
      ) : null}

      <div className={styles.backendCardInfo}>
        {isInboundConnection(row) ? (
          <>
            <InboundPeerFacts row={row} />
          </>
        ) : (
          <>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>
                {t("advancedSettings.bridge.peerUrl")}:
              </span>
              <span className={styles.infoValue} title={row.peer_base_url}>
                {peerHostLabel(row.peer_base_url)}
              </span>
            </div>
            <div className={styles.infoRow}>
              <span className={styles.infoLabel}>
                {t("advancedSettings.bridge.peerAccount")}:
              </span>
              <span className={styles.infoValue}>{row.peer_username}</span>
            </div>
          </>
        )}
        {isInboundConnection(row) ? (
          <p className={styles.explain}>
            {connected
              ? t("advancedSettings.bridge.inboundHint")
              : t("advancedSettings.bridge.inboundOfflineHint")}
          </p>
        ) : null}
        {row.last_error ? (
          <p className={styles.metaError}>{row.last_error}</p>
        ) : null}
      </div>

      <div className={styles.backendCardActions}>
        <div className={styles.backendActionsLeft}>
          {isInboundConnection(row) ? null : (
            <AutoReconnectControl
              row={row}
              labeled
              busy={actions.busyId === row.connection_id}
              onToggle={actions.onToggleAutoReconnect}
            />
          )}
        </div>
        <div className={styles.backendActionsRight}>
          <Tooltip title={t("common.edit")}>
            <Button
              size="small"
              type="text"
              icon={<Pencil size={14} />}
              aria-label={t("common.edit")}
              onClick={() => actions.onEdit(row)}
            />
          </Tooltip>
          <BridgeDisconnectButton
            row={row}
            connected={connected}
            busy={actions.busyId === row.connection_id}
            onDisconnect={actions.onDisconnect}
            onConnect={actions.onConnect}
          />
          <BridgeDeleteButton
            row={row}
            connected={connected}
            busy={actions.busyId === row.connection_id}
            onDelete={actions.onDelete}
          />
        </div>
      </div>

      <RemoteAgentsBlock
        row={row}
        agents={agents}
        onOpen={actions.onOpenAgent}
      />
    </section>
  );
}

export default function BridgeSettingsPanel({
  asPage = false,
}: {
  asPage?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refresh: refreshAgents } = useAgent();
  const { viewMode, setViewMode, showCardView } = useCardTableView("card");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [rows, setRows] = useState<BridgeConnection[]>([]);
  const [agentsByConn, setAgentsByConn] = useState<
    Record<string, BridgeRemoteAgent[]>
  >({});
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<BridgeProbeResult | null>(
    null,
  );
  const [form] = Form.useForm();
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editProbing, setEditProbing] = useState(false);
  const [editProbeResult, setEditProbeResult] =
    useState<BridgeProbeResult | null>(null);
  const [editTarget, setEditTarget] = useState<BridgeConnection | null>(null);
  const [editForm] = Form.useForm();

  const closeCreateDrawer = () => {
    setCreateOpen(false);
    setProbeResult(null);
    form.resetFields();
  };

  const openEditDrawer = useCallback(
    (row: BridgeConnection) => {
      setEditTarget(row);
      setEditProbeResult(null);
      editForm.setFieldsValue({
        display_name: row.display_name,
        notes: row.notes ?? "",
        icon_name: row.icon_name || DEFAULT_BRIDGE_ICON,
        peer_base_url: row.peer_base_url,
        peer_username: row.peer_username,
        password: "",
      });
      setEditOpen(true);
    },
    [editForm],
  );

  const closeEditDrawer = () => {
    setEditOpen(false);
    setEditTarget(null);
    setEditProbeResult(null);
    editForm.resetFields();
  };

  const reload = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = Boolean(opts?.silent);
      if (!silent) setLoading(true);
      try {
        const list = await bridgeApi.list();
        setRows(list);
        const next: Record<string, BridgeRemoteAgent[]> = {};
        await Promise.all(
          list
            .filter((c) => c.status === "connected")
            .map(async (c) => {
              try {
                next[c.connection_id] = await bridgeApi.listAgents(
                  c.connection_id,
                );
              } catch {
                next[c.connection_id] = [];
              }
            }),
        );
        setAgentsByConn(next);
      } catch (err) {
        if (!silent) {
          message.error(
            apiErrorMessage(err, t("advancedSettings.bridge.loadFailed"), t),
          );
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => {
      void reload({ silent: true });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const onSaveEdit = async () => {
    if (!editTarget) return;
    try {
      const inbound = isInboundConnection(editTarget);
      const values = inbound
        ? await editForm.validateFields(["display_name", "notes", "icon_name"])
        : await editForm.validateFields();
      setEditing(true);
      const password = String(values.password || "").trim();
      await bridgeApi.patch(
        editTarget.connection_id,
        inbound
          ? {
              display_name: values.display_name,
              notes: values.notes ?? "",
              icon_name: values.icon_name || DEFAULT_BRIDGE_ICON,
            }
          : {
              display_name: values.display_name,
              notes: values.notes ?? "",
              icon_name: values.icon_name || DEFAULT_BRIDGE_ICON,
              peer_base_url: values.peer_base_url,
              peer_username: values.peer_username,
              ...(password ? { password } : {}),
            },
      );
      message.success(t("advancedSettings.bridge.editSaved"));
      closeEditDrawer();
      await reload({ silent: true });
      await refreshAgents({ silent: true, force: true });
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        apiErrorMessage(err, t("advancedSettings.bridge.editFailed"), t),
      );
    } finally {
      setEditing(false);
    }
  };

  const onEditProbe = async () => {
    if (!editTarget) return;
    try {
      const values = await editForm.validateFields([
        "peer_base_url",
        "peer_username",
      ]);
      const password = String(editForm.getFieldValue("password") || "").trim();
      if (!password && !editTarget.has_password) {
        message.warning(t("advancedSettings.bridge.passwordRequired"));
        return;
      }
      setEditProbing(true);
      const result = await bridgeApi.probeConnection(editTarget.connection_id, {
        peer_base_url: values.peer_base_url,
        peer_username: values.peer_username,
        ...(password ? { password } : {}),
      });
      setEditProbeResult(result);
      message.success(
        t("advancedSettings.bridge.probeOk", { count: result.agent_count }),
      );
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      setEditProbeResult(null);
      message.error(
        apiErrorMessage(err, t("advancedSettings.bridge.probeFailed"), t),
      );
    } finally {
      setEditProbing(false);
    }
  };

  const onCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      await bridgeApi.create({
        peer_base_url: values.peer_base_url,
        peer_username: values.peer_username,
        password: values.password,
        display_name: values.display_name,
        notes: values.notes || undefined,
        icon_name: values.icon_name || DEFAULT_BRIDGE_ICON,
        connect: true,
      });
      message.success(t("advancedSettings.bridge.created"));
      closeCreateDrawer();
      await reload({ silent: true });
      await refreshAgents({ silent: true, force: true });
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        apiErrorMessage(err, t("advancedSettings.bridge.createFailed"), t),
      );
    } finally {
      setCreating(false);
    }
  };

  const onProbe = async () => {
    try {
      const values = await form.validateFields([
        "peer_base_url",
        "peer_username",
        "password",
      ]);
      setProbing(true);
      const result = await bridgeApi.probe({
        peer_base_url: values.peer_base_url,
        peer_username: values.peer_username,
        password: values.password,
      });
      setProbeResult(result);
      message.success(
        t("advancedSettings.bridge.probeOk", { count: result.agent_count }),
      );
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      setProbeResult(null);
      message.error(
        apiErrorMessage(err, t("advancedSettings.bridge.probeFailed"), t),
      );
    } finally {
      setProbing(false);
    }
  };

  const replaceRow = useCallback((updated: BridgeConnection) => {
    setRows((prev) =>
      prev.map((item) =>
        item.connection_id === updated.connection_id ? updated : item,
      ),
    );
  }, []);

  const syncConnectionAgents = useCallback(
    async (updated: BridgeConnection) => {
      if (updated.status !== "connected") {
        setAgentsByConn((prev) => {
          if (!(updated.connection_id in prev)) return prev;
          const next = { ...prev };
          delete next[updated.connection_id];
          return next;
        });
        return;
      }
      try {
        const agents = await bridgeApi.listAgents(updated.connection_id);
        setAgentsByConn((prev) => ({
          ...prev,
          [updated.connection_id]: agents,
        }));
      } catch {
        setAgentsByConn((prev) => ({
          ...prev,
          [updated.connection_id]: [],
        }));
      }
    },
    [],
  );

  const refreshRow = useCallback(
    async (connectionId: string) => {
      try {
        const updated = await bridgeApi.get(connectionId);
        replaceRow(updated);
        await syncConnectionAgents(updated);
      } catch {
        // The 5s poll reconciles if this single-row read fails.
      }
    },
    [replaceRow, syncConnectionAgents],
  );

  const runOnRow = useCallback(
    async (connectionId: string, task: () => Promise<void>) => {
      if (busyRef.current) return;
      busyRef.current = connectionId;
      setBusyId(connectionId);
      try {
        await task();
      } finally {
        busyRef.current = null;
        setBusyId(null);
      }
    },
    [],
  );

  const actions = useMemo<ConnectionActions>(
    () => ({
      busyId,
      onConnect: (row) =>
        runOnRow(row.connection_id, async () => {
          try {
            const updated = await bridgeApi.connect(row.connection_id);
            replaceRow(updated);
            await syncConnectionAgents(updated);
            await refreshAgents({ silent: true, force: true });
          } catch (err) {
            message.error(
              apiErrorMessage(
                err,
                t("advancedSettings.bridge.createFailed"),
                t,
              ),
            );
            await refreshRow(row.connection_id);
          }
        }),
      onDisconnect: (row) =>
        runOnRow(row.connection_id, async () => {
          try {
            const updated = await bridgeApi.disconnect(row.connection_id);
            replaceRow(updated);
            await syncConnectionAgents(updated);
            await refreshAgents({ silent: true, force: true });
          } catch (err) {
            message.error(
              apiErrorMessage(err, t("advancedSettings.bridge.loadFailed"), t),
            );
            await refreshRow(row.connection_id);
          }
        }),
      onDelete: (row) =>
        runOnRow(row.connection_id, async () => {
          try {
            await bridgeApi.remove(row.connection_id);
            setRows((prev) =>
              prev.filter((item) => item.connection_id !== row.connection_id),
            );
            setAgentsByConn((prev) => {
              if (!(row.connection_id in prev)) return prev;
              const next = { ...prev };
              delete next[row.connection_id];
              return next;
            });
            message.success(t("advancedSettings.bridge.deleted"));
            await refreshAgents({ silent: true, force: true });
          } catch (err) {
            message.error(
              apiErrorMessage(
                err,
                t("advancedSettings.bridge.deleteFailed"),
                t,
              ),
            );
          }
        }),
      onEdit: (row) => {
        openEditDrawer(row);
      },
      onToggleAutoReconnect: (row, enabled) =>
        runOnRow(row.connection_id, async () => {
          try {
            const updated = await bridgeApi.patch(row.connection_id, {
              auto_reconnect: enabled,
            });
            replaceRow(updated);
          } catch (err) {
            message.error(
              apiErrorMessage(err, t("advancedSettings.bridge.loadFailed"), t),
            );
          }
        }),
      onOpenAgent: (agentId) => {
        navigate(`/chat/${encodeURIComponent(agentId)}`);
      },
    }),
    [
      busyId,
      navigate,
      openEditDrawer,
      refreshAgents,
      refreshRow,
      replaceRow,
      runOnRow,
      syncConnectionAgents,
      t,
    ],
  );

  const columns = useMemo<ColumnsType<BridgeConnection>>(
    () => [
      {
        title: t("advancedSettings.bridge.displayName"),
        dataIndex: "display_name",
        key: "display_name",
        ellipsis: true,
        render: (name: string, row) => (
          <div className={styles.tableNameCell}>
            <span className={styles.tableNameIcon}>
              {iconForName(row.icon_name || DEFAULT_BRIDGE_ICON, 14)}
            </span>
            <div className={styles.tableNameText}>
              <strong>{name}</strong>
              {isInboundConnection(row) ? (
                <Tag style={{ marginInlineStart: 6, marginInlineEnd: 0 }}>
                  {t("advancedSettings.bridge.inboundTag")}
                </Tag>
              ) : null}
              {row.notes ? (
                <span className={styles.tableNameNote}>{row.notes}</span>
              ) : null}
            </div>
          </div>
        ),
      },
      {
        title: t("advancedSettings.bridge.peerUrl"),
        dataIndex: "peer_base_url",
        key: "peer_base_url",
        ellipsis: true,
        render: (url: string, row) =>
          isInboundConnection(row) ? inboundPeerAddress(row) || "—" : url,
      },
      {
        title: t("advancedSettings.bridge.peerAccount"),
        dataIndex: "peer_username",
        key: "peer_username",
        width: 120,
        ellipsis: true,
      },
      {
        title: t("advancedSettings.bridge.colStatus"),
        dataIndex: "status",
        key: "status",
        width: 110,
        render: (_status: string, row) => (
          <Tag color={statusColor(row.status)}>
            {connectionStatusText(row, t)}
          </Tag>
        ),
      },
      {
        title: t("advancedSettings.bridge.autoReconnect"),
        dataIndex: "auto_reconnect",
        key: "auto_reconnect",
        width: 110,
        render: (_value: boolean | undefined, row) =>
          isInboundConnection(row) ? (
            "—"
          ) : (
            <AutoReconnectControl
              row={row}
              busy={actions.busyId === row.connection_id}
              onToggle={actions.onToggleAutoReconnect}
            />
          ),
      },
      {
        title: t("advancedSettings.bridge.colAgents"),
        key: "agents",
        width: 90,
        render: (_: unknown, row) => {
          const n = (agentsByConn[row.connection_id] || []).length;
          return row.status === "connected" ? n : "—";
        },
      },
      {
        title: t("common.actions"),
        key: "actions",
        width: 240,
        render: (_: unknown, row) => (
          <div className={styles.tableActions}>
            <Button
              size="small"
              type="link"
              icon={<Pencil size={14} />}
              onClick={() => actions.onEdit(row)}
            >
              {t("common.edit")}
            </Button>
            <BridgeDisconnectButton
              row={row}
              connected={row.status === "connected"}
              link
              busy={actions.busyId === row.connection_id}
              onDisconnect={actions.onDisconnect}
              onConnect={actions.onConnect}
            />
            <BridgeDeleteButton
              row={row}
              connected={row.status === "connected"}
              link
              busy={actions.busyId === row.connection_id}
              onDelete={actions.onDelete}
            />
          </div>
        ),
      },
    ],
    [actions, agentsByConn, t],
  );

  const viewToggle = (
    <Segmented
      size="small"
      value={viewMode}
      onChange={(v) => setViewMode(v as "table" | "card")}
      options={[
        {
          value: "card",
          label: (
            <span className={styles.viewModeLabel}>
              <LayoutGrid size={14} />
              {t("advancedSettings.bridge.viewCard")}
            </span>
          ),
        },
        {
          value: "table",
          label: (
            <span className={styles.viewModeLabel}>
              <List size={14} />
              {t("advancedSettings.bridge.viewTable")}
            </span>
          ),
        },
      ]}
    />
  );

  const atConnectionLimit = rows.length >= MAX_BRIDGE_CONNECTIONS;
  const headerActions = (
    <>
      {rows.length > 0 ? viewToggle : null}
      <Button icon={<RefreshCw size={14} />} onClick={() => void reload()}>
        {t("common.refresh")}
      </Button>
      <Tooltip
        title={
          atConnectionLimit
            ? t("advancedSettings.bridge.addDisabled", {
                limit: MAX_BRIDGE_CONNECTIONS,
              })
            : undefined
        }
      >
        <Button
          type="primary"
          icon={<Plus size={14} />}
          disabled={atConnectionLimit}
          onClick={() => setCreateOpen(true)}
        >
          {t("advancedSettings.bridge.add")}
        </Button>
      </Tooltip>
    </>
  );

  return (
    <>
      {asPage ? (
        <div className={styles.pageToolbar}>
          <span className={styles.gridCount}>
            {!loading && rows.length > 0
              ? t("advancedSettings.bridge.totalConnections", {
                  count: rows.length,
                })
              : null}
          </span>
          <div className={styles.pageToolbarActions}>{headerActions}</div>
        </div>
      ) : (
        <TabPanelHeader
          icon={<Share2 size={18} strokeWidth={1.8} />}
          title={t("advancedSettings.bridge.title")}
          description={t("advancedSettings.bridge.description")}
          actions={headerActions}
        />
      )}

      {loading ? (
        <div className={styles.loading}>
          <Spin />
        </div>
      ) : rows.length === 0 ? (
        <StreamSetupGuide
          className={styles.emptyGuide}
          wide
          plain
          icon={<OctopEmptyMascot />}
          title={t("advancedSettings.bridge.emptyTitle")}
          description={t("advancedSettings.bridge.emptyDesc")}
          steps={[
            {
              label: t("advancedSettings.bridge.emptyGuideStepWhat"),
              detail: t("advancedSettings.bridge.emptyGuideStepWhatDetail"),
            },
            {
              label: t("advancedSettings.bridge.emptyGuideStepHow"),
              detail: t("advancedSettings.bridge.emptyGuideStepHowDetail"),
            },
            {
              label: t("advancedSettings.bridge.emptyGuideStepChat"),
              detail: t("advancedSettings.bridge.emptyGuideStepChatDetail"),
            },
          ]}
          primaryAction={{
            label: t("advancedSettings.bridge.add"),
            onClick: () => setCreateOpen(true),
            icon: <Plus size={14} />,
            disabled: atConnectionLimit,
            title: atConnectionLimit
              ? t("advancedSettings.bridge.addDisabled", {
                  limit: MAX_BRIDGE_CONNECTIONS,
                })
              : undefined,
          }}
        />
      ) : (
        <>
          {!asPage ? (
            <div className={styles.gridToolbar}>
              <span className={styles.gridCount}>
                {t("advancedSettings.bridge.totalConnections", {
                  count: rows.length,
                })}
              </span>
            </div>
          ) : null}
          {showCardView ? (
            <div className={styles.cardGrid}>
              {rows.map((row) => (
                <BridgeConnectionCard
                  key={row.connection_id}
                  row={row}
                  agents={agentsByConn[row.connection_id] || []}
                  actions={actions}
                />
              ))}
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <Table<BridgeConnection>
                rowKey="connection_id"
                size="middle"
                pagination={false}
                columns={columns}
                dataSource={rows}
                scroll={{ x: 900 }}
                expandable={{
                  expandedRowRender: (row) => (
                    <RemoteAgentsBlock
                      row={row}
                      agents={agentsByConn[row.connection_id] || []}
                      onOpen={actions.onOpenAgent}
                    />
                  ),
                  rowExpandable: (row) =>
                    row.status === "connected" ||
                    (agentsByConn[row.connection_id] || []).length > 0,
                }}
              />
            </div>
          )}
        </>
      )}

      <Drawer
        title={t("advancedSettings.bridge.add")}
        open={createOpen}
        onClose={closeCreateDrawer}
        width={460}
        placement="right"
        destroyOnHidden
        className={styles.createDrawer}
        footer={
          <div className={styles.drawerFooter}>
            <Button onClick={closeCreateDrawer}>{t("common.cancel")}</Button>
            <Button
              icon={<Activity size={14} />}
              loading={probing}
              onClick={() => void onProbe()}
            >
              {t("advancedSettings.bridge.probe")}
            </Button>
            <Button
              type="primary"
              loading={creating}
              disabled={atConnectionLimit}
              icon={<Cloudy size={14} />}
              onClick={() => void onCreate()}
            >
              {t("advancedSettings.bridge.addConfirm")}
            </Button>
          </div>
        }
      >
        <p className={styles.drawerHint}>
          {t("advancedSettings.bridge.drawerHint")}
        </p>
        <p className={styles.drawerHint}>
          {t("advancedSettings.bridge.directionHint")}
        </p>
        <p className={styles.drawerHint}>
          {t("advancedSettings.bridge.limitHint", {
            limit: MAX_BRIDGE_CONNECTIONS,
          })}
        </p>
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          className={styles.createForm}
          initialValues={{ icon_name: DEFAULT_BRIDGE_ICON }}
        >
          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("advancedSettings.bridge.sectionIdentity")}
            </div>
            <Form.Item
              name="display_name"
              label={t("advancedSettings.bridge.displayName")}
              extra={t("advancedSettings.bridge.displayNameHint")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("advancedSettings.bridge.displayNameRequired"),
                },
                { max: 64 },
              ]}
            >
              <Input
                prefix={<TagIcon {...FIELD_ICON} />}
                placeholder={t(
                  "advancedSettings.bridge.displayNamePlaceholder",
                )}
                maxLength={64}
                autoFocus
              />
            </Form.Item>
            <Form.Item
              name="icon_name"
              label={t("advancedSettings.bridge.icon")}
              extra={t("advancedSettings.bridge.iconHint")}
              initialValue={DEFAULT_BRIDGE_ICON}
            >
              <BridgeIconPicker />
            </Form.Item>
            <Form.Item
              name="notes"
              label={t("advancedSettings.bridge.notes")}
              rules={[{ max: 500 }]}
            >
              <Input.TextArea
                placeholder={t("advancedSettings.bridge.notesPlaceholder")}
                autoSize={{ minRows: 2, maxRows: 4 }}
                maxLength={500}
              />
            </Form.Item>
          </div>

          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("advancedSettings.bridge.sectionRemote")}
            </div>
            <Form.Item
              name="peer_base_url"
              label={t("advancedSettings.bridge.peerUrl")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("advancedSettings.bridge.peerUrlRequired"),
                },
              ]}
            >
              <Input
                prefix={<Globe {...FIELD_ICON} />}
                placeholder={t("advancedSettings.bridge.peerUrlPlaceholder")}
                autoComplete="url"
              />
            </Form.Item>
            <Form.Item
              name="peer_username"
              label={t("advancedSettings.bridge.peerAccount")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("advancedSettings.bridge.usernameRequired"),
                },
              ]}
            >
              <Input
                prefix={<User {...FIELD_ICON} />}
                placeholder={t("advancedSettings.bridge.peerAccount")}
                autoComplete="username"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label={t("advancedSettings.bridge.password")}
              rules={[
                {
                  required: true,
                  message: t("advancedSettings.bridge.passwordRequired"),
                },
              ]}
            >
              <Input.Password
                prefix={<Lock {...FIELD_ICON} />}
                placeholder={t("advancedSettings.bridge.password")}
                autoComplete="current-password"
              />
            </Form.Item>
          </div>
        </Form>

        {probeResult ? (
          <div className={styles.probePanel}>
            <div className={styles.probePanelHead}>
              <Activity size={14} />
              {t("advancedSettings.bridge.probeResultTitle", {
                name: probeResult.peer_display_name,
                count: probeResult.agent_count,
              })}
            </div>
            <ProbeAgentList agents={probeResult.agents} />
          </div>
        ) : null}
      </Drawer>

      <Drawer
        title={t("advancedSettings.bridge.editTitle")}
        open={editOpen}
        onClose={closeEditDrawer}
        width={420}
        destroyOnClose
        footer={
          <div className={styles.drawerFooter}>
            <Button onClick={closeEditDrawer}>{t("common.cancel")}</Button>
            {editTarget && !isInboundConnection(editTarget) ? (
              <Button
                loading={editProbing}
                onClick={() => void onEditProbe()}
                icon={<Activity size={14} />}
              >
                {t("advancedSettings.bridge.probe")}
              </Button>
            ) : null}
            <Button
              type="primary"
              loading={editing}
              icon={<Cloudy size={14} />}
              onClick={() => void onSaveEdit()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <p className={styles.drawerHint}>
          {t(
            editTarget && isInboundConnection(editTarget)
              ? "advancedSettings.bridge.editHintInbound"
              : "advancedSettings.bridge.editHint",
          )}
        </p>
        <Form
          form={editForm}
          layout="vertical"
          requiredMark={false}
          className={styles.createForm}
        >
          <div className={styles.createSection}>
            <div className={styles.createSectionTitle}>
              {t("advancedSettings.bridge.sectionIdentity")}
            </div>
            <Form.Item
              name="display_name"
              label={t("advancedSettings.bridge.displayName")}
              extra={t("advancedSettings.bridge.displayNameHint")}
              rules={[
                {
                  required: true,
                  whitespace: true,
                  message: t("advancedSettings.bridge.displayNameRequired"),
                },
                { max: 64 },
              ]}
            >
              <Input
                prefix={<TagIcon {...FIELD_ICON} />}
                placeholder={t(
                  "advancedSettings.bridge.displayNamePlaceholder",
                )}
                maxLength={64}
                autoFocus
              />
            </Form.Item>
            <Form.Item
              name="icon_name"
              label={t("advancedSettings.bridge.icon")}
              extra={t("advancedSettings.bridge.iconHint")}
              initialValue={DEFAULT_BRIDGE_ICON}
            >
              <BridgeIconPicker />
            </Form.Item>
            <Form.Item
              name="notes"
              label={t("advancedSettings.bridge.notes")}
              rules={[{ max: 500 }]}
            >
              <Input.TextArea
                placeholder={t("advancedSettings.bridge.notesPlaceholder")}
                autoSize={{ minRows: 2, maxRows: 4 }}
                maxLength={500}
              />
            </Form.Item>
          </div>

          {editTarget && isInboundConnection(editTarget) ? (
            <div className={styles.createSection}>
              <div className={styles.createSectionTitle}>
                {t("advancedSettings.bridge.sectionRemote")}
              </div>
              <InboundPeerFacts row={editTarget} />
            </div>
          ) : null}

          {editTarget && !isInboundConnection(editTarget) ? (
            <div className={styles.createSection}>
              <div className={styles.createSectionTitle}>
                {t("advancedSettings.bridge.sectionRemote")}
              </div>
              <Form.Item
                name="peer_base_url"
                label={t("advancedSettings.bridge.peerUrl")}
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    message: t("advancedSettings.bridge.peerUrlRequired"),
                  },
                ]}
              >
                <Input
                  prefix={<Globe {...FIELD_ICON} />}
                  placeholder={t("advancedSettings.bridge.peerUrlPlaceholder")}
                  autoComplete="url"
                />
              </Form.Item>
              <Form.Item
                name="peer_username"
                label={t("advancedSettings.bridge.peerAccount")}
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    message: t("advancedSettings.bridge.usernameRequired"),
                  },
                ]}
              >
                <Input
                  prefix={<User {...FIELD_ICON} />}
                  placeholder={t("advancedSettings.bridge.peerAccount")}
                  autoComplete="username"
                />
              </Form.Item>
              <Form.Item
                name="password"
                label={t("advancedSettings.bridge.password")}
                extra={t("advancedSettings.bridge.passwordKeepHint")}
                rules={[{ max: 256 }]}
              >
                <Input.Password
                  prefix={<Lock {...FIELD_ICON} />}
                  placeholder={t(
                    "advancedSettings.bridge.passwordKeepPlaceholder",
                  )}
                  autoComplete="new-password"
                />
              </Form.Item>
            </div>
          ) : null}
        </Form>

        {editProbeResult ? (
          <div className={styles.probePanel}>
            <div className={styles.probePanelHead}>
              <Activity size={14} />
              {t("advancedSettings.bridge.probeResultTitle", {
                name: editProbeResult.peer_display_name,
                count: editProbeResult.agent_count,
              })}
            </div>
            <ProbeAgentList agents={editProbeResult.agents} />
          </div>
        ) : null}
      </Drawer>
    </>
  );
}
