import { useEffect, useState } from "react";
import { Alert, Checkbox, Empty, Modal, Select, Spin } from "antd";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";
import { skillPackagesApi } from "../../../../api/modules/skillPackages";
import type { SkillPackage } from "../../../../api/types/skillPackage";
import { showApiError } from "../../../../utils/showApiToast";
import type { SkillDetail } from "../useSkills";
import styles from "../index.module.less";

interface PushSkillToPackageModalProps {
  open: boolean;
  agentId: string;
  skill: SkillDetail | null;
  onClose: () => void;
}

export function PushSkillToPackageModal({
  open,
  agentId,
  skill,
  onClose,
}: PushSkillToPackageModalProps) {
  const { t } = useTranslation();
  const [packages, setPackages] = useState<SkillPackage[]>([]);
  const [packageId, setPackageId] = useState<string>();
  const [overwrite, setOverwrite] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pushing, setPushing] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setPackages([]);
    setPackageId(undefined);
    setOverwrite(false);
    skillPackagesApi
      .listWritable()
      .then((rows) => {
        if (!cancelled) setPackages(rows);
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, t("skills.packagesLoadFailed"), t);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, t]);

  const handlePush = async () => {
    if (!skill || !packageId) return;
    setPushing(true);
    try {
      await skillPackagesApi.pushFromWorkspace(agentId, skill.slug, {
        package_id: packageId,
        overwrite,
      });
      message.success(t("skills.pushSkillSuccess"));
      onClose();
    } catch (error) {
      showApiError(error, t("skills.pushSkillFailed"), t);
    } finally {
      setPushing(false);
    }
  };

  return (
    <Modal
      title={t("skills.pushSkillTitle", { name: skill?.name ?? "" })}
      open={open}
      onCancel={onClose}
      onOk={() => void handlePush()}
      okText={t("skills.pushToSkillPackage")}
      confirmLoading={pushing}
      okButtonProps={{ disabled: loading || !packageId }}
      destroyOnHidden
    >
      <Alert
        type="info"
        showIcon
        className={styles.skillTransferAlert}
        message={t("skills.pushSnapshotWarning")}
      />
      {loading ? (
        <Spin className={styles.skillPackagesLoading} />
      ) : packages.length === 0 ? (
        <Empty description={t("skills.noWritableSkillPackages")} />
      ) : (
        <Select
          value={packageId}
          onChange={setPackageId}
          placeholder={t("skills.selectWritableSkillPackage")}
          className={styles.skillTransferSelect}
          options={packages.map((pack) => ({
            value: pack.id,
            label: pack.name,
          }))}
        />
      )}
      {!loading && packages.length > 0 ? (
        <Checkbox
          checked={overwrite}
          onChange={(event) => setOverwrite(event.target.checked)}
        >
          {t("skills.overwriteExisting")}
        </Checkbox>
      ) : null}
    </Modal>
  );
}
