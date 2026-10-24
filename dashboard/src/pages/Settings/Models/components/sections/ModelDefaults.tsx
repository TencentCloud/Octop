import { useState } from "react";
import { Alert, Button, Modal, Select } from "antd";
import { useTranslation } from "react-i18next";
import { providerApi } from "../../../../../api/modules/provider";
import { useCurrentUser } from "../../../../../hooks/useCurrentUser";
import { message } from "../../../../../utils/antdMessage";
import {
  modelOptionLabel,
  modelOptionValue,
} from "../../../../../utils/modelOptions";
import { userCan } from "../../../../../utils/permissions";
import type { ResolvedModel, UseProvidersResult } from "../../useProviders";
import styles from "../../index.module.less";

interface ModelDefaultsProps {
  globalActiveModel: UseProvidersResult["globalActiveModel"];
  preferredModel: string;
  resolvedModels: ResolvedModel[];
  onSaved: () => void | Promise<void>;
}

export function ModelDefaults({
  globalActiveModel,
  preferredModel,
  resolvedModels,
  onSaved,
}: ModelDefaultsProps) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const canManageGlobalModel = userCan(user, "providers");
  const [editing, setEditing] = useState(false);
  const [selectedRef, setSelectedRef] = useState<string>();
  const [saving, setSaving] = useState(false);
  const globalRef =
    globalActiveModel.provider_name && globalActiveModel.model
      ? modelOptionValue(globalActiveModel)
      : "";
  const selectedModel = resolvedModels.find(
    (model) => modelOptionValue(model) === selectedRef,
  );

  const labelFor = (ref: string) => {
    const model = resolvedModels.find((item) => modelOptionValue(item) === ref);
    return model ? modelOptionLabel(model) : ref;
  };

  const saveGlobalModel = async () => {
    if (!canManageGlobalModel || !selectedModel || selectedRef === globalRef)
      return;
    setSaving(true);
    try {
      await providerApi.setActiveModel({
        provider_name: selectedModel.provider_name,
        model: selectedModel.model,
      });
      await onSaved();
      setEditing(false);
      message.success(
        t("models.globalModelSet", { model: modelOptionLabel(selectedModel) }),
      );
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={`${styles.poolSection} ${styles.modelDefaults}`}>
      <div className={styles.modelDefaultsHeader}>
        <div>
          <h3 className={styles.slotTitle}>{t("models.globalActiveModel")}</h3>
          <div className={styles.modelDefaultValue}>
            {labelFor(globalRef) || t("models.globalModelNotSet")}
          </div>
          <p className={styles.modelDefaultHelp}>
            {t("models.globalModelHelp")}
          </p>
        </div>
        {canManageGlobalModel && (
          <Button
            disabled={resolvedModels.length === 0}
            onClick={() => {
              setSelectedRef(globalRef || undefined);
              setEditing(true);
            }}
          >
            {t("models.changeGlobalModel")}
          </Button>
        )}
      </div>
      <p className={styles.personalModelDefault}>
        <strong>{t("models.personalChatModel")}: </strong>
        {preferredModel
          ? labelFor(preferredModel)
          : t("models.followsGlobalModel")}
      </p>
      {globalRef && preferredModel && preferredModel !== globalRef && (
        <Alert
          type="warning"
          showIcon
          message={t("models.chatModelOverrideWarning")}
        />
      )}
      {canManageGlobalModel && (
        <Modal
          title={t("models.changeGlobalModel")}
          open={editing}
          onCancel={() => setEditing(false)}
          onOk={() => void saveGlobalModel()}
          confirmLoading={saving}
          okText={t("common.save")}
          okButtonProps={{
            disabled: !selectedModel || selectedRef === globalRef,
          }}
          destroyOnHidden
        >
          <p>{t("models.globalModelHelp")}</p>
          <Select
            aria-label={t("models.globalActiveModel")}
            style={{ width: "100%" }}
            showSearch
            optionFilterProp="label"
            placeholder={t("models.selectGlobalModel")}
            value={selectedRef}
            onChange={setSelectedRef}
            options={resolvedModels.map((model) => ({
              value: modelOptionValue(model),
              label: modelOptionLabel(model),
            }))}
          />
        </Modal>
      )}
    </section>
  );
}
