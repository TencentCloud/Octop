import { useCallback, useEffect, useRef, useState } from "react";
import {
  App,
  AutoComplete,
  Button,
  Dropdown,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Tag,
  Tooltip,
} from "antd";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleX,
  CodeXml,
  FileText,
  FolderOpen,
  Lightbulb,
  LoaderCircle,
  Paperclip,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Square,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { codeApi } from "../../api/modules/code";
import type {
  CodeFileItem,
  CodeLiveEvent,
  CodeModelOption,
  CodePermission,
  CodeRunner,
  CodeSession,
} from "../../api/types/code";
import styles from "./index.module.less";

const { TextArea } = Input;

const CODE_MONO =
  "var(--fn-font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)";

/** Accepted upload extensions — must stay in sync with the backend allow-list. */
const UPLOAD_ACCEPT =
  ".txt,.md,.markdown,.py,.js,.ts,.tsx,.json,.yaml,.yml,.toml,.sh,.sql,.csv,.log,.diff,.patch";

type CodeRole = "user" | "assistant" | "thought" | "tool" | "error";

interface CodeMessage {
  id: string;
  role: CodeRole;
  text: string;
  /** Assistant/thought message still receiving deltas. */
  streaming?: boolean;
  /** Thought block expanded. */
  open?: boolean;
  /** Tool call in flight. */
  running?: boolean;
  failed?: boolean;
  callId?: string;
  toolTitle?: string;
  toolKind?: string;
}

interface SkillItem {
  id: string;
  name: string;
}

export default function CodeConsolePage() {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [runners, setRunners] = useState<CodeRunner[]>([]);
  const [runnerName, setRunnerName] = useState("");
  const [modelMap, setModelMap] = useState<Record<string, CodeModelOption[]>>(
    {},
  );
  const [modelName, setModelName] = useState("");
  const [sessions, setSessions] = useState<CodeSession[]>([]);
  const [current, setCurrent] = useState<CodeSession | null>(null);
  const [msgs, setMsgs] = useState<CodeMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [warming, setWarming] = useState(false);
  const [creating, setCreating] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [attachments, setAttachments] = useState<CodeFileItem[]>([]);
  const [permission, setPermission] = useState<CodePermission | null>(null);
  const [patch, setPatch] = useState("");
  const [showPatch, setShowPatch] = useState(false);
  const [fileItems, setFileItems] = useState<CodeFileItem[]>([]);
  const [fileOpen, setFileOpen] = useState(false);
  const [skillItems, setSkillItems] = useState<SkillItem[]>([]);
  const [skillOpen, setSkillOpen] = useState(false);

  const abortRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const seqRef = useRef(0);

  const modelOptions = modelMap[runnerName] ?? [];
  const busy = streaming || warming;

  const nextId = () => {
    seqRef.current += 1;
    return `m${seqRef.current}`;
  };

  // -- data loading ----------------------------------------------------------

  const loadRunners = useCallback(async () => {
    try {
      const [runnerRes, modelRes] = await Promise.all([
        codeApi.listRunners(),
        codeApi.listModels(),
      ]);
      setRunners(runnerRes.runners);
      setModelMap(modelRes.models);
      setRunnerName((prev) => {
        if (prev && runnerRes.runners.some((r) => r.name === prev)) return prev;
        const preferred =
          runnerRes.runners.find((r) => r.name === "codebuddy") ??
          runnerRes.runners[0];
        return preferred?.name ?? "";
      });
    } catch {
      /* runners stay empty; the composer disables itself */
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const res = await codeApi.listSessions();
      setSessions(res.sessions);
    } catch {
      /* ignore — the list simply stays empty */
    }
  }, []);

  const loadSkills = useCallback(async () => {
    try {
      const raw = await codeApi.listSkills();
      const rows = Array.isArray(raw) ? raw : [];
      const list: SkillItem[] = rows
        .map((it) => ({
          id: String(it?.id ?? it?.name ?? ""),
          name: String(it?.name ?? it?.id ?? ""),
        }))
        .filter((it) => it.name)
        .slice(0, 100);
      setSkillItems(list);
    } catch {
      setSkillItems([]);
    }
  }, []);

  useEffect(() => {
    void loadRunners();
    void loadSessions();
    void loadSkills();
  }, [loadRunners, loadSessions, loadSkills]);

  useEffect(() => {
    const list = modelMap[runnerName] ?? [];
    setModelName((prev) =>
      prev && list.some((m) => m.id === prev) ? prev : list[0]?.id ?? "",
    );
  }, [runnerName, modelMap]);

  // -- live turn rendering ---------------------------------------------------

  const upsertTool = useCallback(
    (
      callId: string,
      patchUpdate: Partial<CodeMessage>,
      fallback: CodeMessage,
    ) => {
      setMsgs((prev) => {
        const idx = prev.findIndex(
          (m) => m.role === "tool" && m.callId === callId,
        );
        if (idx === -1) return [...prev, { ...fallback, ...patchUpdate }];
        const next = [...prev];
        next[idx] = { ...next[idx], ...patchUpdate };
        return next;
      });
    },
    [],
  );

  const applyLiveEvent = useCallback(
    (data: CodeLiveEvent) => {
      const type = String(data.type ?? "");
      if (type === "text_delta" || type === "text") {
        const chunk = String(data.text ?? "");
        setWarming(false);
        if (!chunk) return;
        setMsgs((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && last.streaming) {
            // A full `text` frame replaces the accumulated deltas.
            if (
              type === "text" &&
              (last.text === chunk || chunk.startsWith(last.text))
            ) {
              return [
                ...prev.slice(0, -1),
                { ...last, text: chunk, streaming: false },
              ];
            }
            const next = [...prev];
            next[next.length - 1] = { ...last, text: last.text + chunk };
            return next;
          }
          if (
            type === "text" &&
            last &&
            last.role === "assistant" &&
            last.text === chunk
          ) {
            return prev;
          }
          return [
            ...prev,
            {
              id: nextId(),
              role: "assistant",
              text: chunk,
              streaming: type !== "text",
            },
          ];
        });
        return;
      }
      if (type === "thought") {
        const chunk = String(data.text ?? "");
        setWarming(false);
        if (!chunk) return;
        setMsgs((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "thought" && last.streaming) {
            const next = [...prev];
            next[next.length - 1] = { ...last, text: last.text + chunk };
            return next;
          }
          return [
            ...prev,
            {
              id: nextId(),
              role: "thought",
              text: chunk,
              streaming: true,
              open: true,
            },
          ];
        });
        return;
      }
      if (type === "tool_start") {
        setWarming(false);
        const callId = String(data.call_id ?? "");
        const title = String(data.title ?? data.name ?? "tool");
        const kind = String(data.kind ?? "other");
        upsertTool(
          callId,
          { toolTitle: title, toolKind: kind, running: true },
          {
            id: nextId(),
            role: "tool",
            text: "",
            callId,
            toolTitle: title,
            toolKind: kind,
            running: true,
          },
        );
        return;
      }
      if (type === "tool_update") {
        const callId = String(data.call_id ?? "");
        const status = String(data.status ?? "");
        const detail = data.detail != null ? String(data.detail) : "";
        const terminal =
          status === "completed" || status === "done" || status === "failed";
        const patchUpdate: Partial<CodeMessage> = {
          running: !terminal && status !== "failed",
          failed: status === "failed",
          streaming: false,
        };
        if (detail && detail !== "unknown") patchUpdate.text = detail;
        if (data.title) patchUpdate.toolTitle = String(data.title);
        upsertTool(callId, patchUpdate, {
          id: nextId(),
          role: "tool",
          text: detail,
          callId,
          running: !terminal,
        });
        return;
      }
      if (type === "error" || data.is_error) {
        setWarming(false);
        setMsgs((prev) => [
          ...prev,
          { id: nextId(), role: "error", text: String(data.text ?? "") },
        ]);
      }
    },
    [upsertTool],
  );

  const loadEvents = useCallback(async (sessionId: string) => {
    setLoadingEvents(true);
    try {
      const res = await codeApi.listEvents(sessionId);
      const out: CodeMessage[] = [];
      const tools = new Map<string, number>();
      for (const e of res.events) {
        const p = e.payload ?? {};
        if (e.kind === "user_prompt") {
          out.push({ id: nextId(), role: "user", text: String(p.text ?? "") });
        } else if (e.kind === "agent_message") {
          out.push({
            id: nextId(),
            role: "assistant",
            text: String(p.text ?? ""),
          });
        } else if (e.kind === "thought") {
          out.push({
            id: nextId(),
            role: "thought",
            text: String(p.text ?? ""),
            open: true,
          });
        } else if (e.kind === "turn_error") {
          out.push({
            id: nextId(),
            role: "error",
            text: String(p.text ?? ""),
          });
        } else if (e.kind === "tool_start") {
          const item: CodeMessage = {
            id: nextId(),
            role: "tool",
            callId: String(p.call_id ?? ""),
            toolTitle: String(p.title ?? p.name ?? "tool"),
            toolKind: String(p.kind ?? "other"),
            text: p.detail != null ? String(p.detail) : "",
            running: false,
          };
          tools.set(item.callId ?? "", out.length);
          out.push(item);
        } else if (e.kind === "tool_update") {
          const idx = tools.get(String(p.call_id ?? ""));
          if (idx === undefined) continue;
          const detail = p.detail != null ? String(p.detail) : "";
          if (detail && detail !== "unknown") out[idx].text = detail;
          if (p.title) out[idx].toolTitle = String(p.title);
          const st = String(p.status ?? "");
          out[idx].failed = st === "failed";
          out[idx].running = !(
            st === "completed" ||
            st === "done" ||
            st === "failed"
          );
        }
      }
      setMsgs(out);
    } catch {
      /* history replay is best-effort */
    } finally {
      setLoadingEvents(false);
    }
  }, []);

  // -- session lifecycle -----------------------------------------------------

  const selectSession = useCallback(
    async (s: CodeSession) => {
      setCurrent(s);
      setPermission(null);
      setMsgs([]);
      setAttachments([]);
      if (s.model) setModelName(s.model);
      if (s.runner) setRunnerName(s.runner);
      await loadEvents(s.id);
    },
    [loadEvents],
  );

  const createSession = useCallback(async () => {
    if (runners.length === 0) {
      message.warning(t("code.noRunners"));
      return null;
    }
    setCreating(true);
    try {
      const s = await codeApi.createSession({
        runner: runnerName || runners[0].name,
        model: modelName || undefined,
      });
      setSessions((prev) => [s, ...prev]);
      setCurrent(s);
      setMsgs([]);
      setAttachments([]);
      return s;
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setCreating(false);
    }
  }, [runners, runnerName, modelName, message, t]);

  const closeSession = useCallback(
    async (s: CodeSession) => {
      try {
        await codeApi.closeSession(s.id);
        message.success(t("code.sessionClosed"));
        if (current?.id === s.id) {
          setCurrent(null);
          setMsgs([]);
          setAttachments([]);
        }
        setSessions((prev) => prev.filter((x) => x.id !== s.id));
      } catch (err) {
        message.error(err instanceof Error ? err.message : String(err));
      }
    },
    [current, message, t],
  );

  // -- turn execution --------------------------------------------------------

  const handleFinal = useCallback(
    (data: {
      status?: string;
      text?: string;
      permission?: CodePermission;
      event?: { text?: string } | null;
    }) => {
      setStreaming(false);
      setWarming(false);
      abortRef.current = null;
      setMsgs((prev) =>
        prev.map((m) =>
          m.running || m.streaming
            ? { ...m, running: false, streaming: false }
            : m,
        ),
      );
      const status = String(data.status ?? "");
      if (status === "permission_required" && data.permission) {
        setPermission(data.permission);
        return;
      }
      if (status === "error") {
        setMsgs((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "error",
            text: String(data.text ?? t("code.turnError")),
          },
        ]);
        return;
      }
      const ev = data.event;
      if (ev && ev.text) {
        const full = String(ev.text);
        setMsgs((prev) => {
          const seen = prev.some(
            (m) => m.role === "assistant" && m.text === full,
          );
          if (seen) return prev;
          return [...prev, { id: nextId(), role: "assistant", text: full }];
        });
      }
    },
    [t],
  );

  const sendPrompt = useCallback(
    async (text: string, optionId = "") => {
      if (!optionId && !text.trim()) return;
      let target = current;
      if (!target) {
        target = await createSession();
        if (!target) return;
      }
      const files = attachments.map((f) => f.path);
      setStreaming(true);
      setWarming(true);
      if (text.trim()) {
        setMsgs((prev) => [...prev, { id: nextId(), role: "user", text }]);
      }
      setInput("");
      setAttachments([]);
      abortRef.current = codeApi.streamPrompt(
        target.id,
        { text, option_id: optionId, attachments: files },
        applyLiveEvent,
        handleFinal,
        (err) => {
          setStreaming(false);
          setWarming(false);
          abortRef.current = null;
          setMsgs((prev) => [
            ...prev,
            {
              id: nextId(),
              role: "error",
              text: err instanceof Error ? err.message : String(err),
            },
          ]);
        },
      );
    },
    [current, attachments, applyLiveEvent, handleFinal, createSession],
  );

  const cancelStream = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);
    setWarming(false);
    if (current) {
      void codeApi.cancel(current.id).catch(() => undefined);
    }
  }, [current]);

  const resolvePermission = useCallback(
    (optionId: string) => {
      if (!current) return;
      setPermission(null);
      void sendPrompt("", optionId);
    },
    [current, sendPrompt],
  );

  // -- composer helpers ------------------------------------------------------

  const uploadFiles = useCallback(
    async (files: FileList | null) => {
      if (!current || !files || files.length === 0) return;
      setUploading(true);
      try {
        const res = await codeApi.uploadFiles(current.id, Array.from(files));
        setAttachments((prev) => [...prev, ...res.files]);
      } catch (err) {
        message.error(
          `${t("code.uploadFail")}: ${
            err instanceof Error ? err.message : String(err)
          }`,
        );
      } finally {
        setUploading(false);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [current, message, t],
  );

  const showPatchView = useCallback(async () => {
    if (!current) return;
    try {
      const res = await codeApi.getPatch(current.id);
      setPatch(res.patch);
      setShowPatch(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  }, [current, message]);

  const toggleThought = useCallback((id: string) => {
    setMsgs((prev) =>
      prev.map((m) => (m.id === id ? { ...m, open: !m.open } : m)),
    );
  }, []);

  const openFileMenu = useCallback(
    async (open: boolean) => {
      setFileOpen(open);
      if (!open || !current) return;
      try {
        const res = await codeApi.listFiles(current.id);
        setFileItems((res.files ?? []).slice(0, 60));
      } catch {
        setFileItems([]);
      }
    },
    [current],
  );

  const insertText = useCallback((snippet: string) => {
    setInput((prev) =>
      prev ? `${prev.replace(/\s*$/, "")} ${snippet} ` : `${snippet} `,
    );
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [msgs, warming]);

  // -- menus -----------------------------------------------------------------

  const templateItems = [
    {
      key: "review",
      label: t("code.tplReview"),
      prompt: t("code.tplReviewPrompt"),
    },
    {
      key: "security",
      label: t("code.tplSecurity"),
      prompt: t("code.tplSecurityPrompt"),
    },
    {
      key: "refactor",
      label: t("code.tplRefactor"),
      prompt: t("code.tplRefactorPrompt"),
    },
  ];

  const fileMenu = {
    items: fileItems.length
      ? fileItems.map((f) => ({
          key: f.path,
          label: f.path,
          onClick: () => insertText(`@${f.path}`),
        }))
      : [{ key: "empty", label: t("code.noFiles"), disabled: true }],
  };

  const skillMenu = {
    items: skillItems.length
      ? skillItems.map((s) => ({
          key: s.id,
          label: s.name,
          onClick: () => insertText(`@${s.name}`),
        }))
      : [{ key: "empty", label: t("code.noSkills"), disabled: true }],
  };

  // -- message renderer ------------------------------------------------------

  const renderMsg = (m: CodeMessage) => {
    if (m.role === "tool") {
      return (
        <div key={m.id} className={styles.toolCard}>
          <div className={styles.toolHead}>
            {m.failed ? (
              <CircleX size={13} className={styles.toolFail} />
            ) : m.running ? (
              <LoaderCircle size={13} className={styles.spin} />
            ) : (
              <CircleCheck size={13} className={styles.toolOk} />
            )}
            <Wrench size={12} />
            <span className={styles.toolTitle}>{m.toolTitle}</span>
            <Tag>{m.toolKind}</Tag>
          </div>
          {m.text ? <div className={styles.toolDetail}>{m.text}</div> : null}
        </div>
      );
    }
    if (m.role === "thought") {
      return (
        <div
          key={m.id}
          style={{
            border: "1px dashed var(--fn-border-subtle, rgba(127,127,127,.35))",
            borderRadius: 10,
            background: "var(--fn-bg-secondary, rgba(127,127,127,.06))",
            marginBottom: 10,
            overflow: "hidden",
          }}
        >
          <div
            onClick={() => toggleThought(m.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 10px",
              cursor: "pointer",
              color: "var(--fn-text-secondary)",
              fontSize: 12,
              userSelect: "none",
            }}
          >
            {m.open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <Brain size={13} />
            <span>{m.streaming ? t("code.thinking") : t("code.thought")}</span>
            {m.streaming ? (
              <LoaderCircle size={11} className={styles.spin} />
            ) : null}
            <span style={{ flex: 1 }} />
            <span style={{ color: "var(--fn-text-tertiary)" }}>
              {m.text.length}
            </span>
          </div>
          {m.open ? (
            <pre
              style={{
                margin: 0,
                padding: "0 12px 10px",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 12,
                lineHeight: 1.6,
                color: "var(--fn-text-tertiary)",
                fontFamily: CODE_MONO,
              }}
            >
              {m.text}
            </pre>
          ) : null}
        </div>
      );
    }
    if (m.role === "error") {
      return (
        <div
          key={m.id}
          style={{
            background: "var(--fn-color-error-bg, rgba(255,77,79,.08))",
            border:
              "1px solid var(--fn-color-error-border, rgba(255,77,79,.35))",
            color: "var(--fn-color-error, #cf1322)",
            borderRadius: 12,
            padding: "10px 14px",
            marginBottom: 10,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 13,
          }}
        >
          {m.text}
        </div>
      );
    }
    if (m.role === "user") {
      return (
        <div
          key={m.id}
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: 12,
          }}
        >
          <div
            style={{
              maxWidth: "78%",
              background: "var(--fn-color-brand, #4f46e5)",
              color: "var(--fn-color-on-brand, #fff)",
              borderRadius: "14px 14px 4px 14px",
              padding: "9px 14px",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontSize: 14,
              lineHeight: 1.65,
              boxShadow: "var(--fn-shadow-sm)",
            }}
          >
            {m.text}
          </div>
        </div>
      );
    }
    return (
      <div key={m.id} style={{ display: "flex", marginBottom: 12, gap: 8 }}>
        <div
          style={{
            flex: "0 0 auto",
            width: 22,
            height: 22,
            borderRadius: 11,
            marginTop: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--fn-bg-tertiary, rgba(127,127,127,.16))",
            color: "var(--fn-text-secondary)",
          }}
        >
          <Sparkles size={13} />
        </div>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            background: "var(--fn-assistant-bubble-bg, transparent)",
            border: "1px solid var(--fn-assistant-bubble-border, transparent)",
            borderRadius: 12,
            padding: "8px 12px",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 14,
            lineHeight: 1.7,
            color: "var(--fn-text-primary)",
          }}
        >
          {m.text}
          {m.streaming ? (
            <span
              style={{
                display: "inline-block",
                width: 7,
                height: 15,
                marginLeft: 3,
                verticalAlign: "text-bottom",
                background: "var(--fn-color-brand, #4f46e5)",
                borderRadius: 2,
                opacity: 0.85,
              }}
            />
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <PageShell title={t("code.title")}>
      <input
        ref={fileRef}
        type="file"
        multiple
        hidden
        accept={UPLOAD_ACCEPT}
        onChange={(e) => void uploadFiles(e.target.files)}
      />
      <div className={styles.layout}>
        <div className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <span>{t("code.sessions")}</span>
            <Button
              type="text"
              size="small"
              icon={<Plus size={14} />}
              onClick={() => void createSession()}
              loading={creating}
            />
          </div>
          <div className={styles.sessionList}>
            {sessions.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t("code.noSessions")}
              />
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  className={`${styles.sessionItem} ${
                    current?.id === s.id ? styles.active : ""
                  }`}
                  onClick={() => void selectSession(s)}
                >
                  <div className={styles.sessionMeta}>
                    <Tag color="blue">{s.runner}</Tag>
                    {s.model ? <Tag color="purple">{s.model}</Tag> : null}
                    <span className={styles.sessionStatus}>{s.status}</span>
                  </div>
                  <div className={styles.sessionId}>{s.id}</div>
                  <div className={styles.sessionActions}>
                    <Tooltip title={t("code.close")}>
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<Trash2 size={12} />}
                        onClick={(e) => {
                          e.stopPropagation();
                          void closeSession(s);
                        }}
                      />
                    </Tooltip>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className={styles.chat}>
          <div className={styles.chatHeader}>
            <Space size={6} wrap>
              {current ? <Tag color="geekblue">{current.runner}</Tag> : null}
              {current?.model ? (
                <Tag color="purple">{current.model}</Tag>
              ) : null}
              {warming ? (
                <Tag
                  icon={<LoaderCircle size={10} className={styles.spin} />}
                  color="processing"
                >
                  {t("code.warming")}
                </Tag>
              ) : null}
              {streaming ? (
                <Tag
                  icon={<LoaderCircle size={10} className={styles.spin} />}
                  color="processing"
                >
                  {t("code.streaming")}
                </Tag>
              ) : null}
              {current ? (
                <span className={styles.cwd}>{current.cwd}</span>
              ) : null}
            </Space>
            <Space>
              <Button
                size="small"
                icon={<RefreshCw size={12} />}
                onClick={() => current && void loadEvents(current.id)}
              >
                {t("code.refresh")}
              </Button>
              <Button
                size="small"
                icon={<CodeXml size={12} />}
                onClick={() => void showPatchView()}
              >
                {t("code.patch")}
              </Button>
            </Space>
          </div>

          <div className={styles.messages} ref={scrollRef}>
            {loadingEvents ? (
              <Empty description={t("code.loading")} />
            ) : msgs.length === 0 ? (
              <div className={styles.emptyCenter}>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("code.emptyChat")}
                />
              </div>
            ) : (
              msgs.map(renderMsg)
            )}
          </div>

          {attachments.length > 0 ? (
            <div className={styles.attachBar}>
              {attachments.map((f) => (
                <Tag
                  key={f.path}
                  closable
                  icon={<FileText size={11} />}
                  onClose={() =>
                    setAttachments((prev) =>
                      prev.filter((x) => x.path !== f.path),
                    )
                  }
                >
                  {f.name}
                </Tag>
              ))}
            </div>
          ) : null}

          <div className={styles.composer}>
            <div className={styles.composerTools}>
              <Dropdown
                trigger={["click"]}
                open={fileOpen}
                onOpenChange={(v) => void openFileMenu(v)}
                menu={fileMenu}
              >
                <Tooltip title={t("code.mention")}>
                  <Button size="small" type="text">
                    <span style={{ fontWeight: 700, fontSize: 14 }}>@</span>
                  </Button>
                </Tooltip>
              </Dropdown>
              <Tooltip title={t("code.upload")}>
                <Button
                  size="small"
                  type="text"
                  disabled={streaming || !current}
                  icon={
                    uploading ? (
                      <LoaderCircle size={14} className={styles.spin} />
                    ) : (
                      <Paperclip size={14} />
                    )
                  }
                  onClick={() => fileRef.current?.click()}
                />
              </Tooltip>
              <Dropdown
                trigger={["click"]}
                menu={{
                  items: templateItems.map((it) => ({
                    key: it.key,
                    label: it.label,
                    onClick: () => setInput(it.prompt),
                  })),
                }}
              >
                <Tooltip title={t("code.templates")}>
                  <Button
                    size="small"
                    type="text"
                    icon={<Lightbulb size={14} />}
                  />
                </Tooltip>
              </Dropdown>
              <span style={{ flex: 1 }} />
              {busy ? (
                <Tag
                  color="processing"
                  icon={<LoaderCircle size={10} className={styles.spin} />}
                >
                  {t("code.streaming")}
                </Tag>
              ) : null}
            </div>

            <TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("code.promptPlaceholder")}
              autoSize={{ minRows: 2, maxRows: 12 }}
              disabled={busy}
              style={{
                border: "none",
                boxShadow: "none",
                background: "transparent",
                padding: "2px 0",
                resize: "none",
                fontSize: 14,
                lineHeight: 1.65,
              }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  void sendPrompt(input);
                }
              }}
            />

            <div className={styles.composerFooter}>
              <Select
                size="small"
                value={runnerName || undefined}
                onChange={setRunnerName}
                placeholder={t("code.selectRunner")}
                options={runners.map((r) => ({ value: r.name, label: r.name }))}
                style={{ minWidth: 120 }}
              />
              <AutoComplete
                size="small"
                value={modelName}
                onChange={setModelName}
                options={modelOptions.map((m) => ({
                  value: m.id,
                  label: m.label,
                }))}
                placeholder={t("code.modelPlaceholder")}
                style={{ minWidth: 170 }}
                allowClear
                disabled={modelOptions.length === 0}
              />
              <Dropdown
                trigger={["click"]}
                open={skillOpen}
                onOpenChange={setSkillOpen}
                menu={skillMenu}
              >
                <Button size="small" icon={<Sparkles size={13} />}>
                  {t("code.skills")}
                </Button>
              </Dropdown>
              <span style={{ flex: 1 }} />
              {current ? (
                <Tooltip title={t("code.workspace")}>
                  <span className={styles.workspace}>
                    <FolderOpen size={12} />
                    <span>{current.cwd}</span>
                  </span>
                </Tooltip>
              ) : null}
              {busy ? (
                <Button
                  danger
                  icon={<Square size={14} />}
                  onClick={cancelStream}
                >
                  {t("code.stop")}
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<Send size={14} />}
                  onClick={() => void sendPrompt(input)}
                >
                  {t("code.send")}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      <Modal
        open={Boolean(permission)}
        title={t("code.permissionRequired")}
        onCancel={() => setPermission(null)}
        footer={null}
        destroyOnClose
      >
        {permission ? (
          <div className={styles.permission}>
            <div className={styles.permTitle}>
              {permission.title || permission.tool_name}
            </div>
            {permission.detail ? (
              <div className={styles.permDetail}>{permission.detail}</div>
            ) : null}
            <div className={styles.permTool}>
              <Tag>{permission.tool_name}</Tag>
              <Tag color="orange">{permission.tool_kind}</Tag>
            </div>
            <div className={styles.permOptions}>
              {permission.options.map((opt) => (
                <Button
                  key={opt.id}
                  type={opt.kind === "deny" ? "default" : "primary"}
                  danger={opt.kind === "deny"}
                  onClick={() => resolvePermission(opt.id)}
                >
                  {opt.name}
                </Button>
              ))}
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={showPatch}
        title={t("code.patch")}
        onCancel={() => setShowPatch(false)}
        footer={
          <Button onClick={() => setShowPatch(false)}>
            <X size={12} /> {t("code.close")}
          </Button>
        }
        width={800}
      >
        <pre className={styles.patch}>{patch || t("code.noChanges")}</pre>
      </Modal>
    </PageShell>
  );
}
