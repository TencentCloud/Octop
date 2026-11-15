import { useTranslation } from "react-i18next";
import BetaBadge from "../../../components/BetaBadge";
import { isBridgeAgentId } from "../../../utils/remoteExpert";
import RemoteExpertHint from "../../Chat/components/RemoteExpertHint";
import styles from "../index.module.less";

interface EditExpertDrawerTitleProps {
  agent?: {
    agent_id?: string;
    kind?: string | null;
    bridge?: boolean | null;
    bridge_connection_name?: string | null;
    bridge_connection_icon?: string | null;
  } | null;
}

/** Drawer title: “Edit Expert”, with peer icon + connection name on the right. */
export default function EditExpertDrawerTitle({
  agent,
}: EditExpertDrawerTitleProps) {
  const { t } = useTranslation();
  const remote = Boolean(agent?.bridge) || isBridgeAgentId(agent?.agent_id);
  const beta = agent?.kind === "managed" ? <BetaBadge /> : null;
  if (remote && agent) {
    return (
      <span className={styles.editExpertTitle}>
        {beta ? t("experts.managed.createTitle") : t("experts.editExpert")}
        {beta}
        <RemoteExpertHint agent={agent} />
      </span>
    );
  }
  if (beta) {
    return (
      <span className={styles.titleWithBeta}>
        {t("experts.managed.createTitle")}
        {beta}
      </span>
    );
  }
  return t("experts.editExpert");
}
