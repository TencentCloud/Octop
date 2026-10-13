import { Button } from "antd";
import type { TFunction } from "i18next";
import {
  octopThreadsApi,
  type ThreadDeleteResult,
} from "../../../api/modules/octopThreads";
import { apiErrorMessage } from "../../../utils/apiError";
import { message as antMessage } from "../../../utils/antdMessage";
import { modal } from "../../../utils/antdModal";

const MOBILE_BREAKPOINT = 768;

function deleteResultText(
  t: TFunction,
  compact: boolean,
  result: ThreadDeleteResult | undefined,
): string {
  if (compact && result?.compacted) return t("chat.deleteSessionCompacted");
  if (compact) return t("chat.deleteSessionCompactLater");
  return t("chat.deleteSessionLater");
}

/** Delete one conversation. ``compact`` rebuilds the database before returning. */
export async function deleteConversation(
  agentId: string,
  threadId: string,
  compact: boolean,
  t: TFunction,
): Promise<boolean> {
  const closeLoading = compact
    ? antMessage.loading(t("chat.deleteSessionCompacting"), 0)
    : undefined;
  try {
    const result = await octopThreadsApi.delete(agentId, threadId, compact);
    if (typeof closeLoading === "function") closeLoading();
    antMessage.success(deleteResultText(t, compact, result));
    return true;
  } catch (error) {
    if (typeof closeLoading === "function") closeLoading();
    antMessage.error(apiErrorMessage(error, t("sessions.deleteFailed"), t));
    return false;
  }
}

/**
 * Confirm deleting a conversation.
 *
 * Delete-and-compact shrinks the database file now and pauses the expert.
 * Delete-only leaves that to idle maintenance.
 */
export function confirmDeleteConversation(
  t: TFunction,
  onConfirm: (compact: boolean) => void | Promise<void>,
): void {
  const mobile =
    typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT;
  let chosen = false;
  const handle: { destroy?: () => void } = {};
  const choose = (compact: boolean) => {
    if (chosen) return;
    chosen = true;
    handle.destroy?.();
    void onConfirm(compact);
  };
  const buttonStyle = mobile ? { width: "100%" } : undefined;
  const opened = modal.confirm({
    title: t("chat.deleteSessionTitle"),
    icon: null,
    width: mobile ? Math.min(400, Math.max(280, window.innerWidth - 32)) : 480,
    content: (
      <div>
        <p style={{ marginBottom: 8 }}>{t("chat.deleteSessionBody")}</p>
        <p style={{ marginBottom: 8 }}>
          {t("chat.deleteSessionAndCompactHint")}
        </p>
        <p style={{ margin: 0 }}>{t("chat.deleteSessionOnlyHint")}</p>
      </div>
    ),
    footer: (
      <div
        style={{
          display: "flex",
          flexDirection: mobile ? "column-reverse" : "row",
          justifyContent: "flex-end",
          gap: 8,
          marginTop: 16,
        }}
      >
        <Button style={buttonStyle} onClick={() => handle.destroy?.()}>
          {t("common.cancel")}
        </Button>
        <Button style={buttonStyle} onClick={() => choose(false)}>
          {t("chat.deleteSessionOnly")}
        </Button>
        <Button
          danger
          type="primary"
          style={buttonStyle}
          onClick={() => choose(true)}
        >
          {t("chat.deleteSessionAndCompact")}
        </Button>
      </div>
    ),
  });
  handle.destroy = opened.destroy;
}
