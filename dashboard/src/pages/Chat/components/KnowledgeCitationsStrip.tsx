import { useState } from "react";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { KnowledgeCitation } from "../../../utils/parseKnowledgeCitations";
import { knowledgeCitationTooltip } from "../../../utils/knowledgeCitationDisplay";
import { KnowledgeCitationPreviewModal } from "./KnowledgeCitationPreviewModal";
import styles from "../index.module.less";

export function KnowledgeCitationsStrip({
  citations,
}: {
  citations: KnowledgeCitation[];
}) {
  const { t } = useTranslation();
  const [previewCitation, setPreviewCitation] =
    useState<KnowledgeCitation | null>(null);

  if (citations.length === 0) return null;

  return (
    <>
      <div
        className={styles.knowledgeCitations}
        aria-label={t("chat.citations")}
      >
        <div className={styles.knowledgeCitationsLabel}>
          {t("chat.citations")}
        </div>
        <div className={styles.knowledgeCitationsList}>
          {citations.map((citation) => (
            <button
              key={citation.docId}
              type="button"
              className={styles.knowledgeCitationChip}
              title={knowledgeCitationTooltip(citation)}
              onClick={() => setPreviewCitation(citation)}
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
      <KnowledgeCitationPreviewModal
        citation={previewCitation}
        open={previewCitation != null}
        onClose={() => setPreviewCitation(null)}
      />
    </>
  );
}
