import { lazy, Suspense, useState } from "react";
import { Alert, Button, Drawer, Input, List, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  openDesignApi,
  type DesignSource,
  type DesignTask,
} from "../../../api/modules/openDesign";
import { apiErrorMessage } from "../../../utils/apiError";
import { useTheme } from "../../../context/ThemeContext";
const DiffEditor = lazy(() =>
  import("@monaco-editor/react").then((m) => ({ default: m.DiffEditor })),
);

export default function OpenDesignSource({
  agentId,
  threadId,
  task,
}: {
  agentId: string;
  threadId: string;
  task: DesignTask;
}) {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState(task.result.entryFile ?? "");
  const [source, setSource] = useState<DesignSource>();
  const [draft, setDraft] = useState("");
  const [reviewed, setReviewed] = useState<string>();
  const [matches, setMatches] = useState<
    { file: string; line: number; snippet: string }[]
  >([]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string>();
  const load = async (file: string) => {
    setBusy(true);
    setError(undefined);
    try {
      const data = await openDesignApi.file(
        agentId,
        threadId,
        task.instance_id,
        task.project,
        file,
      );
      setSource(data);
      setPath(data.path);
      setDraft(data.content);
      setReviewed(undefined);
    } catch (e) {
      setError(apiErrorMessage(e, t("openDesignStudio.failed"), t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button onClick={() => setOpen(true)}>
        {t("openDesignSource.title")}
      </Button>
      <Drawer
        title={`${t("openDesignSource.title")} · ${task.project}`}
        width={960}
        open={open}
        onClose={() => setOpen(false)}
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Alert type="info" showIcon message={t("openDesignSource.safety")} />
          {error && <Alert type="error" showIcon message={error} />}
          <Input.Search
            placeholder={t("openDesignSource.search")}
            loading={busy}
            onSearch={async (query) => {
              if (!query.trim()) return;
              setBusy(true);
              setError(undefined);
              try {
                setMatches(
                  (
                    await openDesignApi.search(
                      agentId,
                      threadId,
                      task.instance_id,
                      task.project,
                      query,
                    )
                  ).matches ?? [],
                );
              } catch (e) {
                setError(apiErrorMessage(e, t("openDesignStudio.failed"), t));
              } finally {
                setBusy(false);
              }
            }}
          />
          {!!matches.length && (
            <List
              size="small"
              bordered
              style={{ maxHeight: 220, overflow: "auto" }}
              dataSource={matches}
              renderItem={(match) => (
                <List.Item>
                  <Button type="link" onClick={() => void load(match.file)}>
                    {match.file}:{match.line}
                  </Button>
                  <Typography.Text ellipsis>{match.snippet}</Typography.Text>
                </List.Item>
              )}
            />
          )}
          <Input.Search
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t("openDesignSource.path")}
            enterButton={t("openDesignSource.load")}
            loading={busy}
            onSearch={() => void load(path)}
          />
          {source && (
            <>
              <Typography.Text strong>{source.path}</Typography.Text>
              {source.truncated && (
                <Alert
                  type="warning"
                  message={t("openDesignSource.truncated")}
                />
              )}
              <Input.TextArea
                aria-label={t("openDesignSource.content")}
                readOnly={source.truncated}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setReviewed(undefined);
                }}
                autoSize={{ minRows: 12, maxRows: 24 }}
                style={{ fontFamily: "monospace" }}
              />
              <Space wrap>
                <Button
                  disabled={source.truncated || source.content === draft}
                  onClick={() => setReviewed(draft)}
                >
                  {t("openDesignSource.review")}
                </Button>
                <Button
                  type="primary"
                  loading={busy}
                  disabled={
                    source.truncated ||
                    reviewed !== draft ||
                    source.content === draft
                  }
                  onClick={async () => {
                    setBusy(true);
                    setError(undefined);
                    try {
                      const data = await openDesignApi.edit(
                        agentId,
                        threadId,
                        task.instance_id,
                        task.project,
                        {
                          path: source.path,
                          digest: source.digest,
                          content: draft,
                        },
                      );
                      setSource(data);
                      setDraft(data.content);
                      setReviewed(undefined);
                      setPreview(data.previewUrl);
                    } catch (e) {
                      setError(
                        apiErrorMessage(e, t("openDesignStudio.failed"), t),
                      );
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {t("openDesignSource.save")}
                </Button>
                {preview && /^https?:\/\//.test(preview) && (
                  <Button
                    href={preview}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t("openDesignTasks.preview")}
                  </Button>
                )}
              </Space>
              {reviewed !== undefined && (
                <Suspense
                  fallback={
                    <Typography.Text>{t("common.loading")}</Typography.Text>
                  }
                >
                  <DiffEditor
                    height="400px"
                    original={source.content}
                    modified={reviewed}
                    theme={isDark ? "vs-dark" : "light"}
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                    }}
                  />
                </Suspense>
              )}
            </>
          )}
        </Space>
      </Drawer>
    </>
  );
}
