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
} from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

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

const statusOptions = (t: TFunction) =>
  [
    { value: "pending", label: t("memory.candidates.status.pending") },
    { value: "needs_review", label: t("memory.candidates.status.needsReview") },
    { value: "conflict", label: t("memory.candidates.status.conflict") },
    { value: "promoted", label: t("memory.candidates.status.promoted") },
    { value: "rejected", label: t("memory.candidates.status.rejected") },
    { value: "", label: t("memory.candidates.status.all") },
  ] as { value: CandidateStatus | ""; label: string }[];

const kindOptions = (t: TFunction) =>
  [
    { value: "", label: t("memory.candidates.kindAll") },
    { value: "Fact", label: t("memory.kind.fact") },
    { value: "Decision", label: t("memory.kind.decision") },
    { value: "Task", label: t("memory.kind.task") },
    { value: "Preference", label: t("memory.kind.preference") },
    { value: "ConflictCandidate", label: t("memory.kind.conflict") },
  ] as { value: AtomKind | ""; label: string }[];

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
          ? t("memory.candidates.promoteMerged", { n: r.merged })
          : r.needs_review > 0
          ? t("memory.candidates.promoteNeedsReview", { n: r.needs_review })
          : t("memory.candidates.promoteNew", { n: r.promoted });
      message.success(t("memory.candidates.promoteOk") + ` · ${detail}`);
      void load();
    } catch (e) {
      message.error((e as Error).message ?? t("common.operationFailed"));
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
      message.success(t("memory.candidates.rejectOk"));
      setRejectTarget(null);
      setRejectReason("");
      void load();
    } catch (e) {
      message.error((e as Error).message ?? t("common.operationFailed"));
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
            {t("memory.candidates.statusLabel")}
          </span>
          <Select
            className={styles.candidatesFilterSelect}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={statusOptions(t)}
          />
        </div>
        <div className={styles.candidatesFilterField}>
          <span className={styles.candidatesFilterLabel}>
            {t("memory.candidates.kindLabel")}
          </span>
          <Select
            className={styles.candidatesFilterSelect}
            value={kind}
            onChange={(v) => {
              setKind(v);
              setPage(1);
            }}
            options={kindOptions(t)}
          />
        </div>
      </div>

      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("memory.candidates.empty")}
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
                      {kindLabel(c.candidate_type, t)}
                    </Tag>
                    <Tag color={statusColor(c.status)}>
                      {statusLabel(c.status, t)}
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
                    title={t("memory.candidates.confirmPromote")}
                    okText={t("common.confirm")}
                    cancelText={t("common.cancel")}
                    disabled={decided}
                    onConfirm={() => void handlePromote(c)}
                  >
                    <Button
                      type="primary"
                      size="small"
                      loading={busyId === c.id}
                      disabled={decided}
                    >
                      {t("memory.candidates.promote")}
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
                    {t("memory.candidates.reject")}
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
        title={t("memory.candidates.detail")}
        open={!!selected}
        onClose={() => setSelected(null)}
        width={isMobile ? "100%" : 560}
      >
        {selected ? (
          <div>
            <Space size={4} wrap style={{ marginBottom: 12 }}>
              <Tag color={kindColor(selected.candidate_type)}>
                {kindLabel(selected.candidate_type, t)}
              </Tag>
              <Tag color={statusColor(selected.status)}>
                {statusLabel(selected.status, t)}
              </Tag>
              <ImportanceStars importance={selected.importance} />
            </Space>
            <Typography.Title level={5}>
              {t("memory.candidates.draftContent")}
            </Typography.Title>
            <Typography.Paragraph>{selected.assertion}</Typography.Paragraph>
            <Typography.Title level={5}>
              {t("memory.candidates.verbatimTitle")}
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              “{selected.verbatim_quote}”
            </Typography.Paragraph>
            <Typography.Title level={5}>
              {t("memory.candidates.suggestionTitle")}
            </Typography.Title>
            <Typography.Paragraph>
              {selected.recommended_action}
              {selected.promotion_reason
                ? ` — ${selected.promotion_reason}`
                : ""}
            </Typography.Paragraph>
            <Typography.Title level={5}>
              {t("memory.candidates.subjectTitle")}
            </Typography.Title>
            <Typography.Paragraph>{selected.subject_name}</Typography.Paragraph>
          </div>
        ) : null}
      </Drawer>

      <Modal
        title={t("memory.candidates.rejectTitle")}
        open={!!rejectTarget}
        confirmLoading={rejecting}
        okText={t("memory.candidates.confirmReject")}
        cancelText={t("common.cancel")}
        okButtonProps={{ danger: true }}
        onCancel={() => {
          if (rejecting) return;
          setRejectTarget(null);
          setRejectReason("");
        }}
        onOk={() => void handleReject()}
      >
        <Typography.Paragraph>
          {t("memory.candidates.rejectHint")}
        </Typography.Paragraph>
        <Input.TextArea
          rows={3}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder={t("memory.candidates.rejectReasonPlaceholder")}
        />
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Guidance banner — shown above the filter bar for actionable statuses
// ---------------------------------------------------------------------------

function GuidanceBanner({ status }: { status: CandidateStatus | "" }) {
  const { t } = useTranslation();
  if (status === "pending") {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 14 }}
        message={t("memory.candidates.guide.pendingTitle")}
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>{t("memory.candidates.guide.pending1")}</li>
            <li>
              {t("memory.candidates.guide.pending2a")}
              <strong>{t("memory.candidates.guide.pending2b")}</strong>。
            </li>
            <li>{t("memory.candidates.guide.pending3")}</li>
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
        message={t("memory.candidates.guide.reviewTitle")}
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>
              <strong>{t("memory.candidates.promote")}</strong>
              {t("memory.candidates.guide.reviewAcceptDesc")}
            </li>
            <li>
              <strong>{t("memory.candidates.reject")}</strong>
              {t("memory.candidates.guide.reviewRejectDesc")}
            </li>
            <li>
              <strong>{t("memory.candidates.guide.reviewTimeout")}</strong>
              {t("memory.candidates.guide.reviewTimeoutDesc")}
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
        message={t("memory.candidates.guide.conflictTitle")}
        description={
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, lineHeight: "1.8" }}>
            <li>{t("memory.candidates.guide.conflict1")}</li>
            <li>
              <strong>{t("memory.candidates.promote")}</strong>
              {t("memory.candidates.guide.conflictAcceptDesc")}
            </li>
            <li>
              <strong>{t("memory.candidates.reject")}</strong>
              {t("memory.candidates.guide.conflictRejectDesc")}
            </li>
            <li>
              <strong>{t("memory.candidates.guide.conflictNoTimeout")}</strong>
              {t("memory.candidates.guide.conflictNoTimeoutDesc")}
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

function kindLabel(k: string, t: TFunction): string {
  switch (k) {
    case "Fact":
      return t("memory.kind.fact");
    case "Decision":
      return t("memory.kind.decision");
    case "Task":
      return t("memory.kind.task");
    case "Preference":
      return t("memory.kind.preference");
    case "ConflictCandidate":
      return t("memory.kind.conflict");
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

function statusLabel(s: string, t: TFunction): string {
  switch (s) {
    case "pending":
      return t("memory.candidates.status.pending");
    case "needs_review":
      return t("memory.candidates.status.needsReview");
    case "conflict":
      return t("memory.candidates.status.conflict");
    case "promoted":
      return t("memory.candidates.status.promoted");
    case "rejected":
      return t("memory.candidates.status.rejected");
    default:
      return s;
  }
}
function ImportanceStars({ importance }: { importance: string }) {
  const { t } = useTranslation();
  const n = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      title={t("memory.tree.importanceTag", {
        v:
          importance === "high"
            ? t("memory.tree.importanceHigh")
            : importance === "medium"
            ? t("memory.tree.importanceMedium")
            : t("memory.tree.importanceLow"),
      })}
      style={{ color: "#faad14", fontSize: 13, letterSpacing: 1 }}
    >
      {"★".repeat(n)}
      <span style={{ color: "#d9d9d9" }}>{"★".repeat(3 - n)}</span>
    </span>
  );
}
