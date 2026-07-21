import { useState, useEffect } from "react";
import { Button, Card, Empty, Form, Segmented, Table, Tooltip } from "antd";
import { LayoutGrid, List, RefreshCw } from "lucide-react";
import type { CronJobSpecOutput } from "../../../api/types";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { setPendingPrefillText } from "../../Chat/hooks/chatStore";
import {
  createColumns,
  CronJobCard,
  ExecuteNowModal,
  JobDrawer,
  JobDetailDrawer,
  useCronJobs,
} from "./components";
import type { CronJobFormValues } from "./useCronJobs";
import { useCardTableView } from "../../../hooks/useCardTableView";
import { showConfirmModal } from "../../../utils/confirmModal";
import { TableSkeleton } from "../../../components/Skeleton";
import PageShell from "../../../layouts/PageShell";
import { useAgent } from "../../../context/AgentContext";
import styles from "./index.module.less";

type CronJob = CronJobSpecOutput;

// Flat clock SVG icon
function ClockIcon() {
  return (
    <svg
      width="56"
      height="56"
      viewBox="0 0 56 56"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle
        cx="28"
        cy="28"
        r="26"
        fill="var(--fn-color-brand-light, #fff0f3)"
        stroke="var(--fn-color-brand, #e85d75)"
        strokeWidth="2.5"
      />
      <circle cx="28" cy="28" r="3" fill="var(--fn-color-brand, #e85d75)" />
      <line
        x1="28"
        y1="28"
        x2="28"
        y2="14"
        stroke="var(--fn-color-brand, #e85d75)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <line
        x1="28"
        y1="28"
        x2="38"
        y2="34"
        stroke="var(--fn-text-tertiary, #9ca3af)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="28" cy="10" r="1.5" fill="var(--fn-color-brand, #e85d75)" />
      <circle cx="28" cy="46" r="1.5" fill="var(--fn-color-brand, #e85d75)" />
      <circle cx="10" cy="28" r="1.5" fill="var(--fn-color-brand, #e85d75)" />
      <circle cx="46" cy="28" r="1.5" fill="var(--fn-color-brand, #e85d75)" />
    </svg>
  );
}

interface CronJobsEmptyStateProps {
  onCreate: () => void;
  onSuggestionClick: (text: string) => void;
}

function CronJobsEmptyState({
  onCreate,
  onSuggestionClick,
}: CronJobsEmptyStateProps) {
  const { t } = useTranslation();
  const suggestions = [
    t("cronJobs.noJobsSuggestion1"),
    t("cronJobs.noJobsSuggestion2"),
    t("cronJobs.noJobsSuggestion3"),
  ];

  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyStateIcon}>
        <ClockIcon />
      </div>
      <h2 className={styles.emptyStateTitle}>{t("cronJobs.noJobs")}</h2>
      <p className={styles.emptyStateDesc}>{t("cronJobs.noJobsDesc")}</p>
      <div className={styles.emptyStateSuggestions}>
        {suggestions.map((text, i) => (
          <button
            key={i}
            type="button"
            className={styles.emptyStateSuggestionItem}
            onClick={() => onSuggestionClick(text)}
          >
            <span className={styles.emptyStateSuggestionText}>{text}</span>
            <span className={styles.emptyStateSuggestionArrow}>→</span>
          </button>
        ))}
      </div>
      <Button
        type="primary"
        onClick={onCreate}
        className={styles.emptyStateCreateBtn}
      >
        + {t("cronJobs.createJob")}
      </Button>
    </div>
  );
}

function CronJobsPage() {
  const { t } = useTranslation();
  const { isMobile, viewMode, setViewMode, showCardView } =
    useCardTableView("table");
  const navigate = useNavigate();
  const { activeAgentId } = useAgent();
  const {
    jobs,
    loading,
    cronTimezone,
    createJob,
    updateJob,
    deleteJob,
    toggleEnabled,
    executeNow,
    jobToFormValues,
    refetchJobs,
  } = useCronJobs();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<CronJobFormValues | null>(null);
  const [form] = Form.useForm<CronJobFormValues>();
  const [refreshing, setRefreshing] = useState(false);

  // Detail drawer state
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [detailJob, setDetailJob] = useState<CronJob | null>(null);

  // Execute-now confirmation
  const [executingJob, setExecutingJob] = useState<CronJob | null>(null);
  const [executing, setExecuting] = useState(false);

  const handleDetail = (job: CronJob) => {
    setDetailJob(job);
    setDetailDrawerOpen(true);
  };

  const handleDetailClose = () => {
    setDetailDrawerOpen(false);
    setDetailJob(null);
  };

  // Keep detail drawer in sync after list refresh (e.g. run-now).
  useEffect(() => {
    if (!detailDrawerOpen || !detailJob) return;
    const fresh = jobs.find((j) => j.id === detailJob.id);
    if (fresh) setDetailJob(fresh);
  }, [jobs, detailDrawerOpen, detailJob]);

  const handleCreate = () => {
    setEditingJob(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleSuggestionClick = (text: string) => {
    setPendingPrefillText(text);
    navigate("/chat", { state: { prefillInput: text } });
  };

  const handleEdit = (job: CronJob) => {
    setEditingJob(jobToFormValues(job, cronTimezone));
    setDrawerOpen(true);
  };

  const handleDelete = (jobId: string) => {
    showConfirmModal(
      {
        title: t("cronJobs.confirmDelete"),
        content: t("cronJobs.deleteConfirm"),
        okText: t("common.delete"),
        okType: "primary",
        cancelText: t("common.cancel"),
        onOk: async () => {
          await deleteJob(jobId);
        },
      },
      { isMobile },
    );
  };

  const handleToggleEnabled = async (job: CronJob) => {
    await toggleEnabled(job);
  };

  const handleExecuteNow = async (job: CronJob) => {
    setExecutingJob(job);
  };

  const handleExecuteNowConfirm = async () => {
    if (!executingJob) return;
    setExecuting(true);
    try {
      await executeNow(executingJob.id);
      setExecutingJob(null);
    } finally {
      setExecuting(false);
    }
  };

  const handleExecuteNowCancel = () => {
    if (executing) return;
    setExecutingJob(null);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetchJobs();
    setRefreshing(false);
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
    setEditingJob(null);
  };

  const handleSubmit = async (values: CronJobFormValues) => {
    let success = false;
    if (editingJob?.id) {
      success = await updateJob(editingJob.id, values);
    } else {
      success = await createJob(values);
    }
    if (success) {
      setDrawerOpen(false);
      setEditingJob(null);
    }
  };

  const columns = createColumns({
    onDetail: handleDetail,
    onToggleEnabled: handleToggleEnabled,
    onExecuteNow: handleExecuteNow,
    onEdit: handleEdit,
    onDelete: handleDelete,
    t,
    timeZone: cronTimezone,
  });

  // Until the user picks an agent there is nothing to fetch and no scope
  // to write to. Mirror the behaviour of the other octop agent-scoped pages.
  if (!activeAgentId) {
    return (
      <PageShell
        title={t("pageShell.tasks.title")}
        subtitle={t("pageShell.tasks.subtitle")}
        agentScoped
      >
        <Card>
          <Empty description={t("cronJobs.noAgentSelected")} />
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell
      title={t("pageShell.tasks.title")}
      subtitle={t("pageShell.tasks.subtitle")}
      agentScoped
    >
      {/* When empty, show the full-page empty state without a table card */}
      {!loading && jobs.length === 0 ? (
        <CronJobsEmptyState
          onCreate={handleCreate}
          onSuggestionClick={handleSuggestionClick}
        />
      ) : (
        <>
          {/* Toolbar — outside the card, matching experts page layout */}
          <div className={styles.gridToolbar}>
            <span className={styles.gridCount}>
              {t("cronJobs.totalItems", { count: jobs.length })}
            </span>
            <div className={styles.gridToolbarRight}>
              <Segmented
                size="small"
                value={viewMode}
                onChange={(v) => setViewMode(v as "table" | "card")}
                options={[
                  {
                    value: "table",
                    label: (
                      <span className={styles.viewModeLabel}>
                        <List size={14} />
                        {t("cronJobs.viewTable")}
                      </span>
                    ),
                  },
                  {
                    value: "card",
                    label: (
                      <span className={styles.viewModeLabel}>
                        <LayoutGrid size={14} />
                        {t("cronJobs.viewCard")}
                      </span>
                    ),
                  },
                ]}
              />
              <Tooltip title={t("common.refresh")}>
                <Button
                  icon={<RefreshCw size={15} />}
                  loading={refreshing}
                  onClick={handleRefresh}
                />
              </Tooltip>
              <Button type="primary" onClick={handleCreate}>
                + {t("cronJobs.createJob")}
              </Button>
            </div>
          </div>

          {/* Card grid or table */}
          {loading ? (
            <div style={{ padding: "8px 0" }}>
              <TableSkeleton rows={4} columns={isMobile ? 3 : 6} />
            </div>
          ) : showCardView ? (
            <div className={styles.cardGrid}>
              {jobs.map((job) => (
                <CronJobCard
                  key={job.id}
                  job={job}
                  timeZone={cronTimezone}
                  onToggleEnabled={handleToggleEnabled}
                  onExecuteNow={handleExecuteNow}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          ) : (
            <Card className={styles.tableCard} bodyStyle={{ padding: 0 }}>
              <Table
                columns={columns}
                dataSource={jobs}
                rowKey="id"
                scroll={{ x: "max-content" }}
                pagination={{
                  pageSize: 10,
                  showSizeChanger: false,
                  showTotal: (total) =>
                    t("cronJobs.totalItems", { count: total }),
                }}
              />
            </Card>
          )}
        </>
      )}

      <JobDrawer
        open={drawerOpen}
        editingJob={editingJob}
        activeAgentId={activeAgentId}
        cronTimezone={cronTimezone}
        form={form}
        onClose={handleDrawerClose}
        onSubmit={handleSubmit}
      />

      <JobDetailDrawer
        open={detailDrawerOpen}
        job={detailJob}
        timeZone={cronTimezone}
        onClose={handleDetailClose}
      />

      <ExecuteNowModal
        open={executingJob !== null}
        job={executingJob}
        loading={executing}
        onCancel={handleExecuteNowCancel}
        onConfirm={handleExecuteNowConfirm}
      />
    </PageShell>
  );
}

export default CronJobsPage;
