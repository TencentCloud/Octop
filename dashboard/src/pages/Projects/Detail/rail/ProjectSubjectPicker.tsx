import { Button, Spin } from "antd";
import { Bot, Check, Plus, RefreshCw, Users } from "lucide-react";
import { useTranslation } from "react-i18next";

import SearchablePickerPanel from "../../../../components/ChatPicker/SearchablePickerPanel";
import styles from "./ProjectSubjectPicker.module.less";

/**
 * 右栏「+」四类统一到图 2 形态的**唯一薄封装**（PLAN §1.1 / §6）。
 *
 * ★ 复用而非平行实现：列表渲染与搜索**完全交给**
 * `components/ChatPicker/SearchablePickerPanel<T>`（其内部即 `useFilteredList`）；
 * 本文件只做「数据源适配 + 已加入勾选态 + 单选提交」，不另写列表/滚动实现
 * （判据：`grep -rc 'SearchablePickerPanel' rail/` ≥ 2）。
 *
 * ★ 单选语义（PLAN §1.3）：**点卡片即加入**；图 2 的「已选 N」是多选计数，
 * 本批**不显示**（边界 C7）。
 */

export type ProjectSubjectKind = "agent" | "team";

export interface ProjectSubjectOption {
  kind: ProjectSubjectKind;
  id: string;
  /** 空串 = 无名字（父层负责回退显示 `subject_id`，组件不猜）。 */
  name: string;
  description?: string;
  /** true = 已在项目成员里 → 勾选态 + 不可重复提交（R13 / C12）。 */
  joined?: boolean;
}

export interface ProjectSubjectPickerProps {
  kind: ProjectSubjectKind;
  /** 专家 / 团队 切换（成员面板）。 */
  onKindChange: (next: ProjectSubjectKind) => void;
  options: ProjectSubjectOption[];
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  onPick: (option: ProjectSubjectOption) => void;
  emptyMessage: string;
}

/** agent/team 的中文键映射（导出供兄弟面板复用，避免第三份枚举）。 */
export const KIND_LABEL_KEYS: Record<ProjectSubjectKind, string> = {
  agent: "projects.subjectAgent",
  team: "projects.subjectTeam",
};

export function ProjectSubjectPicker({
  kind,
  onKindChange,
  options,
  loading,
  failed,
  onRetry,
  onPick,
  emptyMessage,
}: ProjectSubjectPickerProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={styles.picker}>
      <div className={styles.kindRow}>
        {(["agent", "team"] as const).map((value) => (
          <Button
            key={value}
            type="text"
            size="small"
            icon={value === "agent" ? <Bot size={13} /> : <Users size={13} />}
            className={
              value === kind
                ? `${styles.kind} ${styles.kindActive}`
                : styles.kind
            }
            data-testid={`picker-kind-${value}`}
            aria-pressed={value === kind}
            onClick={() => onKindChange(value)}
          >
            {t(KIND_LABEL_KEYS[value])}
          </Button>
        ))}
      </div>

      {/* ★ `picker-panel` 在**所有状态**下都存在（加载/失败/成功）——
          AC-C-1 要求四类面板都渲染该 testid（骨架 = `SearchablePickerPanel`）。 */}
      <div className={styles.panelHost} data-testid="picker-panel">
        {loading ? (
          /* R10：加载中**不得**显示空态文案（避免被读成「没有候选」）。 */
          <div className={styles.centered} data-testid="picker-loading">
            <Spin size="small" />
          </div>
        ) : failed ? (
          /* 失败 → 可重试；**不得**静默空列表。 */
          <div className={styles.failed} data-testid="picker-failed">
            <Button
              size="small"
              icon={<RefreshCw size={13} />}
              data-testid="picker-retry"
              onClick={onRetry}
            >
              {t("common.retry")}
            </Button>
          </div>
        ) : (
          <SearchablePickerPanel<ProjectSubjectOption>
            items={options}
            filterFn={(option, query) =>
              `${option.name}\n${option.id}\n${option.description ?? ""}`
                .toLowerCase()
                .includes(query)
            }
            searchPlaceholder={t("projects.quickInputRecipientFilter")}
            emptyMessage={emptyMessage}
            renderItem={(option) => (
              <button
                key={`${option.kind}:${option.id}`}
                type="button"
                className={styles.option}
                data-testid={`picker-option-${option.kind}-${option.id}`}
                disabled={option.joined}
                aria-pressed={Boolean(option.joined)}
                onClick={() => onPick(option)}
              >
                <span className={styles.optionName}>
                  {/* 名字为空 → 回退显示 id（父层已回退，这里只兜底不空白）。 */}
                  {option.name.trim() ? option.name : option.id}
                </span>
                {option.description ? (
                  <span className={styles.optionDesc}>
                    {option.description}
                  </span>
                ) : null}
                {option.joined ? (
                  <span
                    className={styles.joined}
                    data-testid={`picker-joined-${option.kind}-${option.id}`}
                  >
                    <Check size={13} />
                  </span>
                ) : null}
              </button>
            )}
            footerIcon={<Plus size={15} aria-hidden />}
            footerLabel={t("projects.memberAdd")}
            /* 单选：加入动作在卡片上（PLAN §1.3）；底部行保留骨架形态——
               图 2 的底部确认属于**多选**场景，本批不显示「已选 N」。 */
            onFooterClick={() => undefined}
          />
        )}
      </div>
    </div>
  );
}

export default ProjectSubjectPicker;
