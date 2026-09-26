/**
 * ExpertVisibilityMenu — admin-only control to hide the built-in expert
 * library and/or the SkillHub expert market from non-admin users (#719).
 *
 * Backed by GET/PUT /api/settings/expert-visibility. Hidden from users who are
 * not admins, so it only renders inside the Experts page tab bar for admins.
 */
import { useState } from "react";
import { Button, Popover, Switch } from "antd";
import { Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { useExpertVisibility } from "../../../hooks/useExpertVisibility";
import styles from "../index.module.less";

export default function ExpertVisibilityMenu() {
  const { t } = useTranslation();
  const { hideBuiltinExperts, hideMarket, save } = useExpertVisibility();
  const [saving, setSaving] = useState(false);

  const update = async (patch: {
    hideBuiltinExperts?: boolean;
    hideMarket?: boolean;
  }) => {
    setSaving(true);
    try {
      await save({
        hide_builtin_experts: patch.hideBuiltinExperts ?? hideBuiltinExperts,
        hide_market: patch.hideMarket ?? hideMarket,
      });
      message.success(t("experts.visibility.saved"));
    } catch {
      message.error(t("experts.visibility.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const content = (
    <div className={styles.visibilityMenu}>
      <div className={styles.visibilityMenuHint}>
        {t("experts.visibility.hint")}
      </div>
      <label className={styles.visibilityMenuItem}>
        <span>{t("experts.visibility.hideBuiltin")}</span>
        <Switch
          size="small"
          checked={hideBuiltinExperts}
          loading={saving}
          onChange={(checked) => void update({ hideBuiltinExperts: checked })}
        />
      </label>
      <label className={styles.visibilityMenuItem}>
        <span>{t("experts.visibility.hideMarket")}</span>
        <Switch
          size="small"
          checked={hideMarket}
          loading={saving}
          onChange={(checked) => void update({ hideMarket: checked })}
        />
      </label>
    </div>
  );

  return (
    <Popover content={content} trigger="click" placement="bottomRight">
      <Button size="small" type="text" icon={<Settings2 size={14} />}>
        {t("experts.visibility.trigger")}
      </Button>
    </Popover>
  );
}
