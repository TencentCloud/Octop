import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Empty, Modal, Spin, Switch, Tabs, message } from "antd";
import { History, RefreshCw, Sparkles, TimerReset } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  octopThreadsApi,
  type ThreadTaskSummary,
} from "../../api/modules/octopThreads";
import { useAgent } from "../../context/AgentContext";
import PageShell from "../../layouts/PageShell";
import CronJobsPage from "../Control/CronJobs";
import { TaskDetailDrawer, TaskRunCard } from "./TaskRunCard";
import styles from "./index.module.less";

function ThreadTasksPanel({ status }: { status: "active" | "completed" }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeAgentId } = useAgent();
  const [tasks, setTasks] = useState<ThreadTaskSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(status === "active");
  const [selectedTask, setSelectedTask] = useState<ThreadTaskSummary | null>(
    null,
  );
  const requestGeneration = useRef(0);

  const load = useCallback(
    async (quiet = false) => {
      const generation = ++requestGeneration.current;
      if (!activeAgentId) {
        setTasks([]);
        return;
      }
      if (quiet) setRefreshing(true);
      else setLoading(true);
      try {
        const rows = await octopThreadsApi.tasks(activeAgentId, status, 20);
        if (generation !== requestGeneration.current) return;
        const sorted = [...rows].sort(
          (left, right) =>
            Number(right.turn_active) - Number(left.turn_active) ||
            right.last_active - left.last_active,
        );
        setTasks(sorted);
        setSelectedTask((selected) =>
          selected
            ? sorted.find((row) => row.thread_id === selected.thread_id) || null
            : null,
        );
      } catch {
        if (generation === requestGeneration.current && !quiet) setTasks([]);
      } finally {
        if (generation === requestGeneration.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [activeAgentId, status],
  );

  useEffect(() => {
    void load();
    return () => {
      requestGeneration.current += 1;
    };
  }, [load]);

  useEffect(() => {
    if (status !== "active" || !autoRefresh || !activeAgentId) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [activeAgentId, autoRefresh, load, status]);

  const openThread = useCallback(
    (task: ThreadTaskSummary) => {
      if (!activeAgentId) return;
      navigate(`/chat/${activeAgentId}/${task.thread_id}`);
    },
    [activeAgentId, navigate],
  );

  const cancelTask = useCallback(
    (task: ThreadTaskSummary) => {
      if (!activeAgentId || !task.turn_active) return;
      Modal.confirm({
        title: t("taskCenter.cancelConfirmTitle"),
        content: t("taskCenter.cancelConfirmDesc"),
        okText: t("taskCenter.stopRun"),
        cancelText: t("common.cancel"),
        okButtonProps: { danger: true },
        onOk: async () => {
          const result = await octopThreadsApi.cancelTurn(
            activeAgentId,
            task.thread_id,
          );
          if (result.cancelled) message.success(t("taskCenter.cancelled"));
          await load(true);
        },
      });
    },
    [activeAgentId, load, t],
  );

  const runningCount = tasks.filter((task) => task.turn_active).length;
  const waitingCount = tasks.filter((task) => !task.turn_active).length;
  const completedSteps = tasks.reduce((sum, task) => sum + task.completed, 0);
  const featuredTask = tasks[0];
  const queuedTasks = tasks.slice(1);

  if (!activeAgentId) {
    return (
      <Card>
        <Empty description={t("taskCenter.noAgent")} />
      </Card>
    );
  }
  if (loading && tasks.length === 0) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    );
  }

  return (
    <div className={styles.threadTasks}>
      <div className={styles.toolbar}>
        <div>
          <strong>
            {status === "active"
              ? t("taskCenter.activeHeading")
              : t("taskCenter.historyHeading")}
          </strong>
          <span>{t("taskCenter.count", { count: tasks.length })}</span>
        </div>
        <div className={styles.toolbarActions}>
          {status === "active" ? (
            <label className={styles.liveRefreshToggle}>
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={setAutoRefresh}
              />
              {t("taskCenter.liveRefresh")}
            </label>
          ) : null}
          <Button
            icon={<RefreshCw size={15} />}
            loading={refreshing}
            onClick={() => void load(true)}
          >
            {t("common.refresh")}
          </Button>
        </div>
      </div>

      {status === "active" && tasks.length > 0 ? (
        <div className={styles.runStats}>
          <div>
            <Sparkles size={17} />
            <span>{t("taskCenter.runningNow")}</span>
            <strong>{runningCount}</strong>
          </div>
          <div>
            <TimerReset size={17} />
            <span>{t("taskCenter.awaitingInput")}</span>
            <strong>{waitingCount}</strong>
          </div>
          <div>
            <History size={17} />
            <span>{t("taskCenter.stepsCompleted")}</span>
            <strong>{completedSteps}</strong>
          </div>
        </div>
      ) : null}

      {tasks.length === 0 ? (
        <div className={styles.emptyRunState}>
          <Empty
            description={
              status === "active"
                ? t("taskCenter.noActive")
                : t("taskCenter.noHistory")
            }
          />
        </div>
      ) : (
        <>
          {featuredTask ? (
            <section>
              <div className={styles.sectionLabel}>
                {status === "active"
                  ? featuredTask.turn_active
                    ? t("taskCenter.currentRun")
                    : t("taskCenter.nextPlan")
                  : t("taskCenter.latestCompleted")}
              </div>
              <TaskRunCard
                task={featuredTask}
                featured
                onDetails={() => setSelectedTask(featuredTask)}
                onOpenThread={() => openThread(featuredTask)}
                onCancel={() => cancelTask(featuredTask)}
              />
            </section>
          ) : null}
          {queuedTasks.length > 0 ? (
            <section>
              <div className={styles.sectionLabel}>
                {status === "active"
                  ? t("taskCenter.otherPlans")
                  : t("taskCenter.earlierRuns")}
              </div>
              <div className={styles.cardGrid}>
                {queuedTasks.map((task) => (
                  <TaskRunCard
                    key={task.thread_id}
                    task={task}
                    onDetails={() => setSelectedTask(task)}
                    onOpenThread={() => openThread(task)}
                    onCancel={() => cancelTask(task)}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}

      <TaskDetailDrawer
        task={selectedTask}
        open={selectedTask !== null}
        onClose={() => setSelectedTask(null)}
        onOpenThread={() => selectedTask && openThread(selectedTask)}
        onCancel={() => selectedTask && cancelTask(selectedTask)}
      />
    </div>
  );
}

export default function TasksPage() {
  const { t } = useTranslation();
  const tabs = useMemo(
    () => [
      {
        key: "active",
        label: t("taskCenter.tabs.active"),
        children: <ThreadTasksPanel status="active" />,
      },
      {
        key: "scheduled",
        label: t("taskCenter.tabs.scheduled"),
        children: <CronJobsPage embedded />,
      },
      {
        key: "history",
        label: t("taskCenter.tabs.history"),
        children: <ThreadTasksPanel status="completed" />,
      },
    ],
    [t],
  );
  return (
    <PageShell
      title={t("pageShell.tasks.title")}
      subtitle={t("pageShell.tasks.subtitle")}
      agentScoped
    >
      <Tabs defaultActiveKey="active" items={tabs} destroyInactiveTabPane />
    </PageShell>
  );
}
