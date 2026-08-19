import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { KnowledgeCitation } from "../../../utils/parseKnowledgeCitations";
import styles from "../index.module.less";

export function knowledgeCitationHref(citation: KnowledgeCitation): string {
  const params = new URLSearchParams();
  if (citation.kbId) params.set("kb", citation.kbId);
  if (citation.docId) params.set("doc", citation.docId);
  const qs = params.toString();
  return qs ? `/knowledge-bases?${qs}` : "/knowledge-bases";
}

export function KnowledgeCitationsStrip({
  citations,
}: {
  citations: KnowledgeCitation[];
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (citations.length === 0) return null;

  return (
    <div className={styles.knowledgeCitations} aria-label={t("chat.citations")}>
      <div className={styles.knowledgeCitationsLabel}>
        {t("chat.citations")}
      </div>
      <div className={styles.knowledgeCitationsList}>
        {citations.map((citation) => (
          <button
            key={citation.docId}
            type="button"
            className={styles.knowledgeCitationChip}
            title={
              citation.kbName
                ? `${citation.kbName} · ${citation.filename}`
                : citation.filename
            }
            onClick={() => navigate(knowledgeCitationHref(citation))}
          >
            <FileText size={13} strokeWidth={2} aria-hidden />
            <span className={styles.knowledgeCitationName}>
              {citation.filename}
            </span>
            {citation.kbName ? (
              <span className={styles.knowledgeCitationKb}>
                {citation.kbName}
              </span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}
