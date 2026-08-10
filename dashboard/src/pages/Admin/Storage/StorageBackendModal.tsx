/**
 * StorageBackendDrawer — create or edit a storage backend (right-side drawer).
 *
 * Supports three modes:
 *   - Create (no editing, no presetKind): shows kind selector + all generic fields
 *   - Create from preset (presetKind provided): kind locked, shows type-specific fields
 *   - Edit (editing provided): kind locked, all fields optional (secrets blank = unchanged)
 *
 * Structured fields: name, kind, access_key, secret_key, bucket, region, endpoint
 * Collapsible advanced section: raw JSON config
 */
import { useEffect, useRef, useState } from "react";
import { Button, Collapse, Drawer, Form, Input, Select } from "antd";
import { message } from "@/utils/antdMessage";

import { Activity } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import {
  clearFormDraft,
  loadFormDraft,
  saveFormDraft,
} from "../../../utils/formDraft";
import {
  STORAGE_KINDS,
  STORAGE_TYPE_DEFS,
  type StorageBackendRow,
} from "./useStorageBackends";
import { DockerEnvFooter } from "./DockerEnvFooter";

interface StorageBackendDrawerProps {
  open: boolean;
  onClose: () => void;
  onSaved: (name?: string) => void | Promise<void>;
  /** When provided, modal is in edit mode. */
  editing?: StorageBackendRow;
  /** When provided (create from type card), the kind is pre-selected and locked. */
  presetKind?: string;
}

interface StorageForm {
  name: string;
  kind: string;
  access_key: string;
  secret_key: string;
  bucket: string;
  region: string;
  endpoint?: string;
  config_json?: string;
  note?: string;
  sandbox_scope?: string;
  sandbox_prefix?: string;
  sandbox_id?: string;
  username?: string;
}

export function StorageBackendDrawer({
  open,
  onClose,
  onSaved,
  editing,
  presetKind,
}: StorageBackendDrawerProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [probing, setProbing] = useState(false);
  const [form] = Form.useForm<StorageForm>();
  const isEdit = editing !== undefined;
  const draftScope = editing
    ? `storage:${editing.id}`
    : `storage:new:${presetKind ?? "cos"}`;
  const restoringDraftRef = useRef(false);

  // Determine the active kind for showing type-specific field hints
  const [activeKind, setActiveKind] = useState<string>(
    editing?.kind ?? presetKind ?? "cos",
  );
  const typeDef = STORAGE_TYPE_DEFS.find((d) => d.kind === activeKind);
  const sandboxScope = Form.useWatch("sandbox_scope", form) ?? "agent";

  useEffect(() => {
    if (open) {
      if (editing) {
        setActiveKind(editing.kind);
        let cfg: Record<string, unknown> = {};
        try {
          const parsed = JSON.parse(editing.config_json || "{}") as unknown;
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            cfg = parsed as Record<string, unknown>;
          }
        } catch {
          cfg = {};
        }
        form.setFieldsValue({
          name: editing.name,
          kind: editing.kind,
          access_key: "",
          secret_key: "",
          bucket: editing.bucket ?? "",
          region: editing.region ?? "",
          endpoint: editing.endpoint ?? "",
          config_json: editing.config_json ?? "",
          note: editing.note ?? "",
          sandbox_scope:
            typeof cfg.sandbox_scope === "string" ? cfg.sandbox_scope : "agent",
          sandbox_prefix:
            typeof cfg.sandbox_prefix === "string"
              ? cfg.sandbox_prefix
              : "octop_sandbox",
          sandbox_id: typeof cfg.sandbox_id === "string" ? cfg.sandbox_id : "",
          username: typeof cfg.username === "string" ? cfg.username : "",
        });
      } else {
        const kind = presetKind ?? "cos";
        setActiveKind(kind);
        form.resetFields();
        form.setFieldValue("kind", kind);
        if (kind === "docker") {
          form.setFieldValue("bucket", "python:3.12-slim");
          form.setFieldValue("sandbox_scope", "agent");
          form.setFieldValue("sandbox_prefix", "octop_sandbox");
        }
      }
      const draft = loadFormDraft<Partial<StorageForm>>(draftScope);
      if (draft) {
        restoringDraftRef.current = true;
        form.setFieldsValue(draft);
        if (typeof draft.kind === "string") setActiveKind(draft.kind);
        restoringDraftRef.current = false;
      }
    }
  }, [open, editing, presetKind, form, draftScope]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      const body: Record<string, unknown> = {
        kind: values.kind,
        bucket: values.bucket?.trim() || null,
        region: values.region?.trim() || null,
        endpoint: values.endpoint?.trim() || null,
        config_json: values.config_json?.trim() || null,
        note: values.note?.trim() || null,
      };
      if (values.access_key?.trim()) body.access_key = values.access_key.trim();
      if (values.secret_key?.trim()) body.secret_key = values.secret_key.trim();

      if (values.kind === "docker") {
        let cfg: Record<string, unknown> = {};
        try {
          const parsed = JSON.parse(
            values.config_json?.trim() || "{}",
          ) as unknown;
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            cfg = { ...(parsed as Record<string, unknown>) };
          }
        } catch {
          cfg = {};
        }
        const scope = (values.sandbox_scope || "agent").trim() || "agent";
        cfg.sandbox_scope = scope;
        cfg.sandbox_prefix =
          (values.sandbox_prefix || "octop_sandbox").trim() || "octop_sandbox";
        if (scope === "fixed" && values.sandbox_id?.trim()) {
          cfg.sandbox_id = values.sandbox_id.trim();
        } else {
          delete cfg.sandbox_id;
        }
        if (scope === "user" && values.username?.trim()) {
          cfg.username = values.username.trim();
        } else if (scope !== "user") {
          delete cfg.username;
        }
        body.config_json = JSON.stringify(cfg);
      }

      const backendName = isEdit ? editing!.name : values.name.trim();

      let backendId: number | undefined = isEdit ? editing!.id : undefined;

      if (isEdit) {
        await request(`/admin/storage-backends/${editing!.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        message.success(t("storage.updateSuccess", { name: backendName }));
      } else {
        body.name = backendName;
        const created = await request<{ id: number }>(
          "/admin/storage-backends",
          {
            method: "POST",
            body: JSON.stringify(body),
          },
        );
        backendId = created.id;
        message.success(t("storage.createSuccess", { name: backendName }));
      }

      // New docker backends are enabled by default — start image pull right away.
      if (values.kind === "docker" && backendId != null) {
        const hide = message.loading(t("storage.dockerPulling"), 0);
        try {
          const result = await request<{
            ok: boolean;
            message?: string;
            message_key?: string;
          }>(`/admin/storage-backends/${backendId}/test`, { method: "POST" });
          hide();
          if (result.ok) {
            const msg = result.message_key
              ? t(
                  `storage.${result.message_key}`,
                  result.message || t("storage.testSuccess"),
                )
              : result.message || t("storage.testSuccess");
            message.success(msg);
          } else {
            message.warning(result.message || t("storage.testFailed"));
          }
        } catch (err) {
          hide();
          message.warning(
            err instanceof Error ? err.message : t("storage.testFailed"),
          );
        }
      }

      clearFormDraft(draftScope);
      await onSaved(backendName);
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      const msg = err instanceof Error ? err.message : t("common.saveFailed");
      message.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const kindOptions = STORAGE_KINDS.map((k) => ({
    value: k.value,
    label: t(k.labelKey),
  }));

  // Build field label from typeDef field defs if available, else fallback to generic labels
  const fieldLabel = (key: string, fallbackKey: string) => {
    if (typeDef) {
      const f = typeDef.fields.find((fd) => fd.key === key);
      if (f) return t(f.labelKey);
    }
    return t(fallbackKey);
  };

  const fieldPlaceholder = (key: string, fallback: string) => {
    if (typeDef) {
      const f = typeDef.fields.find((fd) => fd.key === key);
      if (f?.placeholder) return f.placeholder;
    }
    return fallback;
  };

  const fieldRequired = (key: string, defaultRequired: boolean) => {
    if (isEdit) return false;
    if (typeDef) {
      const f = typeDef.fields.find((fd) => fd.key === key);
      if (f !== undefined) return !!f.required;
    }
    return defaultRequired;
  };

  const fieldRequiredMessage = (key: string) => {
    const f = typeDef?.fields.find((fd) => fd.key === key);
    if (f?.requiredMessageKey) return t(f.requiredMessageKey);
    const defaults: Record<string, string> = {
      access_key: "storage.pleaseEnterAccessKey",
      secret_key: "storage.pleaseEnterSecretKey",
      bucket: "storage.pleaseEnterBucket",
      region: "storage.pleaseEnterRegion",
      endpoint: "storage.pleaseEnterEndpoint",
    };
    return t(defaults[key] ?? "storage.pleaseEnterField");
  };

  const hasField = (key: string) => {
    if (!typeDef) return true; // show all fields when no type selected
    return typeDef.fields.some((f) => f.key === key);
  };

  const handleProbe = async () => {
    try {
      const fieldNames: (keyof StorageForm)[] = ["kind"];
      if (hasField("access_key")) fieldNames.push("access_key");
      if (hasField("secret_key")) fieldNames.push("secret_key");
      if (hasField("bucket")) fieldNames.push("bucket");
      if (hasField("region")) fieldNames.push("region");
      if (hasField("endpoint")) fieldNames.push("endpoint");

      const probeRequired = isEdit
        ? []
        : fieldNames.filter((key) => fieldRequired(key, false));
      const values = await form.validateFields([
        ...new Set([...fieldNames, ...probeRequired]),
      ]);
      setProbing(true);

      const body: Record<string, unknown> = {
        kind: values.kind,
        bucket: values.bucket?.trim() || null,
        region: values.region?.trim() || null,
        endpoint: values.endpoint?.trim() || null,
        config_json: values.config_json?.trim() || null,
      };
      if (values.access_key?.trim()) body.access_key = values.access_key.trim();
      if (values.secret_key?.trim()) body.secret_key = values.secret_key.trim();
      if (isEdit) body.backend_id = editing!.id;

      const result = await request<{
        ok: boolean;
        message?: string;
        message_key?: string;
      }>("/admin/storage-backends/probe", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (result.ok) {
        const msg = result.message_key
          ? t(
              `storage.${result.message_key}`,
              result.message || t("storage.testSuccess"),
            )
          : result.message || t("storage.testSuccess");
        message.success(msg);
      } else {
        message.error(result.message || t("storage.testFailed"));
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : t("storage.testFailed"),
      );
    } finally {
      setProbing(false);
    }
  };

  const drawerTitle = isEdit
    ? `${t("common.edit")} — ${editing!.name}`
    : presetKind
    ? `${t("storage.configure")} ${typeDef ? t(typeDef.nameKey) : presetKind}`
    : t("storage.addBackend");

  return (
    <Drawer
      title={drawerTitle}
      open={open}
      onClose={onClose}
      destroyOnHidden
      width={520}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            icon={<Activity size={14} />}
            loading={probing}
            onClick={() => void handleProbe()}
          >
            {t("storage.probe", "探测")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void handleSubmit()}
          >
            {isEdit ? t("common.save") : t("common.create")}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onValuesChange={(_, all) => {
          if (!restoringDraftRef.current) {
            saveFormDraft(
              draftScope,
              all as unknown as Record<string, unknown>,
            );
          }
        }}
      >
        {/* Name — create only */}
        {!isEdit && (
          <Form.Item
            name="name"
            label={t("storage.nameLabel")}
            rules={[{ required: true, message: t("storage.pleaseEnterName") }]}
          >
            <Input placeholder={t("storage.namePlaceholder")} />
          </Form.Item>
        )}

        {/* Kind selector — locked when editing or presetKind provided */}
        <Form.Item
          name="kind"
          label={t("storage.kindLabel")}
          rules={[{ required: true }]}
        >
          <Select
            options={kindOptions}
            disabled={isEdit || !!presetKind}
            onChange={(v: string) => setActiveKind(v)}
          />
        </Form.Item>

        {/* Access Key */}
        {hasField("access_key") && (
          <Form.Item
            name="access_key"
            label={fieldLabel("access_key", "storage.accessKeyLabel")}
            rules={
              fieldRequired("access_key", false)
                ? [
                    {
                      required: true,
                      message: fieldRequiredMessage("access_key"),
                    },
                  ]
                : []
            }
            extra={
              isEdit && editing?.access_key ? editing.access_key : undefined
            }
          >
            <Input.Password
              placeholder={
                isEdit
                  ? t("common.unchanged")
                  : fieldPlaceholder("access_key", "AKIDxxx")
              }
              visibilityToggle
            />
          </Form.Item>
        )}

        {/* Secret Key */}
        {hasField("secret_key") && (
          <Form.Item
            name="secret_key"
            label={fieldLabel("secret_key", "storage.secretKeyLabel")}
            rules={
              fieldRequired("secret_key", false)
                ? [
                    {
                      required: true,
                      message: fieldRequiredMessage("secret_key"),
                    },
                  ]
                : []
            }
          >
            <Input.Password
              placeholder={
                isEdit
                  ? t("common.unchanged")
                  : fieldPlaceholder("secret_key", "SKEYxxx")
              }
              visibilityToggle
            />
          </Form.Item>
        )}

        {/* Bucket / root_dir / image — mapped to "bucket" field */}
        {hasField("bucket") && (
          <Form.Item
            name="bucket"
            label={fieldLabel("bucket", "storage.bucketLabel")}
            rules={
              fieldRequired("bucket", false)
                ? [{ required: true, message: fieldRequiredMessage("bucket") }]
                : []
            }
          >
            <Input
              placeholder={fieldPlaceholder(
                "bucket",
                t("storage.bucketPlaceholder"),
              )}
            />
          </Form.Item>
        )}

        {/* Region / timeout / schema — mapped to "region" field */}
        {hasField("region") && (
          <Form.Item
            name="region"
            label={fieldLabel("region", "storage.regionLabel")}
            rules={
              fieldRequired("region", false)
                ? [{ required: true, message: fieldRequiredMessage("region") }]
                : []
            }
          >
            <Input
              placeholder={fieldPlaceholder(
                "region",
                t("storage.regionPlaceholder"),
              )}
            />
          </Form.Item>
        )}

        {/* Endpoint */}
        {hasField("endpoint") && (
          <Form.Item
            name="endpoint"
            label={fieldLabel("endpoint", "storage.endpointLabel")}
            rules={
              fieldRequired("endpoint", false)
                ? [
                    {
                      required: true,
                      message: fieldRequiredMessage("endpoint"),
                    },
                  ]
                : []
            }
          >
            <Input
              placeholder={fieldPlaceholder(
                "endpoint",
                t("storage.endpointPlaceholder"),
              )}
            />
          </Form.Item>
        )}

        {activeKind === "docker" && (
          <>
            <Form.Item
              name="sandbox_scope"
              label={t("storage.sandboxScopeLabel")}
              extra={t("storage.sandboxScopeExtra")}
              initialValue="agent"
            >
              <Select
                options={[
                  {
                    value: "agent",
                    label: t("storage.sandboxScopeAgent"),
                  },
                  {
                    value: "user",
                    label: t("storage.sandboxScopeUser"),
                  },
                  {
                    value: "fixed",
                    label: t("storage.sandboxScopeFixed"),
                  },
                ]}
              />
            </Form.Item>
            <Form.Item
              name="sandbox_prefix"
              label={t("storage.sandboxPrefixLabel")}
              extra={t("storage.sandboxPrefixExtra")}
              initialValue="octop_sandbox"
            >
              <Input placeholder="octop_sandbox" />
            </Form.Item>
            {sandboxScope === "fixed" && (
              <Form.Item
                name="sandbox_id"
                label={t("storage.sandboxIdLabel")}
                rules={[
                  {
                    required: true,
                    message: t("storage.pleaseEnterSandboxId"),
                  },
                ]}
              >
                <Input placeholder="my_shared_box" />
              </Form.Item>
            )}
            {sandboxScope === "user" && (
              <Form.Item
                name="username"
                label={t("storage.sandboxUsernameLabel")}
                extra={t("storage.sandboxUsernameExtra")}
              >
                <Input placeholder="alice" />
              </Form.Item>
            )}
          </>
        )}

        {/* Advanced JSON */}
        <Collapse
          ghost
          items={[
            {
              key: "advanced",
              label: t("storage.advancedConfig"),
              children: (
                <Form.Item
                  name="config_json"
                  extra={t("storage.advancedConfigExtra")}
                >
                  <Input.TextArea
                    rows={5}
                    placeholder='{"path_style": true}'
                    style={{ fontFamily: "monospace", fontSize: 12 }}
                  />
                </Form.Item>
              ),
            },
          ]}
        />

        {/* Note */}
        <Form.Item name="note" label={t("storage.noteLabel")}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>

      {activeKind === "docker" ? <DockerEnvFooter /> : null}
    </Drawer>
  );
}
