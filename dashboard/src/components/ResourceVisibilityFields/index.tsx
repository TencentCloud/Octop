import { useEffect, useMemo, useState } from "react";
import { Button, Form, Radio, Select, Tag } from "antd";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  userGroupsApi,
  type ResourceVisibilityMode,
  type UserGroup,
} from "../../api/modules/userGroups";
import { ResourceAvatar, ROLE_AVATAR_PRESETS } from "../AvatarPicker";
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

function useGroups() {
  const [groups, setGroups] = useState<UserGroup[]>([]);

  useEffect(() => {
    let cancelled = false;
    userGroupsApi
      .list()
      .then((rows) => {
        if (!cancelled) setGroups(rows);
      })
      .catch(() => {
        if (!cancelled) setGroups([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return groups;
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
  const groups = useGroups();
  const byId = useMemo(
    () => new Map(groups.map((group) => [group.user_group_id, group])),
    [groups],
  );
  const disabledLabel = t("adminUsers.statusDisabled");

  const radioOptions = [
    ...(allowOwner
      ? [{ value: "owner" as const, label: t("resourceVisibility.owner") }]
      : []),
    { value: "all" as const, label: t("resourceVisibility.all") },
    { value: "groups" as const, label: t("resourceVisibility.groups") },
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
  return (
    <Form.Item
      label={label ?? t("resourceVisibility.label")}
      extra={extra}
      className={className}
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
  const [open, setOpen] = useState(defaultOpen || visibility === "groups");
  const restricted = visibility === "groups";

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

export default ResourceVisibilityFields;
