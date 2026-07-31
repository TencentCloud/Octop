/**
 * MigrateMemory.tsx — memory migration dialog component.
 *
 * Features:
 *   1. Export current agent memory as an .hmpkg browser download.
 *   2. Import from .hmpkg with target host, conflict policy, and dry-run preview.
 *   3. Run doctor checks and display migration health results.
 */

import { useState } from "react";
import {
  Alert,
  Button,
  Dropdown,
  Form,
  Modal,
  Radio,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  CheckCircle,
  CloudDownload,
  CloudUpload,
  Download,
  Stethoscope,
  Upload as UploadIcon,
  XCircle,
} from "lucide-react";
import type { MenuProps } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useTranslation } from "react-i18next";

import memoryPortableApi, {
  type AdoptSummary,
  type DoctorCheck,
  type DoctorReport,
} from "../../../api/modules/memoryPortable";

const { Text, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ModalMode = "export" | "import" | "doctor" | null;

interface Props {
  agentId: string;
}

// ---------------------------------------------------------------------------
// Child component: doctor check result.
// ---------------------------------------------------------------------------

function DoctorCheckRow({ check }: { check: DoctorCheck }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        marginBottom: 6,
      }}
    >
      {check.passed ? (
        <CheckCircle size={14} style={{ color: "#52c41a", marginTop: 2 }} />
      ) : (
        <XCircle size={14} style={{ color: "#ff4d4f", marginTop: 2 }} />
      )}
      <div>
        <Text strong>{check.name}</Text>
        {check.message ? (
          <Text type="secondary" style={{ marginLeft: 8 }}>
            {check.message}
          </Text>
        ) : null}
        {!check.passed && check.hint ? (
          <div>
            <Text type="warning" style={{ fontSize: 12 }}>
              💡 {check.hint}
            </Text>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MigrateMemory({ agentId }: Props) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<ModalMode>(null);
  const [loading, setLoading] = useState(false);

  // Import form state.
  const [importFile, setImportFile] = useState<UploadFile | null>(null);
  const [targetHost, setTargetHost] = useState("openclaw");
  const [onConflict, setOnConflict] = useState<"skip" | "replace">("skip");
  const [hostRewrite, setHostRewrite] = useState<"keep" | "target">("keep");

  // Result state.
  const [adoptResult, setAdoptResult] = useState<AdoptSummary | null>(null);
  const [doctorResult, setDoctorResult] = useState<DoctorReport | null>(null);
  const [doctorFile, setDoctorFile] = useState<UploadFile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resetState = () => {
    setImportFile(null);
    setTargetHost("openclaw");
    setOnConflict("skip");
    setHostRewrite("keep");
    setAdoptResult(null);
    setDoctorResult(null);
    setDoctorFile(null);
    setError(null);
  };

  const openMode = (m: ModalMode) => {
    resetState();
    setMode(m);
  };

  const closeModal = () => {
    setMode(null);
    resetState();
  };

  // ---- Export ----
  const handleExport = async () => {
    setLoading(true);
    setError(null);
    try {
      await memoryPortableApi.packAndDownload(agentId);
      message.success(t("memory.migrate.exportSuccess", "记忆包已下载"));
      closeModal();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // ---- Import: dry-run first, then confirm execution ----
  const handleImport = async (actualDryRun: boolean) => {
    if (!importFile?.originFileObj) {
      message.warning(t("memory.migrate.selectFile", "请先选择 .hmpkg 文件"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await memoryPortableApi.adoptMemory(
        agentId,
        importFile.originFileObj,
        {
          targetHost,
          onConflict,
          hostRewrite,
          dryRun: actualDryRun,
        },
      );
      setAdoptResult(result);
      if (!actualDryRun) {
        message.success(
          t("memory.migrate.importSuccess", "导入完成，共写入 {{n}} 条", {
            n: result.applied,
          }),
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // ---- doctor ----
  const handleDoctor = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await memoryPortableApi.doctorMemory(agentId, {
        hostSpec: "agent",
        comparePkg: doctorFile?.originFileObj,
      });
      setDoctorResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // ---- Dropdown menu ----
  const menuItems: MenuProps["items"] = [
    {
      key: "export",
      icon: <UploadIcon size={14} />,
      label: t("memory.migrate.exportLabel", "导出到文件"),
      onClick: () => openMode("export"),
    },
    {
      key: "import",
      icon: <Download size={14} />,
      label: t("memory.migrate.importLabel", "从文件导入"),
      onClick: () => openMode("import"),
    },
    {
      key: "doctor",
      icon: <Stethoscope size={14} />,
      label: t("memory.migrate.doctorLabel", "验证迁移"),
      onClick: () => openMode("doctor"),
    },
  ];

  return (
    <>
      <Dropdown menu={{ items: menuItems }} trigger={["click"]}>
        <Button size="small" icon={<CloudUpload size={14} />}>
          {t("memory.migrate.buttonLabel", "迁移记忆")} ▾
        </Button>
      </Dropdown>

      {/* ---- Export dialog ---- */}
      <Modal
        open={mode === "export"}
        title={
          <Space>
            <CloudDownload size={14} />
            {t("memory.migrate.exportTitle", "导出记忆到文件")}
          </Space>
        }
        onCancel={closeModal}
        footer={[
          <Button key="cancel" onClick={closeModal}>
            {t("common.cancel", "取消")}
          </Button>,
          <Button
            key="export"
            type="primary"
            icon={<CloudDownload size={14} />}
            loading={loading}
            onClick={handleExport}
          >
            {t("memory.migrate.exportBtn", "打包并下载")}
          </Button>,
        ]}
      >
        <Paragraph>
          {t(
            "memory.migrate.exportDesc",
            "将当前 Octop 的全部记忆打包为 .hmpkg 文件并下载到本地。你可以在其他宿主（openclaw / hermes）上导入此文件继续使用。",
          )}
        </Paragraph>
        {error ? <Alert type="error" message={error} showIcon /> : null}
      </Modal>

      {/* ---- Import dialog ---- */}
      <Modal
        open={mode === "import"}
        title={
          <Space>
            <CloudUpload size={14} />
            {t("memory.migrate.importTitle", "从文件导入记忆")}
          </Space>
        }
        onCancel={closeModal}
        width={520}
        footer={
          adoptResult && !adoptResult.dry_run
            ? [
                <Button key="close" type="primary" onClick={closeModal}>
                  {t("common.close", "关闭")}
                </Button>,
              ]
            : adoptResult?.dry_run
            ? [
                <Button key="cancel" onClick={closeModal}>
                  {t("common.cancel", "取消")}
                </Button>,
                <Button
                  key="confirm"
                  type="primary"
                  loading={loading}
                  onClick={() => handleImport(false)}
                >
                  {t("memory.migrate.confirmImport", "确认执行")}
                </Button>,
              ]
            : [
                <Button key="cancel" onClick={closeModal}>
                  {t("common.cancel", "取消")}
                </Button>,
                <Button
                  key="preview"
                  loading={loading}
                  onClick={() => handleImport(true)}
                >
                  {t("memory.migrate.previewBtn", "预检（dry-run）")}
                </Button>,
                <Button
                  key="import"
                  type="primary"
                  loading={loading}
                  onClick={() => handleImport(false)}
                >
                  {t("memory.migrate.importBtn", "直接导入")}
                </Button>,
              ]
        }
      >
        <Spin spinning={loading}>
          {/* File selection */}
          {!adoptResult ? (
            <Form layout="vertical" style={{ marginTop: 8 }}>
              <Form.Item
                label={t("memory.migrate.selectFileLabel", "选择 .hmpkg 文件")}
              >
                <Upload
                  accept=".hmpkg"
                  maxCount={1}
                  beforeUpload={() => false}
                  fileList={importFile ? [importFile] : []}
                  onChange={({ fileList }) =>
                    setImportFile(fileList[0] ?? null)
                  }
                >
                  <Button icon={<Download size={14} />}>
                    {t("memory.migrate.chooseFile", "选择文件")}
                  </Button>
                </Upload>
              </Form.Item>

              <Form.Item
                label={t("memory.migrate.targetHostLabel", "目标宿主")}
              >
                <Select
                  value={targetHost}
                  onChange={setTargetHost}
                  options={[
                    { value: "openclaw", label: "openclaw" },
                    { value: "hermes", label: "hermes" },
                    { value: "agent", label: "octop（本机）" },
                  ]}
                />
              </Form.Item>

              <Form.Item label={t("memory.migrate.conflictLabel", "冲突策略")}>
                <Radio.Group
                  value={onConflict}
                  onChange={(e) => setOnConflict(e.target.value)}
                >
                  <Radio value="skip">
                    {t("memory.migrate.conflictSkip", "跳过（保留已有）")}
                  </Radio>
                  <Radio value="replace">
                    {t(
                      "memory.migrate.conflictReplace",
                      "覆盖（用新数据替换）",
                    )}
                  </Radio>
                </Radio.Group>
              </Form.Item>

              <Form.Item
                label={t("memory.migrate.hostRewriteLabel", "host 字段")}
              >
                <Radio.Group
                  value={hostRewrite}
                  onChange={(e) => setHostRewrite(e.target.value)}
                >
                  <Radio value="keep">
                    {t("memory.migrate.hostRewriteKeep", "保留原始 host")}
                  </Radio>
                  <Radio value="target">
                    {t("memory.migrate.hostRewriteTarget", "改写为目标宿主")}
                  </Radio>
                </Radio.Group>
              </Form.Item>
            </Form>
          ) : null}

          {/* Dry-run preview result */}
          {adoptResult?.dry_run ? (
            <div>
              <Alert
                type="info"
                showIcon
                message={t("memory.migrate.dryRunResult", "预检结果")}
                description={
                  <div>
                    <div>
                      {t("memory.migrate.willApply", "预计写入：{{n}} 条", {
                        n: adoptResult.applied,
                      })}
                    </div>
                    <div>
                      {t("memory.migrate.targetNs", "目标 namespace：{{ns}}", {
                        ns: adoptResult.target_namespace,
                      })}
                    </div>
                  </div>
                }
              />
              <Paragraph style={{ marginTop: 12 }}>
                {t(
                  "memory.migrate.confirmDesc",
                  "确认无误后点击「确认执行」正式导入。",
                )}
              </Paragraph>
            </div>
          ) : null}

          {/* Import completion result */}
          {adoptResult && !adoptResult.dry_run ? (
            <Alert
              type={adoptResult.already_adopted ? "warning" : "success"}
              showIcon
              message={
                adoptResult.already_adopted
                  ? t("memory.migrate.alreadyAdopted", "已迁移，跳过")
                  : t("memory.migrate.importDone", "导入完成")
              }
              description={
                adoptResult.already_adopted
                  ? t(
                      "memory.migrate.alreadyAdoptedAt",
                      "此包已于 {{at}} 导入过",
                      {
                        at: adoptResult.already_adopted_at ?? "",
                      },
                    )
                  : t(
                      "memory.migrate.importStats",
                      "写入 {{n}} 条，跳过 {{s}} 条",
                      {
                        n: adoptResult.applied,
                        s: adoptResult.skipped,
                      },
                    )
              }
            />
          ) : null}

          {error ? (
            <Alert
              type="error"
              message={error}
              showIcon
              style={{ marginTop: 8 }}
            />
          ) : null}
        </Spin>
      </Modal>

      {/* ---- Doctor dialog ---- */}
      <Modal
        open={mode === "doctor"}
        title={
          <Space>
            <Stethoscope size={16} />
            {t("memory.migrate.doctorTitle", "验证迁移健康状态")}
          </Space>
        }
        onCancel={closeModal}
        width={540}
        footer={
          doctorResult
            ? [
                <Button key="close" type="primary" onClick={closeModal}>
                  {t("common.close", "关闭")}
                </Button>,
              ]
            : [
                <Button key="cancel" onClick={closeModal}>
                  {t("common.cancel", "取消")}
                </Button>,
                <Button
                  key="run"
                  type="primary"
                  icon={<Stethoscope size={14} />}
                  loading={loading}
                  onClick={handleDoctor}
                >
                  {t("memory.migrate.runDoctor", "开始检查")}
                </Button>,
              ]
        }
      >
        <Spin spinning={loading}>
          {!doctorResult ? (
            <div>
              <Paragraph>
                {t(
                  "memory.migrate.doctorDesc",
                  "对当前 Octop 的记忆库执行健康检查，验证 schema、索引、外键完整性等。",
                )}
              </Paragraph>
              <Form layout="vertical">
                <Form.Item
                  label={t(
                    "memory.migrate.comparePkgLabel",
                    "可选：上传 .hmpkg 文件进行行数比对",
                  )}
                >
                  <Upload
                    accept=".hmpkg"
                    maxCount={1}
                    beforeUpload={() => false}
                    fileList={doctorFile ? [doctorFile] : []}
                    onChange={({ fileList }) =>
                      setDoctorFile(fileList[0] ?? null)
                    }
                  >
                    <Button icon={<Download size={14} />}>
                      {t("memory.migrate.chooseFile", "选择文件")}
                    </Button>
                  </Upload>
                </Form.Item>
              </Form>
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: 12 }}>
                {doctorResult.all_passed ? (
                  <Alert
                    type="success"
                    showIcon
                    message={t(
                      "memory.migrate.doctorAllPassed",
                      "全部检查通过 ✓",
                    )}
                  />
                ) : (
                  <Alert
                    type="error"
                    showIcon
                    message={t(
                      "memory.migrate.doctorFailed",
                      "部分检查未通过，请查看详情",
                    )}
                  />
                )}
              </div>
              {doctorResult.checks.map((c) => (
                <DoctorCheckRow key={c.name} check={c} />
              ))}
              {doctorResult.row_count_diff &&
              Object.keys(doctorResult.row_count_diff).length > 0 ? (
                <div style={{ marginTop: 12 }}>
                  <Text strong>
                    {t("memory.migrate.rowCountDiff", "行数差异：")}
                  </Text>
                  {Object.entries(doctorResult.row_count_diff).map(([k, v]) => (
                    <Tag
                      key={k}
                      color={v === 0 ? "green" : "orange"}
                      style={{ marginLeft: 4 }}
                    >
                      {k}: {v > 0 ? `+${v}` : v}
                    </Tag>
                  ))}
                </div>
              ) : null}
            </div>
          )}
          {error ? (
            <Alert
              type="error"
              message={error}
              showIcon
              style={{ marginTop: 8 }}
            />
          ) : null}
        </Spin>
      </Modal>
    </>
  );
}
