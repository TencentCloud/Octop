import { useEffect, useMemo, useState } from "react";
import { Form, Input, Select } from "antd";
import RootDirSelect from "./RootDirSelect";
import { MinusCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  BUILTIN_BACKENDS,
  DEFAULT_BACKEND,
  fetchFilesystemDefaults,
  type BackendOption,
  type FilesystemDefaults,
  type PathMapping,
  builtinDesc,
  builtinLabel,
  isValidCompositePath,
} from "./agentBackendForm";
import { HOST_FS_ROOT } from "./rootDirTree";
import styles from "../index.module.less";

interface AgentBackendFieldsProps {
  backends: BackendOption[];
  backendsLoading: boolean;
  backendChoice: string;
  pathMappings: PathMapping[];
  /** ``create`` fills empty root_dir with home; ``edit`` leaves existing values. */
  rootDirMode?: "create" | "edit";
  onAddPathMapping: () => void;
  onRemovePathMapping: (index: number) => void;
  onUpdatePathMapping: (
    index: number,
    field: keyof PathMapping,
    value: string,
  ) => void;
}

export default function AgentBackendFields({
  backends,
  backendsLoading,
  backendChoice,
  pathMappings,
  rootDirMode = "create",
  onAddPathMapping,
  onRemovePathMapping,
  onUpdatePathMapping,
}: AgentBackendFieldsProps) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const [fsDefaults, setFsDefaults] = useState<FilesystemDefaults | null>(null);
  const watchedRootDir = Form.useWatch("root_dir", form) as string | undefined;

  useEffect(() => {
    let cancelled = false;
    fetchFilesystemDefaults()
      .then((defaults) => {
        if (!cancelled) setFsDefaults(defaults);
      })
      .catch(() => {
        if (!cancelled) setFsDefaults(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!fsDefaults || rootDirMode !== "create") return;
    const current = watchedRootDir;
    if (!current) {
      form.setFieldValue("root_dir", fsDefaults.default_root_dir);
    }
  }, [fsDefaults, form, watchedRootDir, rootDirMode]);

  const treeRoot = fsDefaults?.tree_root ?? HOST_FS_ROOT;
  const routeBackendOptions = useMemo(() => {
    const builtins = BUILTIN_BACKENDS.map((mode) => ({
      value: mode,
      label: builtinLabel(mode, t),
    }));
    const configured = backends
      .filter((b) => b.enabled)
      .map((b) => ({
        value: `named:${b.name}` as const,
        label: `${b.name} (${b.kind})`,
      }));
    return [...builtins, ...configured];
  }, [backends, t]);

  const backendSelectOptions = useMemo(
    () => [
      {
        label: t("experts.backendGroups.builtin"),
        options: [
          ...BUILTIN_BACKENDS.map((mode) => ({
            value: mode,
            label: builtinLabel(mode, t),
          })),
          {
            value: "composite",
            label: t("experts.backendModes.composite"),
          },
        ],
      },
      ...(backends.filter((b) => b.enabled).length > 0
        ? [
            {
              label: t("experts.backendGroups.configured"),
              options: backends
                .filter((b) => b.enabled)
                .map((b) => ({
                  value: `named:${b.name}`,
                  label: `${b.name} (${b.kind})`,
                })),
            },
          ]
        : []),
    ],
    [backends, t],
  );

  const desc = builtinDesc(backendChoice, t);

  const pathHasError = (path: string) =>
    path.trim() === "/" ||
    (path.trim().length > 0 && !isValidCompositePath(path));

  return (
    <>
      <Form.Item
        name="backend_choice"
        label={t("experts.backendLabel")}
        initialValue={DEFAULT_BACKEND}
      >
        <Select
          loading={backendsLoading}
          options={backendSelectOptions}
          placeholder={t("experts.backendPlaceholder")}
        />
      </Form.Item>

      {desc ? (
        <div style={{ margin: "-8px 0 12px" }}>
          <p
            style={{
              fontSize: 12,
              color: "var(--fn-text-tertiary)",
              margin: 0,
            }}
          >
            {desc.text}
          </p>
          {desc.warning ? (
            <p style={{ fontSize: 12, color: "#d48806", margin: "4px 0 0" }}>
              {desc.warning}
            </p>
          ) : null}
        </div>
      ) : null}

      {(backendChoice === "local_shell" || backendChoice === "filesystem") && (
        <>
          <Form.Item
            name="root_dir"
            label={t("experts.backendRootDir")}
            initialValue={
              rootDirMode === "create"
                ? fsDefaults?.default_root_dir
                : undefined
            }
          >
            <RootDirSelect treeRoot={treeRoot} />
          </Form.Item>
          <div style={{ margin: "-8px 0 12px" }}>
            <p
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                margin: 0,
              }}
            >
              {t("experts.backendRootDirDesc", {
                home: fsDefaults?.home ?? "~",
              })}
            </p>
            <p
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                margin: "4px 0 0",
              }}
            >
              {t("experts.backendRootDirJailHint")}
            </p>
          </div>
        </>
      )}

      {backendChoice === "composite" && (
        <>
          <Form.Item
            name="composite_default"
            label={t("experts.backendModes.compositeDefault")}
            initialValue={DEFAULT_BACKEND}
          >
            <Select options={routeBackendOptions} />
          </Form.Item>

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>
              {t("experts.backendPathMappings")}
            </div>
            <p
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                margin: "0 0 8px",
              }}
            >
              {t("experts.backendModes.pathMappingHint")}
            </p>
            {pathMappings.map((mapping, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "center",
                }}
              >
                <Input
                  placeholder="/data"
                  value={mapping.path}
                  status={pathHasError(mapping.path) ? "error" : undefined}
                  onChange={(e) =>
                    onUpdatePathMapping(i, "path", e.target.value)
                  }
                  style={{ flex: 1 }}
                />
                <Select
                  placeholder={t("experts.backendModes.routeBackend")}
                  options={routeBackendOptions}
                  value={mapping.backend || undefined}
                  onChange={(v: string) => onUpdatePathMapping(i, "backend", v)}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  onClick={() => onRemovePathMapping(i)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--fn-text-tertiary)",
                    padding: 0,
                  }}
                >
                  <MinusCircle size={16} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className={styles.cardBtn}
              onClick={onAddPathMapping}
            >
              {t("experts.addPathMapping")}
            </button>
          </div>
        </>
      )}
    </>
  );
}
