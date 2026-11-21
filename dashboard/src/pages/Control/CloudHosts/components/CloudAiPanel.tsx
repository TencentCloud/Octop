import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Dropdown, Input, Spin, Typography } from "antd";
import {
  ChevronRight,
  History,
  Plus,
  Send,
  Server,
  Square,
  Wrench,
} from "lucide-react";

import AssistantFrame, {
  readAssistantPlacement,
  type AssistantPlacement,
} from "../../../../components/AssistantFrame/AssistantFrame";

import {
  extractAskQuestions,
  isAskHitl,
  type HitlActionRequest,
} from "../../../../api/types/hitl";
import LazyMarkdown from "../../../../components/Markdown/LazyMarkdown";
import { useAgent } from "../../../../context/AgentContext";
import { useAgentThreadChat } from "../../../../hooks/useAgentThreadChat";
import { findCvmOpsAgent } from "../../../../hooks/useCvmOpsExpert";
import AskQuestionCard from "../../../Chat/components/AskQuestionCard";
import HitlApprovalCard from "../../../Chat/components/HitlApprovalCard";
import styles from "./CloudAiPanel.module.less";

/** 对话里出现的工具审批 / 提问消息片段。 */
type HitlSlice = {
  action_requests?: HitlActionRequest[];
  status?: "pending" | "approved" | "rejected";
  pending_id?: string;
};

/** 输入框上方的快捷气泡。文案要短，窄浮窗里一行放得下。 */
const QUICK_ASKS = [
  {
    label: "诊断报告",
    prompt:
      "请对当前实例出具云服务器诊断报告。先取云监控，需要定位挂载点或进程时再用 TAT。按诊断报告格式输出，并生成可归档的 HTML。未采集的数字不要编造。",
  },
  {
    label: "健康巡检",
    prompt:
      "请对当前实例做一次健康巡检。先取云监控，需要操作系统证据时用 TAT 下发一次巡检采集。按正常、关注、异常分级，只展开需要处理的项。",
  },
  {
    label: "根因诊断",
    prompt:
      "请对当前实例做根因诊断。先看云监控的变化时刻，解释不了再经 TAT 采集操作系统证据。给出结论、依据和已排除项。未采集的数字不要编造。",
  },
  {
    label: "修复方案",
    prompt:
      "请根据当前实例的异常给出修复方案。先定位根因，再给出动作、影响面、回滚方式和验证命令。中、高风险操作先等我确认，不要直接执行。",
  },
] as const;

export type InstanceBrief = {
  name: string;
  instance_id: string;
  region: string;
  zone: string;
  state: string;
  os_name: string;
  cpu: number;
  memory_gb: number;
  public_ips: string[];
  private_ips: string[];
};

/** 云服务器实例状态 → 中文标签；未知状态原样返回。 */
const STATE_LABEL: Record<string, string> = {
  RUNNING: "运行中",
  STOPPED: "已停止",
  STARTING: "启动中",
  STOPPING: "关机中",
  REBOOTING: "重启中",
  PENDING: "创建中",
  TERMINATED: "已销毁",
};

function stateLabel(state: string): string {
  return STATE_LABEL[state] ?? state;
}

type ParsedUserContext = {
  name?: string;
  id?: string;
  region?: string;
  zone?: string;
  state?: string;
  spec?: string;
};

/**
 * 用户消息里带着一段上下文头（`[当前云服务器]` + 名称/实例ID/地域...）。
 * 直接铺在气泡里是一大坨竖线文本，这里把它拆出来单独渲染成引用卡。
 * 同时兼容旧数据（`名称: x | 实例ID: y`）和新格式（每行一个字段）。
 */
function splitUserContext(raw: string): {
  ctx: ParsedUserContext | null;
  body: string;
} {
  if (!raw.startsWith("[当前云服务器]")) return { ctx: null, body: raw };

  const sep = raw.indexOf("\n\n");
  const head = sep === -1 ? raw : raw.slice(0, sep);
  const body = sep === -1 ? "" : raw.slice(sep + 2).trim();

  const fields: Record<string, string> = {};
  head
    .replace("[当前云服务器]", "")
    .split(/[|\n]/)
    .forEach((segment) => {
      const matched = segment.trim().match(/^([^:：]{1,8})[:：]\s*(.+)$/);
      if (matched) fields[matched[1].trim()] = matched[2].trim();
    });

  const regionPair = (fields["地域"] ?? "").split("/");
  const ctx: ParsedUserContext = {
    name: fields["名称"],
    id: fields["实例ID"],
    region: regionPair[0]?.trim() || undefined,
    zone: regionPair[1]?.trim() || undefined,
    state: fields["状态"],
    spec: fields["规格"],
  };
  if (!ctx.name && !ctx.id) return { ctx: null, body: raw };
  return { ctx, body };
}

/**
 * 云服务器会话的标题是首条消息全文（形如 `[当前云服务器] | 名称: xxx | 实例ID: ...`），
 * 直接放进历史下拉会挤成一行乱码。这里只取实例名。
 */
function threadLabel(thread: { title?: string | null }): string {
  const raw = (thread.title || "").trim();
  if (!raw) return "未命名对话";
  const named = raw.match(/名称[:：]\s*([^|\n]+)/);
  if (named?.[1]) {
    const name = named[1].trim();
    return name.length > 26 ? `${name.slice(0, 26)}…` : name;
  }
  const firstLine = raw.split("\n").find((line) => line.trim()) ?? raw;
  return firstLine.length > 30 ? `${firstLine.slice(0, 30)}…` : firstLine;
}

/** Tool step carried on an assistant/tool message (subset of ToolCallData). */
type ToolStepSlice = {
  name?: string;
  displayName?: string;
  output?: string;
  errorCode?: string;
  returnCode?: number;
};

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0
    ? `${mins} 分 ${String(secs).padStart(2, "0")} 秒`
    : `${secs} 秒`;
}

function toolStepLabel(tool: ToolStepSlice): string {
  const raw = (tool.displayName || tool.name || "工具").trim();
  return raw.length > 28 ? `${raw.slice(0, 28)}…` : raw;
}

function toolStepPreview(tool: ToolStepSlice): string {
  const failed =
    Boolean(tool.errorCode) ||
    (tool.returnCode != null && tool.returnCode !== 0);
  const body = (tool.errorCode || tool.output || "").split("\n")[0].trim();
  const text = body.length > 72 ? `${body.slice(0, 72)}…` : body;
  if (failed) return text ? `失败 · ${text}` : "失败";
  return text;
}

function textOf(message: unknown): string {
  if (!message || typeof message !== "object") return "";
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: unknown }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}

/** 渲染项：单条消息 / 纯文本块 / 一轮内的工具组。 */
type TurnItem =
  | { kind: "single"; message: unknown; index: number }
  | { kind: "text"; content: string; index: number }
  | { kind: "tools"; key: string; steps: ToolStepSlice[]; live: boolean };

/**
 * 按「一轮提问」聚合工具调用：同一轮里的所有工具步骤收进同一个折叠组。
 *
 * 之前按"连续工具消息"分组，一条 thinking / 空消息就把组劈成两半，结果一屏
 * 都是「已调用 2 次工具」的碎片。现在以 user 消息为界，一轮只留一个组。
 */
function groupTurns(messages: unknown[]): TurnItem[] {
  const items: TurnItem[] = [];
  const lastIndex = messages.length - 1;
  let group: {
    kind: "tools";
    key: string;
    steps: ToolStepSlice[];
    live: boolean;
  } | null = null;

  messages.forEach((message, index) => {
    const row = message as { role?: string; toolData?: ToolStepSlice };
    const text = textOf(message);

    if ((row.role ?? "") === "user") {
      group = null;
      items.push({ kind: "single", message, index });
      return;
    }

    // 审批卡片的 content 是空的，只带 hitlData。按正文过滤会把它整条丢掉，
    // 主对话能看到批准，工作台这边却像没发生过。
    if ((message as { hitlData?: unknown }).hitlData) {
      group = null;
      items.push({ kind: "single", message, index });
      return;
    }

    if (row.toolData) {
      if (!group) {
        group = {
          kind: "tools",
          key: `tools-${index}`,
          steps: [],
          live: false,
        };
        items.push(group);
      }
      group.steps.push(row.toolData);
      group.live = index === lastIndex;
      // 工具消息里夹带的正文单独渲染，不重复画步骤行
      if (text && row.role !== "tool") {
        items.push({ kind: "text", content: text, index });
      }
      return;
    }

    if (text) items.push({ kind: "single", message, index });
  });

  return items;
}

function stepFailed(step: ToolStepSlice): boolean {
  return (
    Boolean(step.errorCode) ||
    (step.returnCode != null && step.returnCode !== 0)
  );
}

function ToolStepRow({ step }: { step: ToolStepSlice }) {
  const label = toolStepLabel(step);
  const preview = toolStepPreview(step);
  return (
    <div
      className={`${styles.toolStep} ${
        stepFailed(step) ? styles.toolStepFailed : ""
      }`}
      title={step.output?.slice(0, 2000)}
    >
      <Wrench size={11} aria-hidden />
      <span className={styles.toolStepName}>{label}</span>
      {preview ? (
        <>
          <span className={styles.toolStepSep}>·</span>
          <span className={styles.toolStepPreview}>{preview}</span>
        </>
      ) : null}
    </div>
  );
}

/**
 * 一轮里的工具调用折叠条。
 * 执行中自动展开跟随进度，跑完自动收起（用户手动点过之后不再干预）。
 */
function ToolStepGroup({
  steps,
  live,
}: {
  steps: ToolStepSlice[];
  live: boolean;
}) {
  const [open, setOpen] = useState(live);
  const manual = useRef(false);

  useEffect(() => {
    if (!manual.current) setOpen(live);
  }, [live]);

  const failedCount = steps.filter(stepFailed).length;

  return (
    <div className={styles.toolGroup}>
      <button
        type="button"
        className={styles.toolGroupHead}
        onClick={() => {
          manual.current = true;
          setOpen((value) => !value);
        }}
        aria-expanded={open}
      >
        <Wrench size={11} aria-hidden />
        <span className={styles.toolGroupText}>
          已调用 {steps.length} 次工具
          {failedCount ? ` · ${failedCount} 次失败` : ""}
        </span>
        <ChevronRight
          size={13}
          className={`${styles.toolGroupChevron} ${
            open ? styles.toolGroupChevronOpen : ""
          }`}
        />
      </button>
      {open ? (
        <div className={styles.toolGroupBody}>
          {steps.map((step, index) => (
            <ToolStepRow key={`${step.name ?? "tool"}-${index}`} step={step} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

const CLOUD_ASSISTANT_PLACEMENT = "octop:cloud-ai-placement-v2";

export default function CloudAiPanel({
  instance,
  onClose,
  preferredAgentId = null,
  expertError = null,
  hidden = false,
}: {
  instance: InstanceBrief | null;
  onClose: () => void;
  /** 页面级已就绪的运维专家 id（由 useCvmOpsExpert 提供）。 */
  preferredAgentId?: string | null;
  /** 页面级正在创建专家，用于面板占位提示。 */
  expertEnsuring?: boolean;
  /** 专家初始化失败原因，展示在面板顶部。 */
  expertError?: string | null;
  /** 工作台切到其他页签时收起窗口，不卸载这段会话。 */
  hidden?: boolean;
}) {
  const { agents } = useAgent();
  const [agentId, setAgentId] = useState<string | null>(
    () => preferredAgentId ?? findCvmOpsAgent(agents)?.agent_id ?? null,
  );
  const {
    threadId,
    messages,
    isStreaming,
    send,
    cancelStream,
    historyHasMore,
    loadMoreHistory,
    booting,
    bootError,
    threads,
    startNewThread,
    selectThread,
    reload,
    resolveHitl,
  } = useAgentThreadChat(agentId, {
    hitlMode: "ask",
    pinKey: "octop:cloud-ai-thread",
  });

  // 页面级专家创建是异步的，就绪后同步进面板
  useEffect(() => {
    if (preferredAgentId) setAgentId(preferredAgentId);
  }, [preferredAgentId]);
  const [draft, setDraft] = useState("");
  // 只有「最后一条消息」上的待处理审批才应该锁住输入框：
  // 历史里早已失效的 pending 记录不该把整段会话永久卡死；
  // 没有 pending_id 的卡片服务端已经无法恢复，继续禁用输入等于死锁。
  const pendingPause = useMemo(() => {
    const last = messages[messages.length - 1] as
      | { hitlData?: HitlSlice }
      | undefined;
    const hitl = last?.hitlData;
    if (!hitl || (hitl.status ?? "pending") !== "pending") return false;
    if (hitl.pending_id) return true;
    // 提问类卡片即使没有 pending_id 也仍是「等人回答」，其余情况放行
    return isAskHitl(hitl.action_requests ?? []);
  }, [messages]);
  // 流式期间显示已用时：长工具链一轮要几分钟，没有计时会让人以为卡死
  const [elapsed, setElapsed] = useState(0);
  const turnStartedAt = useRef<number | null>(null);
  useEffect(() => {
    if (!isStreaming) {
      turnStartedAt.current = null;
      setElapsed(0);
      return;
    }
    turnStartedAt.current = turnStartedAt.current ?? Date.now();
    const tick = () => {
      const started = turnStartedAt.current;
      if (started != null)
        setElapsed(Math.floor((Date.now() - started) / 1000));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [isStreaming]);
  // 历史下拉只列出真正有消息的会话：空壳会话点进去就是一片空白
  const historyThreads = useMemo(
    () => threads.filter((thread) => thread.has_messages !== false),
    [threads],
  );
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages]);

  /**
   * 历史默认只取最近一页（25 条）。一轮运维常常调十几次工具，工具消息就能
   * 把一页占满，用户往上滑也看不到自己的提问。这里在打开会话时向前翻页，
   * 直到窗口顶部落在一条 user 消息（= 本轮起点）或没有更多历史。
   */
  const alignAttempts = useRef(0);
  useEffect(() => {
    alignAttempts.current = 0;
  }, [threadId]);

  useEffect(() => {
    if (booting || isStreaming || !messages.length) return;
    if (!historyHasMore) return;
    if (alignAttempts.current >= 8) return;
    const first = messages[0] as { role?: string } | undefined;
    if ((first?.role ?? "") === "user") return;
    alignAttempts.current += 1;
    void loadMoreHistory();
  }, [messages, booting, isStreaming, historyHasMore, loadMoreHistory]);

  const contextLine = useMemo(() => {
    if (!instance) return "";
    return [
      "[当前云服务器]",
      `名称: ${instance.name}`,
      `实例ID: ${instance.instance_id}`,
      `地域: ${instance.region}/${instance.zone}`,
      `状态: ${instance.state}`,
      `规格: ${instance.cpu} 核 / ${instance.memory_gb} GB`,
      `系统: ${instance.os_name}`,
      `公网IP: ${instance.public_ips[0] ?? "-"}`,
    ].join("\n");
  }, [instance]);

  const submit = () => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    send(contextLine ? `${contextLine}\n\n${text}` : text);
    setDraft("");
  };

  const ask = (prompt: string) => {
    if (isStreaming || pendingPause || !agentId) return;
    send(contextLine ? `${contextLine}\n\n${prompt}` : prompt);
  };

  const [placement, setPlacement] = useState<AssistantPlacement>(() =>
    readAssistantPlacement(CLOUD_ASSISTANT_PLACEMENT, "right"),
  );

  return (
    <AssistantFrame
      placement={placement}
      onPlacementChange={setPlacement}
      placementKey={CLOUD_ASSISTANT_PLACEMENT}
      storageKey="octop:cloud-ai"
      dock="inline"
      defaultDockWidth={400}
      hidden={hidden}
      title="腾讯云运维专家"
      bodyClassName={styles.panelFill}
      onClose={onClose}
      headerExtra={
        <>
          <Button
            size="small"
            type="text"
            title="新建对话"
            aria-label="新建对话"
            icon={<Plus size={14} />}
            disabled={!agentId || booting}
            onClick={() => void startNewThread()}
          />
          <Dropdown
            trigger={["click"]}
            menu={{
              items: historyThreads.length
                ? historyThreads.slice(0, 20).map((thread) => ({
                    key: thread.thread_id,
                    label: threadLabel(thread),
                  }))
                : [{ key: "__empty", label: "暂无历史对话", disabled: true }],
              onClick: ({ key }) => {
                if (key !== "__empty") void selectThread(key);
              },
            }}
          >
            <Button
              size="small"
              type="text"
              title="历史对话"
              aria-label="历史对话"
              icon={<History size={14} />}
              disabled={!agentId}
            />
          </Dropdown>
        </>
      }
    >
      {expertError ? (
        <div className={styles.expertError} role="alert">
          <span className={styles.expertErrorTitle}>运维专家未就绪</span>
          <span className={styles.expertErrorBody}>{expertError}</span>
        </div>
      ) : null}

      {/* 启动/加载失败以前是静默的：面板会停在一个空会话上，只能看到「没有历史」 */}
      {bootError ? (
        <div className={styles.expertError} role="alert">
          <span className={styles.expertErrorTitle}>会话加载失败</span>
          <span className={styles.expertErrorBody}>{bootError}</span>
          <Button size="small" type="link" onClick={reload}>
            重试
          </Button>
        </div>
      ) : null}

      <div className={styles.context}>
        {instance ? (
          <>
            <div className={styles.contextTitle}>已关联当前实例</div>
            <div className={styles.contextCard}>
              <span
                className={
                  instance.state === "RUNNING" ? styles.dotOn : styles.dotOff
                }
              />
              <div className={styles.contextMain}>
                <div className={styles.contextRow}>
                  <span className={styles.contextName} title={instance.name}>
                    {instance.name}
                  </span>
                  <span
                    className={styles.stateTag}
                    data-on={instance.state === "RUNNING" ? "1" : "0"}
                  >
                    {stateLabel(instance.state)}
                  </span>
                  <span className={styles.contextSpec}>
                    {instance.cpu}C · {instance.memory_gb}G
                  </span>
                </div>
                <div className={styles.contextMeta}>
                  <span className={styles.mono}>{instance.instance_id}</span>
                  <span className={styles.sep}>·</span>
                  <span>
                    {instance.region} / {instance.zone}
                  </span>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className={styles.contextBody}>
            在左侧选择一台实例，提问时会自动带上它的信息。
          </div>
        )}
      </div>

      <div className={styles.list} ref={listRef}>
        {booting ? (
          <div className={styles.booting}>
            <Spin size="small" />
            <span>正在载入会话…</span>
          </div>
        ) : messages.length ? (
          groupTurns(messages).map((item) => {
            if (item.kind === "tools") {
              return (
                <ToolStepGroup
                  key={item.key}
                  steps={item.steps}
                  live={isStreaming && item.live}
                />
              );
            }
            if (item.kind === "text") {
              return (
                <div key={`text-${item.index}`} className={styles.aiMsg}>
                  <LazyMarkdown
                    content={item.content}
                    isStreaming={
                      isStreaming && item.index === messages.length - 1
                    }
                  />
                </div>
              );
            }
            const { message, index } = item;
            const row = message as {
              role?: string;
              hitlData?: HitlSlice;
              toolData?: ToolStepSlice;
            };
            const role = row.role ?? "assistant";
            const text = textOf(message);

            // 工具调用步骤：运维一轮里往往十几次调用，只渲染文本会让界面
            // 静默几分钟，看起来就像卡死。这里把每一步显式打出来。
            if (row.toolData) {
              const label = toolStepLabel(row.toolData);
              const preview = toolStepPreview(row.toolData);
              const failed =
                Boolean(row.toolData.errorCode) ||
                (row.toolData.returnCode != null &&
                  row.toolData.returnCode !== 0);
              const step = (
                <div
                  className={`${styles.toolStep} ${
                    failed ? styles.toolStepFailed : ""
                  }`}
                  title={row.toolData.output?.slice(0, 2000)}
                >
                  <Wrench size={11} aria-hidden />
                  <span className={styles.toolStepName}>{label}</span>
                  {preview ? (
                    <span className={styles.toolStepPreview}>{preview}</span>
                  ) : null}
                </div>
              );
              // 纯工具消息只显示一行进度；带正文的助手消息保留正文
              if (!text || role === "tool") {
                return <div key={`tool-${index}`}>{step}</div>;
              }
              return (
                <div key={`tool-${index}`} className={styles.aiMsg}>
                  {step}
                  <LazyMarkdown
                    content={text}
                    isStreaming={isStreaming && index === messages.length - 1}
                  />
                </div>
              );
            }

            // 工具执行前的审批 / 待回答的提问，直接渲染成卡片而不是文本
            if (row.hitlData) {
              const actions = row.hitlData.action_requests ?? [];
              const hitlStatus = row.hitlData.status ?? "pending";

              if (isAskHitl(actions)) {
                const questions = extractAskQuestions(actions);
                const pendingId = row.hitlData.pending_id;
                // pending 时渲染成可交互的选项卡（选项 / 确认并提交 / 关闭），
                // 提交后走 respond 决策让专家继续，不再把卡片藏起来。
                const canAnswer =
                  hitlStatus === "pending" && Boolean(pendingId);
                return (
                  <div key={`hitl-${index}`} className={styles.aiMsg}>
                    <AskQuestionCard
                      questions={questions}
                      status={hitlStatus}
                      onSubmit={
                        canAnswer
                          ? (answer) =>
                              resolveHitl(
                                [{ type: "respond", message: answer }],
                                pendingId,
                              )
                          : undefined
                      }
                      onDismiss={
                        canAnswer
                          ? () =>
                              resolveHitl(
                                [
                                  {
                                    type: "respond",
                                    message:
                                      "用户关闭了提问，请按已有信息继续，不要再追问。",
                                  },
                                ],
                                pendingId,
                              )
                          : undefined
                      }
                    />
                  </div>
                );
              }

              return (
                <div key={`hitl-${index}`} className={styles.aiMsg}>
                  <HitlApprovalCard
                    actions={actions}
                    status={hitlStatus}
                    pendingId={row.hitlData.pending_id}
                    onDecision={(decisions, _policy, pendingId) =>
                      resolveHitl(decisions, pendingId)
                    }
                  />
                </div>
              );
            }

            if (!text) return null;
            if (role === "user") {
              const { ctx, body } = splitUserContext(text);
              return (
                <div key={`${role}-${index}`} className={styles.userMsg}>
                  {ctx ? (
                    <div className={styles.ctxQuote}>
                      <div className={styles.ctxQuoteHead}>
                        <Server size={11} aria-hidden />
                        <span className={styles.ctxQuoteName}>{ctx.name}</span>
                        {ctx.state ? (
                          <span
                            className={styles.stateTag}
                            data-on={ctx.state === "RUNNING" ? "1" : "0"}
                          >
                            {stateLabel(ctx.state)}
                          </span>
                        ) : null}
                      </div>
                      <div className={styles.ctxQuoteMeta}>
                        {[
                          ctx.id,
                          [ctx.region, ctx.zone].filter(Boolean).join("/"),
                          ctx.spec,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </div>
                  ) : null}
                  {body ? (
                    <span className={styles.userText}>{body}</span>
                  ) : null}
                </div>
              );
            }
            return (
              <div key={`${role}-${index}`} className={styles.aiMsg}>
                <LazyMarkdown
                  content={text}
                  isStreaming={isStreaming && index === messages.length - 1}
                />
              </div>
            );
          })
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            可以问我：这台机器负载是否正常？最近有没有异常？要不要重启？
          </Typography.Text>
        )}
        {isStreaming ? (
          <div className={styles.liveStatus}>
            <Spin size="small" />
            <span>
              {elapsed >= 20
                ? `执行中，已用时 ${formatElapsed(elapsed)} · 可点“停止”中断`
                : `正在执行… ${formatElapsed(elapsed)}`}
            </span>
          </div>
        ) : null}
      </div>

      <div className={styles.composer}>
        <div className={styles.quickAsks} role="group" aria-label="快捷询问">
          {QUICK_ASKS.map((item) => (
            <button
              key={item.label}
              type="button"
              className={styles.quickAsk}
              disabled={isStreaming || pendingPause || !agentId}
              onClick={() => ask(item.prompt)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <Input.TextArea
          autoSize={{ minRows: 2, maxRows: 5 }}
          value={draft}
          disabled={pendingPause}
          placeholder={
            pendingPause
              ? "请先处理上面的提问或审批，再继续对话"
              : instance
              ? `询问关于 ${instance.name} 的问题…`
              : "询问云服务器相关问题…"
          }
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className={styles.composerActions}>
          <span className={styles.hint}>
            {pendingPause ? "等待你在上方做出选择 · " : ""}Enter 发送 /
            Shift+Enter 换行
          </span>
          {isStreaming ? (
            <Button
              size="small"
              danger
              icon={<Square size={13} />}
              onClick={() => cancelStream()}
            >
              停止
            </Button>
          ) : pendingPause ? (
            // 等待审批时输入框是禁用的，这里必须留一个出口：
            // 审批卡片失联（换标签页 / 刷新）时用户否则只能干等。
            <Button
              size="small"
              onClick={() => {
                cancelStream();
                setDraft("");
              }}
            >
              取消本轮
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<Send size={13} />}
              disabled={!draft.trim() || !agentId}
              onClick={submit}
            >
              发送
            </Button>
          )}
        </div>
      </div>
    </AssistantFrame>
  );
}
