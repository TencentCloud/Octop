import { useState, type AriaAttributes } from "react";
import { Alert } from "antd";
import { useTranslation } from "react-i18next";
import ExpertConfigDrawer from "./expertDrawer/ExpertConfigDrawer";
import TeamMemberPicker, {
  selectedRosterIds,
  type TeamMemberOption,
} from "./TeamMemberPicker";

interface TeamMembersConfigProps extends AriaAttributes {
  id?: string;
  value?: string[];
  onChange?: (value: string[]) => void;
  experts: TeamMemberOption[];
  disabled: boolean;
}

export default function TeamMembersConfig({
  value,
  onChange,
  experts,
  disabled,
  ...triggerProps
}: TeamMembersConfigProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string[]>();
  const selected = selectedRosterIds(value, experts);
  const draftIds = selectedRosterIds(draft, experts);
  const canApply = draftIds.length >= 2;

  return (
    <ExpertConfigDrawer
      {...triggerProps}
      title={t("experts.teams.members")}
      summary={t("experts.teams.membersSelected", { count: selected.length })}
      open={draft !== undefined}
      disabled={disabled}
      applyDisabled={!canApply}
      onOpen={() => setDraft(value ?? [])}
      onClose={() => setDraft(undefined)}
      onApply={() => {
        if (canApply) onChange?.(draftIds);
        setDraft(undefined);
      }}
    >
      {draft !== undefined && (
        <>
          <Alert
            type="info"
            showIcon
            message={t("experts.teams.membersHint")}
            style={{ marginBottom: 16 }}
          />
          <TeamMemberPicker
            value={draft}
            onChange={setDraft}
            experts={experts}
          />
        </>
      )}
    </ExpertConfigDrawer>
  );
}
