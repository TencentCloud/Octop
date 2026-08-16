import { useEffect, useRef, useState } from "react";
import { Button, Checkbox, Modal, Segmented } from "antd";
import { Upload as UploadIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";
import { parseSkillZip, type ParsedZipSkill } from "./parseSkillZip";

const DEFAULT_SKILL_URL_PREFIXES = [
  "https://skills.sh/",
  "https://clawhub.ai/",
  "https://skillsmp.com/",
  "https://github.com/",
] as const;

export type ZipImportSummary = {
  imported: number;
  skipped: number;
  failed: number;
};

export interface SkillImportModalProps {
  open: boolean;
  importing: boolean;
  onClose: () => void;
  /** Return true on success so the modal can clear/close. */
  onImportUrl: (
    bundleUrl: string,
    options: { overwrite: boolean },
  ) => Promise<boolean>;
  onImportZip: (
    skills: ParsedZipSkill[],
    options: { overwrite: boolean },
  ) => Promise<ZipImportSummary | false>;
  urlPrefixes?: readonly string[];
}

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function SkillImportModal({
  open,
  importing,
  onClose,
  onImportUrl,
  onImportZip,
  urlPrefixes = DEFAULT_SKILL_URL_PREFIXES,
}: SkillImportModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"url" | "zip">("url");
  const [importUrl, setImportUrl] = useState("");
  const [importUrlError, setImportUrlError] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipError, setZipError] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setMode("url");
      setImportUrl("");
      setImportUrlError("");
      setZipFile(null);
      setZipError("");
      setOverwrite(false);
      setParsing(false);
      setIsDragging(false);
    }
  }, [open]);

  const handleFileSelect = (file: File | null) => {
    if (!file) {
      setZipFile(null);
      return;
    }
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setZipFile(null);
      setZipError(t("skills.zipOnly"));
      return;
    }
    setZipError("");
    setZipFile(file);
  };

  const handleUrlChange = (value: string) => {
    setImportUrl(value);
    const trimmed = value.trim();
    if (!trimmed) {
      setImportUrlError("");
      return;
    }
    if (!isHttpUrl(trimmed)) {
      setImportUrlError(t("skills.invalidSkillUrlSource"));
      return;
    }
    const ok = urlPrefixes.some((prefix) => trimmed.startsWith(prefix));
    setImportUrlError(ok ? "" : t("skills.invalidSkillUrlSource"));
  };

  const handleConfirm = async () => {
    if (importing || parsing) return;

    if (mode === "url") {
      const trimmed = importUrl.trim();
      if (!trimmed || importUrlError) return;
      const ok = await onImportUrl(trimmed, { overwrite });
      if (ok) onClose();
      return;
    }

    if (!zipFile) {
      setZipError(t("skills.zipRequired"));
      return;
    }

    setParsing(true);
    setZipError("");
    try {
      const skills = await parseSkillZip(zipFile);
      const summary = await onImportZip(skills, { overwrite });
      if (summary) onClose();
    } catch (error) {
      const code = error instanceof Error ? error.message : "";
      if (code === "ZIP_TOO_LARGE") {
        setZipError(t("skills.zipTooLarge"));
      } else if (code === "ZIP_EMPTY") {
        setZipError(t("skills.zipEmpty"));
      } else if (code === "ZIP_NO_SKILLS") {
        setZipError(t("skills.zipNoSkills"));
      } else {
        setZipError(t("skills.zipParseFailed"));
      }
    } finally {
      setParsing(false);
    }
  };

  const busy = importing || parsing;
  const confirmDisabled =
    busy ||
    (mode === "url"
      ? !importUrl.trim() || !!importUrlError
      : !zipFile || !!zipError);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (busy) return;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (busy) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  return (
    <Modal
      title={t("skills.importSkills")}
      open={open}
      onCancel={() => {
        if (!busy) onClose();
      }}
      maskClosable={!busy}
      closable={!busy}
      keyboard={!busy}
      footer={
        <div style={{ textAlign: "right" }}>
          <Button onClick={onClose} disabled={busy} style={{ marginRight: 8 }}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            onClick={() => void handleConfirm()}
            loading={busy}
            disabled={confirmDisabled}
          >
            {t("skills.importSkills")}
          </Button>
        </div>
      }
      width={760}
    >
      <Segmented
        block
        value={mode}
        disabled={busy}
        onChange={(value) => setMode(value === "zip" ? "zip" : "url")}
        options={[
          { label: t("skills.importFromUrl"), value: "url" },
          { label: t("skills.importFromZip"), value: "zip" },
        ]}
        style={{ marginBottom: 16 }}
      />

      {mode === "url" ? (
        <>
          <div className={styles.importHintBlock}>
            <p className={styles.importHintTitle}>
              {t("skills.supportedSkillUrlSources")}
            </p>
            <div className={styles.importHintSources}>
              {urlPrefixes.map((prefix) => (
                <code key={prefix} className={styles.importHintCode}>
                  {prefix}
                </code>
              ))}
            </div>
            <p className={styles.importHintTitle} style={{ marginTop: 10 }}>
              {t("skills.urlExamples")}
            </p>
            <div className={styles.importHintExamples}>
              <code className={styles.importHintCode}>
                https://skills.sh/vercel-labs/skills/find-skills
              </code>
              <code className={styles.importHintCode}>
                https://github.com/anthropics/skills/tree/main/skills/skill-creator
              </code>
            </div>
          </div>

          <input
            className={styles.importUrlInput}
            value={importUrl}
            onChange={(e) => handleUrlChange(e.target.value)}
            placeholder={t("skills.enterSkillUrl")}
            disabled={busy}
          />
          {importUrlError ? (
            <div className={styles.importUrlError}>{importUrlError}</div>
          ) : null}
        </>
      ) : (
        <>
          <div className={styles.importHintBlock}>
            <p className={styles.importHintTitle}>{t("skills.zipHintTitle")}</p>
            <div className={styles.importHintExamples}>
              <code className={styles.importHintCode}>skill-a/SKILL.md</code>
              <code className={styles.importHintCode}>skill-b/SKILL.md</code>
            </div>
            <p className={styles.importHintTitle} style={{ marginTop: 10 }}>
              {t("skills.zipHintDetail")}
            </p>
          </div>

          <div
            className={`${styles.zipDragDrop} ${isDragging ? styles.zipDragDropActive : ""} ${zipFile ? styles.zipDragDropHasFile : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => !busy && fileInputRef.current?.click()}
          >
            <div className={styles.zipDragDropIcon}>
              <svg viewBox="0 0 24 24" width="48" height="48" fill="none">
                <path d="M20 17V19C20 20.1046 19.1046 21 18 21H6C4.89543 21 4 20.1046 4 19V17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12 12V3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M7 7L12 2L17 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div className={styles.zipDragDropText}>
              {zipFile ? t("skills.zipSelected", { name: zipFile.name }) : t("skills.zipDragDropHint")}
            </div>
            {zipFile ? (
              <Button
                type="link"
                disabled={busy}
                onClick={(e) => {
                  e.stopPropagation();
                  setZipFile(null);
                  setZipError("");
                }}
              >
                {t("skills.removeZip")}
              </Button>
            ) : null}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,application/zip"
            style={{ display: "none" }}
            disabled={busy}
            onChange={(event) => {
              const next = event.target.files?.[0] ?? null;
              event.target.value = "";
              handleFileSelect(next);
            }}
          />

          <div className={styles.zipPickerRow}>
            <Button
              icon={<UploadIcon size={14} />}
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              {t("skills.chooseZip")}
            </Button>
            <span className={styles.zipFileName}>
              {zipFile ? zipFile.name : t("skills.noZipSelected")}
            </span>
            {zipFile ? (
              <Button
                type="link"
                disabled={busy}
                onClick={() => {
                  setZipFile(null);
                  setZipError("");
                }}
              >
                {t("skills.removeZip")}
              </Button>
            ) : null}
          </div>

          {zipError ? (
            <div className={styles.importUrlError}>{zipError}</div>
          ) : null}
        </>
      )}

      <div className={styles.importOverwriteRow}>
        <Checkbox
          checked={overwrite}
          disabled={busy}
          onChange={(event) => setOverwrite(event.target.checked)}
        >
          {t("skills.overwriteExisting")}
        </Checkbox>
      </div>

      {busy ? (
        <div className={styles.importLoadingText}>{t("common.loading")}</div>
      ) : null}
    </Modal>
  );
}
