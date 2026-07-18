import { Modal } from "antd";
import { useTranslation } from "react-i18next";
import FilePanelContent from "./FilePanelContent";

interface ChatFileModalProps {
  agentId: string;
  open: boolean;
  /** When set, the dialog opens on this path instead of the latest written one. */
  initialPath?: string | null;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  onClose: () => void;
}

/**
 * Centered document dialog (used by auth download file cards). The shared
 * viewer/editor body lives in ``FilePanelContent`` so the docked file panel
 * can reuse it.
 */
export default function ChatFileModal({
  agentId,
  open,
  initialPath,
  filePaths,
  onClose,
}: ChatFileModalProps) {
  const { t } = useTranslation();
  const resolvedPath = initialPath || filePaths[filePaths.length - 1] || "";
  const fileName = resolvedPath
    ? resolvedPath.split("/").filter(Boolean).pop() || resolvedPath
    : "";

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width="min(960px, 92vw)"
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          height: "78vh",
        },
      }}
      title={fileName || t("chat.fileWorkspace", "工作区文件")}
      destroyOnClose
    >
      <FilePanelContent
        agentId={agentId}
        filePaths={filePaths}
        initialPath={initialPath}
      />
    </Modal>
  );
}
