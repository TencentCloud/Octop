import { useTranslation } from "react-i18next";
import { isBridgeAgentId } from "../../../utils/remoteExpert";
import RemoteExpertHint from "../../Chat/components/RemoteExpertHint";
import styles from "../index.module.less";

interface EditExpertDrawerTitleProps {
  agent?: {
    agent_id?: string;
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
  if (remote && agent) {
    return (
      <span className={styles.editExpertTitle}>
        {t("experts.editExpert")}
        <RemoteExpertHint agent={agent} />
      </span>
    );
  }
  return t("experts.editExpert");
}
