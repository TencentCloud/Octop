/**
 * editAtom — shared confirmation flow for replacing one memory's assertion.
 */
import { Input, Modal, Typography } from "antd";
import { message } from "@/utils/antdMessage";
import i18n from "@/i18n";

import {
  memoryDashboardApi,
  type AtomItem,
} from "../../../../api/modules/memoryDashboard";

export function confirmEditAtom({
  agentId,
  atom,
  onSuccess,
}: {
  agentId: string;
  atom: AtomItem;
  onSuccess?: (next: AtomItem) => void;
}) {
  let assertion = atom.assertion;
  Modal.confirm({
    title: i18n.t("memory.edit.title"),
    width: 520,
    content: (
      <div>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {i18n.t("memory.edit.description")}
        </Typography.Paragraph>
        <Input.TextArea
          defaultValue={atom.assertion}
          rows={4}
          onChange={(e) => {
            assertion = e.target.value;
          }}
        />
      </div>
    ),
    okText: i18n.t("memory.edit.ok"),
    cancelText: i18n.t("common.cancel"),
    onOk: async () => {
      const text = assertion.trim();
      if (!text) {
        message.error(i18n.t("memory.edit.empty"));
        throw new Error("empty assertion");
      }
      try {
        const r = await memoryDashboardApi.replaceAtom(agentId, atom.id, {
          assertion: text,
        });
        message.success(i18n.t("memory.edit.success"));
        onSuccess?.(r.atom);
      } catch (e) {
        message.error(
          i18n.t("memory.edit.failed", {
            message: (e as Error).message ?? e,
          }),
        );
        throw e;
      }
    },
  });
}
