import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Empty, Spin, Tag, Typography } from "antd";
import { Brain, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAgent } from "../../../context/AgentContext";
import {
  projectsApi,
  type ProjectMemoryRow,
} from "../../../api/modules/projects";

const { Text } = Typography;

/**
 * 「项目记忆」Tab (T-86 = the previous run's T-40, acceptance verbatim).
 *
 * Data source is the T-37 read route `GET /api/projects/{id}/memory`, reached
 * **only** through `api/modules/projects.ts` (card #3: no `fetch` here).
 *
 * Three states are deliberate, not incidental:
 *
 * * **0 rows** is an **empty state**, never an error — a project with no memory
 *   yet is the normal starting point (the backend's own word: an empty state, not
 *   an error). It points at 「记到项目」 rather than rendering a failure.
 * * **403** is a **permission state**. The frontend does **not** re-decide it: the
 *   backend's project-role read check is the only authority (card #2 — 不得在前端
 *   复制权限矩阵), so this file contains no role table, no permission constant and
 *   no member lookup. It only recognises the transport's 403 and renders a
 *   friendly line.
 * * a **missing active agent** is a "pick one first" hint rather than a request:
 *   `agent_id` locates the memory backend, so without it there is nothing to ask
 *   (and asking anyway would surface a 422 as if it were a failure).
 */

/** 403 as the transport reports it: `request` throws `Error` carrying the status. */
function isForbidden(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const raw = error.message;
  return /\b403\b/.test(raw) || raw.includes("PROJECT_FORBIDDEN");
}

export interface ProjectMemoryTabProps {
  projectId: string;
}

export default function ProjectMemoryTab({ projectId }: ProjectMemoryTabProps) {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const [items, setItems] = useState<ProjectMemoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!activeAgentId) {
      // No locator ⇒ no request. Not an error: the hint below explains it.
      setItems([]);
      setDenied(false);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setDenied(false);
    setError(null);
    void (async () => {
      try {
        const page = await projectsApi.fetchMemory(projectId, {
          agentId: activeAgentId,
        });
        if (cancelled) return;
        setItems(page.items ?? []);
      } catch (err) {
        if (cancelled) return;
        // Permission is a state, not a failure (and it is the backend's call).
        if (isForbidden(err)) {
          setDenied(true);
          setItems([]);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, activeAgentId, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  if (!activeAgentId) {
    return (
      <Empty
        data-testid="project-memory-no-agent"
        image={<Brain size={40} strokeWidth={1.5} />}
        description={
          <span>
            {t("projects.memoryNoAgent", "请先在顶部选择一个 agent")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                "projects.memoryNoAgentHint",
                "项目记忆存放在 agent 的记忆库里，选中 agent 后这里会显示内容。",
              )}
            </Text>
          </span>
        }
      />
    );
  }

  if (denied) {
    return (
      <Empty
        data-testid="project-memory-denied"
        image={<Brain size={40} strokeWidth={1.5} />}
        description={
          <span>
            {t("projects.memoryDenied", "无权查看该项目的记忆")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                "projects.memoryDeniedHint",
                "项目记忆按项目成员授权；请让项目 owner 把你加为成员。",
              )}
            </Text>
          </span>
        }
      />
    );
  }

  if (loading) {
    return (
      <div data-testid="project-memory-loading" style={{ padding: 24 }}>
        <Spin />
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        data-testid="project-memory-error"
        type="error"
        showIcon
        message={t("projects.memoryError", "项目记忆加载失败")}
        description={error}
        action={
          <Button size="small" icon={<RefreshCw size={14} />} onClick={retry}>
            {t("common.retry", "重试")}
          </Button>
        }
      />
    );
  }

  if (items.length === 0) {
    // Card #1: zero rows renders the empty state **and** the 「记到项目」 lead-in.
    return (
      <Empty
        data-testid="project-memory-empty"
        image={<Brain size={40} strokeWidth={1.5} />}
        description={
          <span>
            {t("projects.memoryEmpty", "暂无项目记忆")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                "projects.memoryEmptyHint",
                "在「记忆」页对一条候选或记忆使用「记到项目」，它就会出现在这里。",
              )}
            </Text>
          </span>
        }
      />
    );
  }

  return (
    <ul
      data-testid="project-memory-list"
      style={{ listStyle: "none", margin: 0, padding: 0 }}
    >
      {items.map((row) => (
        <li
          key={row.id}
          data-testid="project-memory-row"
          style={{
            padding: "8px 0",
            borderBottom: "1px solid var(--octop-border, #f0f0f0)",
          }}
        >
          <Text>{row.text}</Text>
          {row.source_layer ? (
            <Tag style={{ marginLeft: 8 }}>{row.source_layer}</Tag>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
