import { useEffect, useState } from "react";
import { Radio, Select } from "antd";
import { useTranslation } from "react-i18next";
import {
  userGroupsApi,
  type ResourceVisibilityMode,
  type UserGroup,
} from "../api/modules/userGroups";

export function ResourceVisibilityFields({
  allowOwner,
  visibility,
  groupIds,
  onChange,
}: {
  allowOwner: boolean;
  visibility: ResourceVisibilityMode;
  groupIds: string[];
  onChange: (next: {
    visibility: ResourceVisibilityMode;
    groupIds: string[];
  }) => void;
}) {
  const { t } = useTranslation();
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

  const options = [
    ...(allowOwner
      ? [{ value: "owner" as const, label: t("resourceVisibility.owner") }]
      : []),
    { value: "all" as const, label: t("resourceVisibility.all") },
    { value: "groups" as const, label: t("resourceVisibility.groups") },
  ];

  return (
    <div>
      <Radio.Group
        value={visibility}
        options={options}
        onChange={(event) =>
          onChange({
            visibility: event.target.value as ResourceVisibilityMode,
            groupIds: event.target.value === "groups" ? groupIds : [],
          })
        }
      />
      {visibility === "groups" ? (
        <Select
          mode="multiple"
          style={{ width: "100%", marginTop: 8 }}
          value={groupIds}
          placeholder={t("resourceVisibility.groupPlaceholder")}
          options={groups.map((group) => ({
            value: group.user_group_id,
            label:
              group.enabled === false
                ? `${group.name} (${t("adminUsers.statusDisabled")})`
                : group.name,
          }))}
          onChange={(ids) => onChange({ visibility, groupIds: ids })}
        />
      ) : null}
    </div>
  );
}
