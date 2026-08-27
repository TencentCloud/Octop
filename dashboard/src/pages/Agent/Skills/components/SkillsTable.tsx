import { Popconfirm, Switch, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Eye, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillSpec } from "../useSkills";
import { useSkillDisplayName } from "../skillDisplayNames";
import styles from "../index.module.less";

interface SkillsTableProps {
  skills: SkillSpec[];
  kind: "custom" | "builtin";
  onView: (skill: SkillSpec) => void;
  onToggleEnabled: (skill: SkillSpec) => void;
  onDelete?: (skill: SkillSpec) => void;
}

export default function SkillsTable({
  skills,
  kind,
  onView,
  onToggleEnabled,
  onDelete,
}: SkillsTableProps) {
  const { t } = useTranslation();
  const skillDisplayName = useSkillDisplayName();

  const columns: ColumnsType<SkillSpec> = [
    {
      title: t("skills.nameLabel"),
      dataIndex: "name",
      width: "18%",
      ellipsis: true,
      render: (_name: string, row) => skillDisplayName(row),
    },
    {
      title: t("skills.skillDescription"),
      dataIndex: "description",
      ellipsis: true,
      render: (desc: string) => desc || "—",
    },
    {
      title: t("skills.source"),
      dataIndex: "kind",
      width: "10%",
      align: "center",
      render: (k: SkillSpec["kind"]) => (
        <Tag
          className={styles.kindTag}
          color={k === "builtin" ? "blue" : "default"}
        >
          {k === "builtin"
            ? t("skills.kindBuiltin")
            : t("skills.kindWorkspace")}
        </Tag>
      ),
    },
    {
      title: t("skills.table.enabled", "启用"),
      dataIndex: "enabled",
      width: "8%",
      align: "center",
      render: (enabled: boolean, row) => (
        <Switch
          size="small"
          checked={enabled}
          onClick={(_, e) => e.stopPropagation()}
          onChange={() => onToggleEnabled(row)}
        />
      ),
    },
    {
      title: t("skills.table.actions", "操作"),
      key: "actions",
      width: kind === "custom" ? 88 : 56,
      align: "center",
      render: (_v, row) => (
        <div className={styles.tableActions}>
          <Tooltip title={t("common.view")} mouseEnterDelay={0.5}>
            <button
              type="button"
              className={styles.tableActionBtn}
              aria-label={t("common.view")}
              onClick={(e) => {
                e.stopPropagation();
                onView(row);
              }}
            >
              <Eye size={13} />
            </button>
          </Tooltip>
          {kind === "custom" && onDelete ? (
            <Popconfirm
              title={t("skills.deleteConfirmContent", { slug: row.slug })}
              okText={t("common.delete")}
              cancelText={t("common.cancel")}
              okButtonProps={{ danger: true }}
              onConfirm={() => onDelete(row)}
            >
              <button
                type="button"
                className={`${styles.tableActionBtn} ${styles.tableActionDanger}`}
                aria-label={t("common.delete")}
                onClick={(e) => e.stopPropagation()}
              >
                <Trash2 size={13} />
              </button>
            </Popconfirm>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Table<SkillSpec>
      className={styles.skillsTable}
      rowKey={(row) => `${row.kind}-${row.slug}`}
      columns={columns}
      dataSource={skills}
      pagination={false}
      size="middle"
      scroll={{ x: 720 }}
      onRow={(row) => ({
        onClick: () => onView(row),
        style: { cursor: "pointer" },
      })}
    />
  );
}
