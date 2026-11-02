import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button, Form, Radio, Select, Tag } from "antd";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  userGroupsApi,
  type ResourceVisibilityMode,
  type UserGroup,
} from "../../api/modules/userGroups";
import { ResourceAvatar, ROLE_AVATAR_PRESETS } from "../AvatarPicker";
import {
  isVisibilityControlVisible,
  needsGroupCatalog,
  showGroupVisibilityOption,
  type AudienceSnapshot,
} from "./visibilityChrome";
import styles from "./ResourceVisibilityFields.module.less";

export type { ResourceVisibilityMode };

export type ResourceVisibilityValue = {
  visibility: ResourceVisibilityMode;
  groupIds: string[];
};

type FieldsProps = {
  /** User-owned resources can stay private (`owner`). Admin resources omit it. */
  allowOwner: boolean;
  visibility: ResourceVisibilityMode;
  groupIds: string[];
  onChange: (next: ResourceVisibilityValue) => void;
  disabled?: boolean;
  className?: string;
};

type AudienceState = AudienceSnapshot & {
  groups: UserGroup[];
  loadedAt: number;
};

/** Collapse the gate and the fields mounting back-to-back into one request. */
const FRESH_MS = 500;

let audienceState: AudienceState = {
  status: "loading",
  userCount: null,
  groupCount: null,
  groupsLoaded: false,
  groupCountFromList: 0,
  groups: [],
  loadedAt: 0,
};
let audienceInflight: Promise<void> | null = null;
const audienceListeners = new Set<() => void>();

function publishAudience(next: AudienceState) {
  audienceState = next;
  audienceListeners.forEach((listener) => listener());
}

function loadAudience(): Promise<void> {
  if (
    audienceState.status === "ready" &&
    Date.now() - audienceState.loadedAt < FRESH_MS
  ) {
    return Promise.resolve();
  }
  if (audienceInflight) return audienceInflight;
  audienceInflight = (async () => {
    const counts = await userGroupsApi.audience().then(
      (row) => ({ ok: true as const, row }),
      () => ({ ok: false as const, row: null }),
    );
    const userCount = counts.ok ? counts.row.user_count : null;
    const groupCount = counts.ok ? counts.row.group_count : null;
    let groups: UserGroup[] = [];
    let groupsLoaded = false;
    if (needsGroupCatalog({ userCount, groupCount })) {
      try {
        groups = await userGroupsApi.list();
        groupsLoaded = true;
      } catch {
        groups = [];
      }
    } else {
      groupsLoaded = true;
    }
    publishAudience({
      status: "ready",
      userCount,
      groupCount,
      groupsLoaded,
      groupCountFromList: groups.length,
      groups,
      loadedAt: Date.now(),
    });
  })().finally(() => {
    audienceInflight = null;
  });
  return audienceInflight;
}

function useResourceAudience(): AudienceState {
  const [snap, setSnap] = useState(audienceState);

  useEffect(() => {
    const sync = () => setSnap(audienceState);
    audienceListeners.add(sync);
    void loadAudience().then(sync);
    return () => {
      audienceListeners.delete(sync);
    };
  }, []);

  return snap;
}

function GroupLabel({
  group,
  disabledLabel,
}: {
  group: UserGroup;
  disabledLabel: string;
}) {
  const name =
    group.enabled === false ? `${group.name} (${disabledLabel})` : group.name;
  return (
    <span className={styles.groupOption}>
      <ResourceAvatar
        url={group.avatar_url}
        icon={group.avatar_icon}
        presets={ROLE_AVATAR_PRESETS}
        className={styles.groupAvatar}
      />
      <span className={styles.groupName}>{name}</span>
    </span>
  );
}

/** Radio + optional multi-select for who may use a resource. */
export function ResourceVisibilityFields({
  allowOwner,
  visibility,
  groupIds,
  onChange,
  disabled = false,
  className,
}: FieldsProps) {
  const { t } = useTranslation();
  const audience = useResourceAudience();
  const groups = audience.groups;
  const byId = useMemo(
    () => new Map(groups.map((group) => [group.user_group_id, group])),
    [groups],
  );
  const disabledLabel = t("adminUsers.statusDisabled");
  const showGroups = showGroupVisibilityOption(audience, visibility);

  if (!isVisibilityControlVisible(audience, { allowOwner, visibility })) {
    return null;
  }

  const radioOptions = [
    ...(allowOwner
      ? [{ value: "owner" as const, label: t("resourceVisibility.owner") }]
      : []),
    { value: "all" as const, label: t("resourceVisibility.all") },
    ...(showGroups
      ? [{ value: "groups" as const, label: t("resourceVisibility.groups") }]
      : []),
  ];

  const options = groups.map((group) => ({
    value: group.user_group_id,
    label: <GroupLabel group={group} disabledLabel={disabledLabel} />,
  }));

  return (
    <div className={[styles.fields, className].filter(Boolean).join(" ")}>
      <Radio.Group
        className={styles.radio}
        disabled={disabled}
        value={visibility}
        options={radioOptions}
        onChange={(event) =>
          onChange({
            visibility: event.target.value as ResourceVisibilityMode,
            groupIds: event.target.value === "groups" ? groupIds : [],
          })
        }
      />
      {visibility === "groups" ? (
        <Select
          className={styles.groups}
          mode="multiple"
          disabled={disabled}
          value={groupIds}
          placeholder={t("resourceVisibility.groupPlaceholder")}
          options={options}
          optionLabelProp="label"
          optionFilterProp="value"
          filterOption={(input, option) => {
            const group = byId.get(String(option?.value ?? ""));
            if (!group) return false;
            const q = input.trim().toLowerCase();
            return (
              group.name.toLowerCase().includes(q) ||
              group.user_group_id.toLowerCase().includes(q)
            );
          }}
          tagRender={(props) => {
            const group = byId.get(props.value);
            return (
              <Tag
                className={styles.groupTag}
                closable={props.closable}
                onClose={props.onClose}
                onMouseDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
              >
                {group ? (
                  <GroupLabel group={group} disabledLabel={disabledLabel} />
                ) : (
                  props.label
                )}
              </Tag>
            );
          }}
          onChange={(ids) => onChange({ visibility, groupIds: ids })}
        />
      ) : null}
    </div>
  );
}

type FormItemProps = {
  allowOwner: boolean;
  visibility: ResourceVisibilityMode;
  groupIds: string[];
  onChange: (next: ResourceVisibilityValue) => void;
  disabled?: boolean;
  /** Override default ``resourceVisibility.label``. */
  label?: string;
  /** Hint under the control (e.g. skill package / connector copy). */
  extra?: string;
  className?: string;
};

/** Drawer-friendly Form.Item wrapping ``ResourceVisibilityFields``. */
export function ResourceVisibilityFormItem({
  allowOwner,
  visibility,
  groupIds,
  onChange,
  disabled,
  label,
  extra,
  className,
}: FormItemProps) {
  const { t } = useTranslation();
  const audience = useResourceAudience();
  if (!isVisibilityControlVisible(audience, { allowOwner, visibility })) {
    return null;
  }
  return (
    <Form.Item
      label={label ?? t("resourceVisibility.label")}
      extra={extra}
      className={[styles.formItem, className].filter(Boolean).join(" ")}
      required={false}
    >
      <ResourceVisibilityFields
        allowOwner={allowOwner}
        visibility={visibility}
        groupIds={groupIds}
        onChange={onChange}
        disabled={disabled}
      />
    </Form.Item>
  );
}

type CollapseProps = {
  allowOwner?: boolean;
  visibility: ResourceVisibilityMode;
  groupIds: string[];
  onChange: (next: ResourceVisibilityValue) => void;
  disabled?: boolean;
  /** Toggle label when collapsed (default: group access title). */
  title?: string;
  /** Toggle label when open. */
  hideTitle?: string;
  hint?: string;
  defaultOpen?: boolean;
  className?: string;
};

/**
 * Admin-style collapsible block (same interaction as model 「兼容性」).
 * Use inside provider/model forms for 「分组使用」.
 */
export function ResourceVisibilityCollapse({
  allowOwner = false,
  visibility,
  groupIds,
  onChange,
  disabled,
  title,
  hideTitle,
  hint,
  defaultOpen = false,
  className,
}: CollapseProps) {
  const { t } = useTranslation();
  const audience = useResourceAudience();
  const [open, setOpen] = useState(defaultOpen || visibility === "groups");
  const restricted = visibility === "groups";

  if (!isVisibilityControlVisible(audience, { allowOwner, visibility })) {
    return null;
  }
  return (
    <div className={[styles.collapse, className].filter(Boolean).join(" ")}>
      <div className={styles.collapseToggle}>
        <Button
          type="link"
          size="small"
          style={{ padding: 0 }}
          icon={open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          onClick={() => setOpen((current) => !current)}
        >
          {open
            ? hideTitle ?? t("resourceVisibility.hideGroupAccess")
            : title ?? t("resourceVisibility.groupAccess")}
          {!open && restricted ? ` · ${t("resourceVisibility.groups")}` : null}
        </Button>
      </div>
      {open ? (
        <div className={styles.collapseBody}>
          {hint ? <p className={styles.collapseHint}>{hint}</p> : null}
          <ResourceVisibilityFields
            allowOwner={allowOwner}
            visibility={visibility}
            groupIds={groupIds}
            onChange={onChange}
            disabled={disabled}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Hides the surrounding label when the picker itself has nothing to choose. */
export function ResourceVisibilityGate({
  allowOwner,
  visibility,
  children,
}: {
  allowOwner: boolean;
  visibility: ResourceVisibilityMode;
  children: ReactNode;
}) {
  const audience = useResourceAudience();
  if (!isVisibilityControlVisible(audience, { allowOwner, visibility })) {
    return null;
  }
  return children;
}

export default ResourceVisibilityFields;
