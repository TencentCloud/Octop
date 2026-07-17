import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import ChatFileModal from "./ChatFileModal";
import styles from "../index.module.less";

interface ChatFilePanelsProps {
  filePaths: string[];
  isMobile: boolean;
  open: boolean;
  agentId: string;
  onToggle: () => void;
  onClose: () => void;
}

/**
 * Floating "workspace files" entry for the chat page.
 *
 * Mirrors ``ChatBrowserPanels``: a fixed action button appears once the agent
 * has written a file, and clicking it opens a document box (``ChatFileModal``)
 * that reuses the shared ``FileViewer`` for preview / edit / download — not the
 * full workspace tree.
 */
export default function ChatFilePanels({
  filePaths,
  isMobile,
  open,
  agentId,
  onToggle,
  onClose,
}: ChatFilePanelsProps) {
  const { t } = useTranslation();

  if (filePaths.length === 0 || isMobile) return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          className={styles.filePanelBtn}
          onClick={onToggle}
          title={t("chat.fileWorkspace", "工作区文件")}
          aria-label={t("chat.fileWorkspace", "工作区文件")}
        >
          <FileText size={18} />
        </button>
      )}

      {open && (
        <ChatFileModal
          agentId={agentId}
          open={open}
          filePaths={filePaths}
          onClose={onClose}
        />
      )}
    </>
  );
}
