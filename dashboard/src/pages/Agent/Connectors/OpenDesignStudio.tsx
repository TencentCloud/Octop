import { useRef, useState, type ReactNode } from "react";
import {
  Alert,
  App,
  Button,
  Drawer,
  Modal,
  Spin,
  Input,
  List,
  Select,
  Space,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";
import { connectorsApi } from "../../../api/modules/connectors";
import {
  openDesignApi,
  type DesignCatalog,
  type DesignResource,
  type DesignSelection,
} from "../../../api/modules/openDesign";
import { apiErrorMessage } from "../../../utils/apiError";
import { OpenDesignHealth } from "./OpenDesignHealth";

function resourceId(
  resource: DesignResource,
  kind: string,
): string | undefined {
  try {
    const uri = new URL(resource.uri);
    if (uri.hostname === kind)
      return decodeURIComponent(uri.pathname.split("/")[1]);
  } catch {
    /* Ignore unsupported resource URIs. */
  }
}

export function OpenDesignStudio({
  instanceId,
  selectedNames,
  agentId,
  threadId,
  trigger,
}: {
  trigger?: (open: () => void) => ReactNode;
  instanceId?: string;
  selectedNames?: string[];
  agentId?: string;
  threadId?: string | null;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const requestNumber = useRef(0);
  const readingNumber = useRef(0);
  const [resourceKind, setResourceKind] = useState("all");
  const [open, setOpen] = useState(false);
  const [instances, setInstances] = useState<
    { value: string; label: string }[]
  >([]);
  const [instance, setInstance] = useState(instanceId);
  const [catalog, setCatalog] = useState<DesignCatalog>();
  const [selection, setSelection] = useState<DesignSelection>({ skills: [] });
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{
    name: string;
    text?: string;
    truncated?: boolean;
    loading?: boolean;
    error?: string;
  }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const closePreview = () => {
    readingNumber.current += 1;
    setPreview(undefined);
  };
  const load = async (id: string, cursor?: string) => {
    const current = ++requestNumber.current;
    setBusy(true);
    setError(undefined);
    try {
      const data = await openDesignApi.catalog(
        id,
        agentId,
        threadId ?? undefined,
        cursor,
      );
      if (current !== requestNumber.current) return;
      setCatalog((previous) =>
        cursor && previous
          ? { ...data, resources: [...previous.resources, ...data.resources] }
          : data,
      );
      if (!cursor)
        setSelection({
          ...data.selection,
          skills: data.selection.skills ?? [],
        });
    } catch (e) {
      setError(apiErrorMessage(e, t("openDesignStudio.failed"), t));
    } finally {
      if (current === requestNumber.current) setBusy(false);
    }
  };
  const start = async () => {
    setOpen(true);
    setCatalog(undefined);
    closePreview();
    setError(undefined);
    if (instanceId) {
      setInstance(instanceId);
      await load(instanceId);
      return;
    }
    setBusy(true);
    try {
      const rows = await connectorsApi.listInstances(agentId);
      const choices = rows
        .filter(
          (r) =>
            r.kind === "open-design" &&
            r.status === "active" &&
            selectedNames?.includes(r.mcp_server_name),
        )
        .map((r) => ({ value: r.instance_id, label: r.display_name }));
      setInstances(choices);
      setInstance(choices[0]?.value);
      if (choices[0]) await load(choices[0].value);
    } catch (e) {
      setError(apiErrorMessage(e, t("openDesignStudio.failed"), t));
    } finally {
      setBusy(false);
    }
  };
  const agent = catalog?.agents.find((a) => a.id === selection.agent);
  const options = (kind: string) =>
    catalog?.resources.flatMap((r) => {
      const id = resourceId(r, kind);
      return id ? [{ value: id, label: r.name }] : [];
    });
  return (
    <>
      {trigger ? (
        trigger(() => void start())
      ) : (
        <Button size="small" onClick={() => void start()}>
          {t("openDesignStudio.title")}
        </Button>
      )}
      <Drawer
        title={t("openDesignStudio.title")}
        width={640}
        open={open}
        onClose={() => {
          setOpen(false);
          closePreview();
        }}
      >
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          {error && <Alert type="error" showIcon message={error} />}
          {!instanceId && (
            <Select
              style={{ width: "100%" }}
              value={instance}
              options={instances}
              placeholder={t("openDesignStudio.connector")}
              onChange={(id) => {
                setInstance(id);
                setCatalog(undefined);
                closePreview();
                void load(id);
              }}
            />
          )}
          <Alert
            type="info"
            showIcon
            message={t(
              threadId
                ? "openDesignStudio.scopeThread"
                : "openDesignStudio.scopeDefault",
            )}
            description={t("openDesignStudio.bindingHint")}
          />
          {instance && (
            <OpenDesignHealth key={instance} instanceId={instance} />
          )}
          {catalog && (
            <>
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Typography.Text strong>
                  {t("openDesignStudio.agent")}
                </Typography.Text>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  value={selection.agent ?? undefined}
                  placeholder={t("openDesignStudio.default")}
                  options={catalog.agents.map((a) => ({
                    value: a.id,
                    label: a.name,
                  }))}
                  onChange={(value) =>
                    setSelection({
                      ...selection,
                      agent: value,
                      model: undefined,
                    })
                  }
                />
                <Typography.Text strong>
                  {t("openDesignStudio.model")}
                </Typography.Text>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  disabled={!agent}
                  value={selection.model ?? undefined}
                  placeholder={t("openDesignStudio.default")}
                  options={agent?.models?.map((m) =>
                    typeof m === "string"
                      ? { value: m, label: m }
                      : { value: m.id, label: m.name ?? m.id },
                  )}
                  onChange={(model) => setSelection({ ...selection, model })}
                />
                <Typography.Text type="secondary">
                  {t("openDesignStudio.modelHint")}
                </Typography.Text>
                <Typography.Text strong>
                  {t("openDesignStudio.skills")}
                </Typography.Text>
                <Select
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  value={selection.skills}
                  options={options("skills")}
                  onChange={(skills) => setSelection({ ...selection, skills })}
                />
                <Typography.Text strong>
                  {t("openDesignStudio.designSystem")}
                </Typography.Text>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  value={selection.designSystem ?? undefined}
                  options={options("design-systems")}
                  onChange={(designSystem) =>
                    setSelection({ ...selection, designSystem })
                  }
                />
                <Button
                  type="primary"
                  loading={busy}
                  onClick={async () => {
                    if (!instance) return;
                    setBusy(true);
                    setError(undefined);
                    try {
                      await openDesignApi.select(
                        instance,
                        selection,
                        agentId,
                        threadId ?? undefined,
                      );
                      message.success(t("openDesignStudio.saved"));
                    } catch (e) {
                      setError(
                        apiErrorMessage(e, t("openDesignStudio.failed"), t),
                      );
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {t("common.save")}
                </Button>
              </Space>
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Typography.Text strong>
                  {t("openDesignStudio.resources")}
                </Typography.Text>
                <Select
                  value={resourceKind}
                  style={{ width: "100%" }}
                  options={["all", "skills", "design-systems"].map((value) => ({
                    value,
                    label: t(`openDesignStudio.category.${value}`),
                  }))}
                  onChange={setResourceKind}
                />
                <Input.Search
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("openDesignStudio.search")}
                />
                <List
                  size="small"
                  bordered
                  style={{ maxHeight: 280, overflow: "auto" }}
                  dataSource={catalog.resources
                    .filter(
                      (r) =>
                        resourceKind === "all" || !!resourceId(r, resourceKind),
                    )
                    .filter((r) =>
                      `${r.name} ${r.description ?? ""}`
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    )}
                  renderItem={(r) => (
                    <List.Item
                      actions={[
                        <Button
                          key="read"
                          type="link"
                          onClick={async () => {
                            if (!instance) return;
                            const reading = ++readingNumber.current;
                            setPreview({ name: r.name, loading: true });
                            try {
                              const content = await openDesignApi.resource(
                                instance,
                                r.uri,
                                agentId,
                                threadId ?? undefined,
                              );
                              if (reading === readingNumber.current)
                                setPreview({ name: r.name, ...content });
                            } catch (e) {
                              if (reading !== readingNumber.current) return;
                              setPreview({
                                name: r.name,
                                error: apiErrorMessage(
                                  e,
                                  t("openDesignStudio.failed"),
                                  t,
                                ),
                              });
                            }
                          }}
                        >
                          {t("openDesignStudio.read")}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={r.name}
                        description={r.description}
                      />
                    </List.Item>
                  )}
                />
                {catalog.next_cursor && (
                  <Button
                    loading={busy}
                    onClick={() =>
                      instance && void load(instance, catalog.next_cursor!)
                    }
                  >
                    {t("openDesignStudio.more")}
                  </Button>
                )}
              </Space>
            </>
          )}
        </Space>
      </Drawer>
      <Modal
        title={preview?.name ?? t("openDesignStudio.read")}
        open={!!preview}
        onCancel={closePreview}
        footer={null}
        width={800}
        centered
      >
        <div style={{ maxHeight: "65vh", overflow: "auto" }}>
          {preview?.loading && <Spin />}
          {preview?.error && (
            <Alert type="error" showIcon message={preview.error} />
          )}
          {preview?.truncated && (
            <Alert type="warning" message={t("openDesignStudio.truncated")} />
          )}
          {preview?.text !== undefined && (
            <Typography.Paragraph
              style={{
                whiteSpace: "pre-wrap",
                overflowWrap: "anywhere",
                margin: 0,
              }}
            >
              {preview.text}
            </Typography.Paragraph>
          )}
        </div>
      </Modal>
    </>
  );
}
