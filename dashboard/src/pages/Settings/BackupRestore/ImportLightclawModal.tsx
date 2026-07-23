import { useState } from "react";
import {
  Alert,
  Button,
  Modal,
  Progress,
  Typography,
  Upload,
  message,
} from "antd";
import { PackageOpen, UploadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  migrationApi,
  type MigrationImportResult,
} from "../../../api/modules/migration";
import styles from "./ImportLightclawModal.module.less";

const { Text, Paragraph } = Typography;

interface ImportLightclawModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (result: MigrationImportResult) => void;
}

type ImportState = "idle" | "uploading" | "done" | "error";

export default function ImportLightclawModal({
  open,
  onClose,
  onSuccess,
}: ImportLightclawModalProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<ImportState>("idle");
  const [percent, setPercent] = useState(0);
  const [result, setResult] = useState<MigrationImportResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const handleClose = () => {
    if (state === "uploading") return;
    setState("idle");
    setPercent(0);
    setResult(null);
    setErrorMsg("");
    onClose();
  };

  const handleFile = async (file: File) => {
    setState("uploading");
    setPercent(0);
    setResult(null);
    setErrorMsg("");
    try {
      const res = await migrationApi.importLightclaw(file, (p) =>
        setPercent(p),
      );
      setResult(res);
      setState("done");
      message.success(
        t("migration.importSuccess", "LightClaw 数据导入成功！"),
      );
      onSuccess?.(res);
    } catch (e) {
      setState("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
      message.error(t("migration.importFailed", "导入失败"));
    }
  };

  return (
    <Modal
      title={
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <PackageOpen size={18} />
          {t("migration.importTitle", "从 LightClaw 导入")}
        </span>
      }
      open={open}
      onCancel={handleClose}
      footer={
        state === "done" ? (
          <Button type="primary" onClick={() => window.location.reload()}>
            {t("migration.reloadPage", "刷新页面")}
          </Button>
        ) : state === "error" ? (
          <Button type="primary" onClick={handleClose}>
            {t("common.close", "关闭")}
          </Button>
        ) : null
      }
      width={560}
      maskClosable={state !== "uploading"}
      closable={state !== "uploading"}
    >
      {state === "idle" && (
        <div className={styles.idleContent}>
          <Paragraph className={styles.desc}>
            {t(
              "migration.importDesc",
              "上传由 LightClaw「导出到 Octop」功能生成的迁移文件（.zip）。将创建新 Agent 并迁移以下内容：",
            )}
          </Paragraph>
          <ul className={styles.featureList}>
            {[
              t("migration.feature.workspace", "身份记忆文件（SOUL.md、USER.md 等）"),
              t("migration.feature.skills", "已启用的技能（skills/）"),
              t("migration.feature.sessions", "对话历史记录"),
              t("migration.feature.uploads", "上传附件"),
              t("migration.feature.cron", "定时任务"),
            ].map((item) => (
              <li key={item}>✓ {item}</li>
            ))}
          </ul>
          <Upload
            accept=".zip,application/zip,application/x-zip-compressed"
            showUploadList={false}
            beforeUpload={(file) => {
              void handleFile(file);
              return false;
            }}
          >
            <Button
              type="primary"
              icon={<UploadCloud size={16} />}
              size="large"
              className={styles.uploadButton}
            >
              {t("migration.selectFile", "选择迁移文件")}
            </Button>
          </Upload>
        </div>
      )}

      {state === "uploading" && (
        <div className={styles.progressContent}>
          <Paragraph>
            {t("migration.importing", "正在导入，请稍候...")}
          </Paragraph>
          <Progress percent={percent} status="active" />
        </div>
      )}

      {state === "done" && result && (
        <div className={styles.resultContent}>
          <Alert
            type="success"
            showIcon
            message={t("migration.importSuccess", "导入成功！")}
            description={t(
              "migration.agentCreated",
              "已创建新 Agent，ID：{{id}}",
              { id: result.agent_id },
            )}
            className={styles.resultAlert}
          />
          <div className={styles.stats}>
            <StatRow
              label={t("migration.stat.identityFiles", "身份记忆文件")}
              value={result.identity_files_written.length}
            />
            <StatRow
              label={t("migration.stat.skills", "技能")}
              value={result.skills_imported}
            />
            <StatRow
              label={t("migration.stat.workspace", "其他 Workspace 文件")}
              value={
                result.workspace_files_written -
                result.identity_files_written.length
              }
              skipped={result.workspace_files_skipped}
            />
            <StatRow
              label={t("migration.stat.uploads", "上传附件")}
              value={result.uploads_written}
              skipped={result.uploads_skipped}
            />
            <StatRow
              label={t("migration.stat.sessions", "对话记录")}
              value={result.sessions_imported}
              skipped={result.sessions_skipped}
            />
            <StatRow
              label={t("migration.stat.cron", "定时任务")}
              value={result.cron_jobs_imported}
              skipped={result.cron_jobs_skipped}
            />
          </div>
          {result.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              className={styles.envAlert}
              message={t("migration.warnings", "导入警告")}
              description={
                <ul className={styles.warnList}>
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}

        </div>
      )}

      {state === "error" && (
        <Alert
          type="error"
          showIcon
          message={t("migration.importFailed", "导入失败")}
          description={errorMsg}
        />
      )}
    </Modal>
  );
}

function StatRow({
  label,
  value,
  skipped,
}: {
  label: string;
  value: number;
  skipped?: number;
}) {
  return (
    <div className={styles.statRow}>
      <Text type="secondary">{label}</Text>
      <span>
        <Text strong>{value}</Text>
        {skipped != null && skipped > 0 && (
          <Text type="secondary" style={{ marginLeft: 4, fontSize: 12 }}>
            （跳过 {skipped}）
          </Text>
        )}
      </span>
    </div>
  );
}
