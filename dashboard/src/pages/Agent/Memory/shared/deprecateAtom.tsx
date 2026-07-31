/**
 * deprecateAtom — shared confirmation flow for manually deprecating one memory.
 *
 * Reuses the same confirm dialog, optional reason input, deprecateAtom call,
 * and toast behavior across tree and list drawers.
 */
import { Input, Modal, Typography } from "antd";
import { message } from "@/utils/antdMessage";

import {
  memoryDashboardApi,
  type AtomItem,
} from "../../../../api/modules/memoryDashboard";

export function confirmDeprecateAtom({
  agentId,
  atom,
  onSuccess,
}: {
  agentId: string;
  atom: AtomItem;
  /** Callback after successful deprecation, usually to close drawer and refresh list. */
  onSuccess?: () => void;
}) {
  let reason = "";
  Modal.confirm({
    title: "弃用这条记忆？",
    content: (
      <div>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          弃用后 Octop
          将不再使用这条记忆。如果是记录有误，建议先描述正确内容作为弃用原因。
        </Typography.Paragraph>
        <Input.TextArea
          placeholder="可选：填写弃用原因，比如「已过期」「记录有误」"
          rows={3}
          onChange={(e) => {
            reason = e.target.value;
          }}
        />
      </div>
    ),
    okText: "弃用",
    okType: "danger",
    cancelText: "取消",
    onOk: async () => {
      try {
        await memoryDashboardApi.deprecateAtom(agentId, atom.id, {
          reason: reason || undefined,
        });
        message.success("已弃用，Octop 将不再使用这条记忆");
        onSuccess?.();
      } catch (e) {
        message.error(`操作失败：${(e as Error).message ?? e}`);
        throw e; // Keep the confirmation dialog open.
      }
    },
  });
}
