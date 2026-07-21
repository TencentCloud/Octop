/**
 * CandidatesReview.tsx — pending Candidate inbox.
 *
 * The candidate-review tab on the Memory page. Lists L1 Candidate rows
 * extracted by the LLM and lets the user promote them to atoms
 * or reject them. Both actions hit the same dashboard surface
 * the bridge already exposes (``promoteCandidate`` / ``rejectCandidate``).
 *
 * MVP scope:
 *   - status / candidate_type filters (defaults status = "pending")
 *   - row-level promote / reject buttons (promote is double-confirmed;
 *     reject opens a small modal so the user can attach a reason)
 *   - click the row → drawer with full Candidate detail (assertion,
 *     verbatim quote, raw_event ids, importance, etc.)
 *
 * Out of scope (deferred):
 *   - bulk select / bulk promote
 *   - inline editing of the candidate before promotion
 *   - the candidate diff view (vs existing atoms) — covered elsewhere.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Modal,
  Pagination,
  Popconfirm,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type AtomKind,
  type CandidateItem,
  type CandidateStatus,
  type ListCandidatesBody,
} from "../../../api/modules/memoryDashboard";
import { useIsMobile } from "../../../hooks/useIsMobile";
import styles from "./CandidatesReview.module.less";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: CandidateStatus | ""; label: string }[] = [
  { value: "pending", label: "待处理" },
  { value: "needs_review", label: "待复核" },
  { value: "conflict", label: "可能冲突" },
  { value: "promoted", label: "已采纳" },
  { value: "rejected", label: "已忽略" },
  { value: "", label: "全部" },
];

const KIND_OPTIONS: { value: AtomKind | ""; label: string }[] = [
  { value: "", label: "全部类型" },
  { value: "Fact", label: "事实" },
  { value: "Decision", label: "决定" },
  { value: "Task", label: "任务" },
  { value: "Preference", label: "偏好" },
  { value: "ConflictCandidate", label: "可能冲突" },
];

interface Props {
  agentId: string;
}

export default function CandidatesReview({ agentId }: Props) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const [items, setItems] = useState<CandidateItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<CandidateStatus | "">("");
  const [kind, setKind] = useState<AtomKind | "">("");
  const [selected, setSelected] = useState<CandidateItem | null>(null);

  // reject-with-reason modal
  const [rejectTarget, setRejectTarget] = useState<CandidateItem | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);

  // per-row pending state so the spinning button is local, not global
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const body: ListCandidatesBody = {
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    };
    if (status) body.status = status;
    if (kind) body.candidate_type = kind;
    try {
      const r = await memoryDashboardApi.listCandidates(agentId, body);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      message.error((e as Error).message ?? "load failed");
    } finally {
      setLoading(false);
    }
    // ``t`` is intentionally NOT a dependency — the i18n hook returns
    // a fresh ``t`` ref on every render, which would re-fire the load
    // effect on every keystroke / hover.
  }, [agentId, page, status, kind]);

  useEffect(() => {
    if (!agentId) return;
    void load();
  }, [agentId, load]);

  const handlePromote = async (c: CandidateItem) => {
    setBusyId(c.id);
    try {
      const r = await memoryDashboardApi.promoteCandidate(agentId, c.id);
      const detail =
        r.merged > 0
          ? `与现有记忆合并 ${r.merged} 条`
          : r.needs_review > 0
          ? `需复核 ${r.needs_review} 条`
          : `新增采纳 ${r.promoted} 条`;
      message.success(
        t("memory.candidates.promoteOk", "已采纳") + ` · ${detail}`,
      );
      void load();
    } catch (e) {
      message.error((e as Error).message ?? "操作失败");
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async () => {
    if (!rejectTarget) return;
    setRejecting(true);
    try {
      await memoryDashboardApi.rejectCandidate(agentId, rejectTarget.id, {
        reason: rejectReason.trim() || undefined,
      });
      message.success(t("memory.candidates.rejectOk", "已忽略"));
      setRejectTarget(null);
      setRejectReason("");
      void load();
    } catch (e) {
      message.error((e as Error).message ?? "操作失败");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <Card size="small" className={styles.candidatesCard}>
      <GuidanceBanner status={status} />
      <div className={styles.candidatesFilters}>
        <div className={styles.candidatesFilterField}>
          <span className={styles.candidatesFilterLabel}>
            {t("memory.candidates.statusLabel", "状态")}
          </span>
          <Select
            className={styles.candidatesFilterSelect}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={STATUS_OPTIONS}
          />
        </div>
        <div className={styles.candidatesFilterField}>
          <span className={styles.candidatesFilterLabel}>
            {t("memory.candidates.kindLabel", "类型")}
          </span>
          <Select
            className={styles.candidatesFilterSelect}
            value={kind}
            onChange={(v) => {
              setKind(v);
              setPage(1);
            }}
            options={KIND_OPTIONS}
          />
        </div>
      </div>

      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("memory.candidates.empty", "暂无记忆内容")}
        />
      ) : (
        <ul className={styles.candidateList}>
          {items.map((c) => {
            const decided = c.status === "promoted" || c.status === "rejected";
            return (
              <li key={c.id} className={styles.candidateRow}>
                <div
                  className={styles.candidateMain}
                  onClick={() => setSelected(c)}
                >
                  <Space size={4} wrap>
                    <Tag color={kindColor(c.candidate_type)}>
                      {kindLabel(c.candidate_type)}
                    </Tag>
                    <Tag color={statusColor(c.status)}>
                      {statusLabel(c.status)}
                    </Tag>
                    <ImportanceStars importance={c.importance} />
                  </Space>
                  <div className={styles.candidateTitle}>
                    {c.title || c.assertion}
                  </div>
                  <div className={styles.candidateMeta}>
                    “{c.verbatim_quote}” · {c.subject_name}
                  </div>
                </div>
                <div className={styles.candidateActions}>
                  <Popconfirm
                    title={t(
                      "memory.candidates.confirmPromote",
                      "采纳这条记忆？",
                    )}
                    okText={t("common.confirm", "采纳")}
                    cancelText={t("common.cancel", "取消")}
                    disabled={decided}
                    onConfirm={() => void handlePromote(c)}
                  >
                    <Button
                      type="primary"
                      size="small"
                      loading={busyId === c.id}
                      disabled={decided}
                    >
                      {t("memory.candidates.promote", "采纳")}
                    </Button>
                  </Popconfirm>
                  <Button
                    danger
                    size="small"
                    disabled={decided}
                    onClick={() => {
                      setRejectTarget(c);
                      setRejectReason("");
                    }}
                  >
                    {t("memory.candidates.reject", "忽略")}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className={styles.candidatesPagination}>
        <Pagination
          current={page}
          pageSize={PAGE_SIZE}
          total={total}
          showSizeChanger={false}
          onChange={setPage}
          size={isMobile ? "small" : "default"}
        />
      </div>

      <Drawer
        title={t("memory.candidates.detail", "记忆草稿详情")}
        open={!!selected}
        onClose={() => setSelected(null)}
        width={isMobile ? "100%" : 560}
      >
        {selected ? (
          <div>
            <Space size={4} wrap style={{ marginBottom: 12 }}>
              <Tag color={kindColor(selected.candidate_type)}>
                {kindLabel(selected.candidate_type)}
              </Tag>
              <Tag color={statusColor(selected.status)}>
                {statusLabel(selected.status)}
              </Tag>
              <ImportanceStars importance={selected.importance} />
            </Space>
            <Typography.Title level={5}>草稿内容</Typography.Title>
            <Typography.Paragraph>{selected.assertion}</Typography.Paragraph>
            <Typography.Title level={5}>原话依据</Typography.Title>
            <Typography.Paragraph type="secondary">
              “{selected.verbatim_quote}”
            </Typography.Paragraph>
            <Typography.Title level={5}>Octop 的建议</Typography.Title>
            <Typography.Paragraph>
              {selected.recommended_action}
              {selected.promotion_reason
                ? ` — ${selected.promotion_reason}`
                : ""}
            </Typography.Paragraph>
            <Typography.Title level={5}>关于谁 / 什么</Typography.Title>
            <Typography.Paragraph>{selected.subject_name}</Typography.Paragraph>
          </div>
        ) : null}
      </Drawer>

      <Modal
        title={t("memory.candidates.rejectTitle", "忽略这条草稿")}
        open={!!rejectTarget}
        confirmLoading={rejecting}
        okText={t("memory.candidates.confirmReject", "确认忽略")}
        cancelText={t("common.cancel", "取消")}
        okButtonProps={{ danger: true }}
        onCancel={() => {
          if (rejecting) return;
          setRejectTarget(null);
          setRejectReason("");
        }}
        onOk={() => void handleReject()}
      >
        <Typography.Paragraph>
          {t(
            "memory.candidates.rejectHint",
            "忽略后这条记忆不会进入长期记忆。可选择填写原因，便于日后回顾。",
          )}
        </Typography.Paragraph>
        <Input.TextArea
          rows={3}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder={t(
            "memory.candidates.rejectReasonPlaceholder",
            "原因可选，例如：已过期 / 记录有误 / 不重要",
          )}
        />
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Guidance banner — shown above the filter bar for actionable statuses
// ---------------------------------------------------------------------------

function GuidanceBanner({ status }: { status: CandidateStatus | "" }) {
  if (status === "pending") {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 14 }}
        message="关于「待处理」草稿"
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>这些草稿由 Octop 从对话中自动提取，正在等待系统规则判断。</li>
            <li>
              系统会自动决定：直接采纳、合并到已有记忆、标记为待复核或丢弃——
              <strong>无需手动干预</strong>。
            </li>
            <li>
              如需提前处理，可切换到「待复核」或「可能冲突」状态查看需要你决策的草稿。
            </li>
          </ul>
        }
      />
    );
  }

  if (status === "needs_review") {
    return (
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 14 }}
        message="关于「待复核」草稿"
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>
              <strong>采纳</strong> → 立即进入长期记忆，下次对话优先使用。
            </li>
            <li>
              <strong>忽略</strong> →
              不会进入长期记忆，可附上原因（保存在操作日志中，便于日后回顾）。
            </li>
            <li>
              <strong>⏰ 若 7 天内未处理</strong>
              ，系统会自动将其加入长期记忆，但置信度较低，排序靠后，不影响主要对话。
            </li>
          </ul>
        }
      />
    );
  }

  if (status === "conflict") {
    return (
      <Alert
        type="error"
        showIcon
        style={{ marginBottom: 14 }}
        message="关于「可能冲突」草稿"
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>
              这些草稿与已有长期记忆存在矛盾，系统无法自动裁决，需要你来决定哪个是准确的。
            </li>
            <li>
              <strong>采纳</strong> → 以这条草稿为准，进入长期记忆。
            </li>
            <li>
              <strong>忽略</strong> → 保留原有记忆不变。
            </li>
            <li>
              <strong>⚠️ 冲突草稿没有自动超时</strong>
              ，不处理会一直停留在此队列。
            </li>
          </ul>
        }
      />
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

function kindColor(k: string): string {
  switch (k) {
    case "Fact":
      return "default";
    case "Decision":
      return "geekblue";
    case "Task":
      return "orange";
    case "Preference":
      return "green";
    case "ConflictCandidate":
      return "red";
    default:
      return "default";
  }
}

function kindLabel(k: string): string {
  switch (k) {
    case "Fact":
      return "事实";
    case "Decision":
      return "决定";
    case "Task":
      return "任务";
    case "Preference":
      return "偏好";
    case "ConflictCandidate":
      return "可能冲突";
    default:
      return k;
  }
}

function statusColor(s: string): string {
  switch (s) {
    case "pending":
      return "blue";
    case "needs_review":
      return "orange";
    case "conflict":
      return "red";
    case "promoted":
      return "green";
    case "rejected":
      return "default";
    default:
      return "default";
  }
}

function statusLabel(s: string): string {
  switch (s) {
    case "pending":
      return "待处理";
    case "needs_review":
      return "待复核";
    case "conflict":
      return "可能冲突";
    case "promoted":
      return "已采纳";
    case "rejected":
      return "已忽略";
    default:
      return s;
  }
}
function ImportanceStars({ importance }: { importance: string }) {
  const n = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      title={`重要程度：${
        importance === "high"
          ? "非常重要"
          : importance === "medium"
          ? "重要"
          : "一般"
      }`}
      style={{ color: "#faad14", fontSize: 13, letterSpacing: 1 }}
    >
      {"★".repeat(n)}
      <span style={{ color: "#d9d9d9" }}>{"★".repeat(3 - n)}</span>
    </span>
  );
}
