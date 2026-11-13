import { useEffect, useMemo, useRef, useState } from "react";
import { Form, Input, Select } from "antd";
import RootDirSelect from "./RootDirSelect";
import { MinusCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import {
  BUILTIN_BACKENDS,
  DEFAULT_BACKEND,
  LEGACY_STATE_BACKEND,
  defaultCreateBackendChoice,
  fetchFilesystemDefaults,
  joinWorkspaceDir,
  newWorkspaceAgentId,
  type BackendOption,
  type FilesystemDefaults,
  type PathMapping,
  backendPolicyTypeLabel,
  builtinDesc,
  builtinLabel,
  canonicalBackendPolicyType,
  isBackendPolicyTypeAllowed,
  isHostRootDir,
  isValidCompositePath,
  resolveCreateBackendChoice,
  resolveRestrictedCompositeDefault,
  restrictedBackendTypes,
} from "./agentBackendForm";
import { HOST_FS_ROOT } from "./rootDirTree";
import styles from "../index.module.less";

interface AgentBackendFieldsProps {
  backends: BackendOption[];
  backendsLoading: boolean;
  backendChoice: string;
  pathMappings: PathMapping[];
  /** ``create`` fills empty root_dir with the filesystem default; ``edit`` leaves existing values. */
  rootDirMode?: "create" | "edit";
  disabled?: boolean;
  /** Skip local ``/filesystem/defaults`` (peer experts have no host tree here). */
  skipHostFilesystem?: boolean;
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
  disabled = false,
  skipHostFilesystem = false,
  onAddPathMapping,
  onRemovePathMapping,
  onUpdatePathMapping,
}: AgentBackendFieldsProps) {
  const { t, i18n } = useTranslation();
  const form = Form.useFormInstance();
  const allowedBackendTypes = useCurrentUser()?.allowed_backend_types;
  const allowedSet = useMemo(
    () => restrictedBackendTypes(allowedBackendTypes),
    [allowedBackendTypes],
  );
  const createDefaultChoice = defaultCreateBackendChoice(allowedBackendTypes);
  const backendTouched = useRef(false);
  const [fsDefaults, setFsDefaults] = useState<FilesystemDefaults | null>(null);
  const watchedRootDir = Form.useWatch("root_dir", form) as string | undefined;
  const watchedWorkspaceDir = Form.useWatch("workspace_dir", form) as
    | string
    | undefined;
  const watchedAgentId = Form.useWatch("agent_id", form) as string | undefined;
  const generatedWorkspaceId = useRef<string | null>(null);
  const watchedCompositeDefault = Form.useWatch("composite_default", form) as
    | string
    | undefined;

  useEffect(() => {
    if (skipHostFilesystem) {
      setFsDefaults(null);
      return;
    }
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
  }, [skipHostFilesystem]);

  useEffect(() => {
    if (!fsDefaults || rootDirMode !== "create") return;
    const current = watchedRootDir;
    if (!current) {
      form.setFieldValue("root_dir", fsDefaults.default_root_dir);
    }
  }, [fsDefaults, form, watchedRootDir, rootDirMode]);

  useEffect(() => {
    if (rootDirMode !== "create" || skipHostFilesystem) return;
    const parent = fsDefaults?.default_workspace_dir?.trim();
    if (!parent || !isHostRootDir(watchedRootDir)) return;
    const current = (watchedWorkspaceDir ?? "").trim();
    const auto = String(form.getFieldValue("workspace_dir_auto") ?? "").trim();
    if (current && current !== auto) return;
    const typedId = watchedAgentId?.trim() ?? "";
    let id = typedId;
    if (!id) {
      if (!generatedWorkspaceId.current || !current) {
        generatedWorkspaceId.current = newWorkspaceAgentId();
      }
      id = generatedWorkspaceId.current;
    }
    const next = joinWorkspaceDir(parent, id);
    if (current === next && auto === next) return;
    form.setFieldsValue({
      workspace_dir: next,
      workspace_dir_auto: next,
    });
  }, [
    form,
    fsDefaults,
    rootDirMode,
    skipHostFilesystem,
    watchedAgentId,
    watchedRootDir,
    watchedWorkspaceDir,
  ]);

  const treeRoots = useMemo(
    () =>
      fsDefaults?.browse_roots?.length
        ? fsDefaults.browse_roots
        : [fsDefaults?.tree_root ?? HOST_FS_ROOT],
    [fsDefaults],
  );
  const choiceLabel = (value: string): string => {
    if (value === "composite") return t("experts.backendModes.composite");
    if (
      value === "local_shell" ||
      value === "filesystem" ||
      value === LEGACY_STATE_BACKEND
    ) {
      return builtinLabel(value, t);
    }
    if (value.startsWith("named:")) {
      const name = value.slice("named:".length);
      const row = backends.find((b) => b.name === name);
      return row ? `${row.name} (${row.kind})` : value;
    }
    return value;
  };
  const filteredBuiltins = useMemo(
    () =>
      BUILTIN_BACKENDS.filter((mode) =>
        isBackendPolicyTypeAllowed(mode, allowedSet),
      ),
    [allowedSet],
  );
  const filteredBackends = useMemo(
    () =>
      backends.filter(
        (b) =>
          b.enabled &&
          isBackendPolicyTypeAllowed(b.kind.toLowerCase(), allowedSet),
      ),
    [allowedSet, backends],
  );
  const concreteValues = useMemo(
    () => [
      ...filteredBuiltins,
      ...filteredBackends.map((b) => `named:${b.name}`),
    ],
    [filteredBackends, filteredBuiltins],
  );

  useEffect(() => {
    if (rootDirMode !== "create" || !allowedSet || disabled) return;
    // The drawer reset writes ``local_shell`` in its own effect, after this
    // one. Read the field on the next turn so that default does not stick.
    const timer = window.setTimeout(() => {
      const current = String(form.getFieldValue("backend_choice") ?? "");
      const next = resolveCreateBackendChoice(current, concreteValues, {
        backendsLoading,
        userTouched: backendTouched.current,
      });
      if (next && next !== current) {
        form.setFieldValue("backend_choice", next);
      }
      const currentDefault = String(
        form.getFieldValue("composite_default") ?? "",
      );
      const nextDefault = resolveRestrictedCompositeDefault(
        currentDefault,
        concreteValues,
        backendsLoading,
      );
      if (nextDefault === undefined) {
        if (currentDefault) {
          form.setFieldValue("composite_default", undefined);
        }
      } else if (nextDefault !== null && nextDefault !== currentDefault) {
        form.setFieldValue("composite_default", nextDefault);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    allowedSet,
    backendsLoading,
    concreteValues,
    disabled,
    form,
    rootDirMode,
  ]);

  const retainSelected = (
    options: { value: string; label: string }[],
    selected: string | undefined,
  ) => {
    if (!selected || options.some((option) => option.value === selected)) {
      return options;
    }
    const keep = selected === LEGACY_STATE_BACKEND || rootDirMode === "edit";
    if (!keep) return options;
    return [...options, { value: selected, label: choiceLabel(selected) }];
  };

  const routeBackendOptions = useMemo(() => {
    const builtins = filteredBuiltins.map((mode) => ({
      value: mode,
      label: builtinLabel(mode, t),
    }));
    const configured = filteredBackends.map((b) => ({
      value: `named:${b.name}` as const,
      label: `${b.name} (${b.kind})`,
    }));
    return [...builtins, ...configured];
  }, [filteredBackends, filteredBuiltins, t]);

  const backendSelectOptions = useMemo(() => {
    const builtinOptions = retainSelected(
      [
        ...filteredBuiltins.map((mode) => ({
          value: mode,
          label: builtinLabel(mode, t),
        })),
        {
          value: "composite",
          label: t("experts.backendModes.composite"),
        },
      ],
      backendChoice.startsWith("named:") ? undefined : backendChoice,
    );
    const configuredOptions = retainSelected(
      filteredBackends.map((b) => ({
        value: `named:${b.name}`,
        label: `${b.name} (${b.kind})`,
      })),
      backendChoice.startsWith("named:") ? backendChoice : undefined,
    );
    return [
      {
        label: t("experts.backendGroups.builtin"),
        options: builtinOptions,
      },
      ...(configuredOptions.length > 0
        ? [
            {
              label: t("experts.backendGroups.configured"),
              options: configuredOptions,
            },
          ]
        : []),
    ];
  }, [backendChoice, filteredBackends, filteredBuiltins, rootDirMode, t]);

  const desc = builtinDesc(backendChoice, t);
  const pathLocked = disabled || rootDirMode === "edit";

  const pathHasError = (path: string) =>
    path.trim() === "/" ||
    (path.trim().length > 0 && !isValidCompositePath(path));

  return (
    <>
      <Form.Item
        name="backend_choice"
        label={t("experts.backendLabel")}
        initialValue={
          rootDirMode === "create" ? createDefaultChoice : DEFAULT_BACKEND
        }
      >
        <Select
          disabled={disabled}
          loading={backendsLoading}
          options={backendSelectOptions}
          placeholder={t("experts.backendPlaceholder")}
          onSelect={() => {
            backendTouched.current = true;
          }}
        />
      </Form.Item>

      {!backendsLoading &&
      allowedSet &&
      filteredBuiltins.length === 0 &&
      filteredBackends.length === 0 ? (
        <p
          style={{
            fontSize: 12,
            color: "var(--fn-text-tertiary)",
            margin: "-8px 0 12px",
          }}
        >
          {t("experts.backendAllowedEmpty", {
            types: (allowedBackendTypes ?? [])
              .map((type) =>
                backendPolicyTypeLabel(canonicalBackendPolicyType(type), t),
              )
              .join(i18n.language.startsWith("zh") ? "、" : ", "),
          })}
        </p>
      ) : null}

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
            <RootDirSelect treeRoots={treeRoots} disabled={pathLocked} />
          </Form.Item>
          <div style={{ margin: "-8px 0 12px" }}>
            {rootDirMode === "edit" ? (
              <p
                style={{
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                  margin: 0,
                }}
              >
                {t("experts.backendRootDirImmutableHint")}
              </p>
            ) : (
              <>
                <p
                  style={{
                    fontSize: 12,
                    color: "var(--fn-text-tertiary)",
                    margin: 0,
                  }}
                >
                  {fsDefaults?.in_container
                    ? t("experts.backendRootDirDescContainer")
                    : t("experts.backendRootDirDesc")}
                </p>
                <p
                  style={{
                    fontSize: 12,
                    color: "var(--fn-text-tertiary)",
                    margin: "4px 0 0",
                  }}
                >
                  {fsDefaults?.jail_enforced
                    ? t("experts.backendRootDirJailHint")
                    : t("experts.backendRootDirPathLimitHint")}
                </p>
              </>
            )}
          </div>
          {isHostRootDir(watchedRootDir) ? (
            <>
              <Form.Item name="workspace_dir" label={t("experts.workspaceDir")}>
                <RootDirSelect treeRoots={treeRoots} disabled={pathLocked} />
              </Form.Item>
              <div style={{ margin: "-8px 0 12px" }}>
                <p
                  style={{
                    fontSize: 12,
                    color: "var(--fn-text-tertiary)",
                    margin: 0,
                  }}
                >
                  {pathLocked
                    ? t("experts.workspaceDirImmutableHint")
                    : t("experts.workspaceDirDesc")}
                </p>
              </div>
            </>
          ) : null}
        </>
      )}

      {backendChoice === "composite" && (
        <>
          <Form.Item
            name="composite_default"
            label={t("experts.backendModes.compositeDefault")}
            initialValue={
              rootDirMode === "create" &&
              createDefaultChoice !== DEFAULT_BACKEND
                ? undefined
                : DEFAULT_BACKEND
            }
            rules={
              rootDirMode === "create"
                ? [{ required: true, message: t("experts.backendPlaceholder") }]
                : undefined
            }
          >
            <Select
              disabled={disabled}
              options={retainSelected(
                routeBackendOptions,
                watchedCompositeDefault,
              )}
            />
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
                  disabled={disabled}
                  placeholder="/data"
                  value={mapping.path}
                  status={pathHasError(mapping.path) ? "error" : undefined}
                  onChange={(e) =>
                    onUpdatePathMapping(i, "path", e.target.value)
                  }
                  style={{ flex: 1 }}
                />
                <Select
                  disabled={disabled}
                  placeholder={t("experts.backendModes.routeBackend")}
                  options={retainSelected(routeBackendOptions, mapping.backend)}
                  value={mapping.backend || undefined}
                  onChange={(v: string) => onUpdatePathMapping(i, "backend", v)}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  disabled={disabled}
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
              disabled={disabled}
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
