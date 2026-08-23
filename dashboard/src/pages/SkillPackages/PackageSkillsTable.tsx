import { Popconfirm } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillPackageSkill } from "../../api/types/skillPackage";
import { ResizableTable } from "@/components/ResizableTable";
import skillStyles from "../Agent/Skills/index.module.less";

interface PackageSkillsTableProps {
  skills: SkillPackageSkill[];
  canMutate: boolean;
  onView: (skill: SkillPackageSkill) => void;
  onDelete?: (skill: SkillPackageSkill) => void;
}

export default function PackageSkillsTable({
  skills,
  canMutate,
  onView,
  onDelete,
}: PackageSkillsTableProps) {
  const { t } = useTranslation();

  const columns: ColumnsType<SkillPackageSkill> = [
    {
      title: t("skills.nameLabel"),
      dataIndex: "name",
      width: "20%",
      ellipsis: true,
    },
    {
      title: t("skillPackages.skillSlug"),
      dataIndex: "slug",
      width: "16%",
      ellipsis: true,
    },
    {
      title: t("skills.skillDescription"),
      dataIndex: "description",
      ellipsis: true,
      render: (desc: string) => desc || "—",
    },
    {
      title: t("skillPackages.tableActions"),
      key: "actions",
      width: canMutate ? "14%" : "10%",
      align: "center",
      render: (_v, row) => (
        <div className={skillStyles.tableActions}>
          <button
            type="button"
            className={skillStyles.tableActionBtn}
            onClick={(e) => {
              e.stopPropagation();
              onView(row);
            }}
          >
            {t("common.view")}
          </button>
          {canMutate && onDelete ? (
            <Popconfirm
              title={t("skillPackages.deleteSkillConfirm")}
              okText={t("common.delete")}
              cancelText={t("common.cancel")}
              okButtonProps={{ danger: true }}
              onConfirm={() => onDelete(row)}
            >
              <button
                type="button"
                className={`${skillStyles.tableActionBtn} ${skillStyles.tableActionDanger}`}
                aria-label={t("common.delete")}
                onClick={(e) => e.stopPropagation()}
              >
                <Trash2 size={14} />
              </button>
            </Popconfirm>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <ResizableTable
      storageKey="skill-packages-skills"
      className={skillStyles.skillsTable}
      rowKey="slug"
      size="middle"
      pagination={false}
      dataSource={skills}
      columns={columns}
      onRow={(row) => ({
        onClick: () => onView(row),
        style: { cursor: "pointer" },
      })}
    />
  );
}
