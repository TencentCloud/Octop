/**
 * deprecateAtom — shared confirmation flow for manually deprecating one memory.
 *
 * Reuses the same confirm dialog, optional reason input, deprecateAtom call,
 * and toast behavior across tree and list drawers.
 */
import { Input, Typography } from "antd";
import { message } from "@/utils/antdMessage";
import { modal } from "@/utils/antdModal";
import i18n from "@/i18n";

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
  modal.confirm({
    title: i18n.t("memory.deprecate.title"),
    content: (
      <div>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {i18n.t("memory.deprecate.description")}
        </Typography.Paragraph>
        <Input.TextArea
          placeholder={i18n.t("memory.deprecate.reasonPlaceholder")}
          rows={3}
          onChange={(e) => {
            reason = e.target.value;
          }}
        />
      </div>
    ),
    okText: i18n.t("memory.deprecate.ok"),
    okType: "danger",
    cancelText: i18n.t("common.cancel"),
    onOk: async () => {
      try {
        await memoryDashboardApi.deprecateAtom(agentId, atom.id, {
          reason: reason || undefined,
        });
        message.success(i18n.t("memory.deprecate.success"));
        onSuccess?.();
      } catch (e) {
        message.error(
          i18n.t("memory.deprecate.failed", {
            message: (e as Error).message ?? e,
          }),
        );
        throw e; // Keep the confirmation dialog open.
      }
    },
  });
}
