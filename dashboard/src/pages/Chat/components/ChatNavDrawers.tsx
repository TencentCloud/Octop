import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { request } from "../../../api/request";
import { useAgent } from "../../../context/AgentContext";
import BridgeSettingsPanel from "../../Settings/AdvancedSettings/BridgeSettings";
import CreateFromExpertDrawer, {
  type CreateFromTemplateSource,
} from "../../Experts/components/CreateFromExpertDrawer";
import type { ExpertSummary } from "../../Experts/components/ExpertCard";
import TeamDrawer from "../../Experts/components/TeamDrawer";
import { apiErrorMessage } from "../../../utils/apiError";
import { isOwnedExpert } from "../../../utils/sharedExpert";
import type { ChatNavScope } from "../utils/chatNavScope";

/** Right-hand create drawers for the chat nav. No route change. */
export function useChatNavDrawers() {
  const [scope, setScope] = useState<ChatNavScope | null>(null);
  const open = useCallback((next: ChatNavScope) => setScope(next), []);
  const close = useCallback(() => setScope(null), []);
  const drawers = <ChatNavDrawers scope={scope} onClose={close} />;
  return { open, drawers };
}

function ChatNavDrawers({
  scope,
  onClose,
}: {
  scope: ChatNavScope | null;
  onClose: () => void;
}) {
  const { agents, refresh } = useAgent();
  const members = useMemo(
    () =>
      agents.filter(
        (item) =>
          item.kind !== "team" &&
          !item.bridge &&
          (isOwnedExpert(item) || item.is_shared),
      ),
    [agents],
  );
  return (
    <>
      <ExpertCreateDrawer
        open={scope === "experts"}
        onClose={onClose}
        onCreated={() => {
          onClose();
          void refresh({ silent: true, force: true });
        }}
      />
      {scope === "teams" ? (
        <TeamDrawer
          open
          mode="create"
          experts={members}
          onClose={onClose}
          onSaved={() => {
            onClose();
            void refresh({ silent: true, force: true });
          }}
        />
      ) : null}
      {scope === "cloud" ? (
        <BridgeSettingsPanel createOnly onDismiss={onClose} />
      ) : null}
    </>
  );
}

function ExpertCreateDrawer({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (agentId: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const lang: "zh" | "en" = i18n.language?.startsWith("zh") ? "zh" : "en";
  const [source, setSource] = useState<CreateFromTemplateSource | null>(null);

  useEffect(() => {
    if (!open) {
      setSource(null);
      return;
    }
    let cancelled = false;
    void request<ExpertSummary>("/experts/default")
      .then((expert) => {
        if (!cancelled) setSource({ kind: "builtin", expert });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        message.error(apiErrorMessage(err, t("experts.createFailed"), t));
        onClose();
      });
    return () => {
      cancelled = true;
    };
  }, [onClose, open, t]);

  return (
    <CreateFromExpertDrawer
      open={open && source != null}
      source={source}
      lang={lang}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}
