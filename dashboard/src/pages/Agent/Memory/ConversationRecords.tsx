import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Pagination,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { Eye, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import {
  CHAT_HISTORY_PAGE_SIZE,
  octopThreadsApi,
  type OctopThread,
} from "../../../api/modules/octopThreads";
import {
  extractText,
  filterDialogueHistoryMessages,
} from "../../../utils/messageParser";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { showConfirmModal } from "../../../utils/confirmModal";
import {
  formatMessageTime,
  formatServerDateTime,
  resolveMessageTimestampMs,
} from "../../../utils/formatMessageTime";
import styles from "./index.module.less";

const { Text } = Typography;

const THREAD_LIST_PAGE_SIZE = 20;
const THREAD_LIST_PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

interface ConversationRecordsProps {
  agentId: string;
}

interface HistoryMessage {
  role: string;
  content: unknown;
  id?: string;
  timestamp?: number;
}

function formatThreadTime(epochSec: number, timeZone: string): string {
  return formatServerDateTime(epochSec, timeZone);
}

function channelLabel(channel: string, t: (key: string) => string): string {
  const key = `memory.conversationChannel.${channel}`;
  const translated = t(key);
  return translated === key ? channel : translated;
}

interface ConversationThreadCardProps {
  thread: OctopThread;
  selected: boolean;
  deleting: boolean;
  channelLabel: string;
  timeZone: string;
  onView: (thread: OctopThread) => void;
  onDelete: (thread: OctopThread) => void;
}

function ConversationThreadCard({
  thread,
  selected,
  deleting,
  channelLabel,
  timeZone,
  onView,
  onDelete,
}: ConversationThreadCardProps) {
  const { t } = useTranslation();
  const title = thread.title?.trim() || t("memory.untitledThread");

  return (
    <div
      className={`${styles.conversationCard} ${
        selected ? styles.conversationCardSelected : ""
      }`}
    >
      <div className={styles.conversationCardHeader}>
        <span className={styles.conversationCardTitle}>{title}</span>
        <Tag className={styles.channelTag}>{channelLabel}</Tag>
      </div>
      <Text code className={styles.conversationCardThreadId}>
        {thread.thread_id}
      </Text>
      <div className={styles.conversationCardMeta}>
        <div className={styles.conversationCardMetaRow}>
          <span className={styles.conversationCardMetaLabel}>
            {t("memory.conversationColumns.lastActive")}
          </span>
          <span className={styles.conversationTimeCell}>
            {formatThreadTime(thread.last_active, timeZone)}
          </span>
        </div>
        <div className={styles.conversationCardMetaRow}>
          <span className={styles.conversationCardMetaLabel}>
            {t("memory.conversationColumns.createdAt")}
          </span>
          <span className={styles.conversationTimeCell}>
            {formatThreadTime(thread.created_at, timeZone)}
          </span>
        </div>
      </div>
      <div className={styles.conversationCardActions}>
        <Button
          type="default"
          size="small"
          icon={<Eye size={15} />}
          onClick={() => void onView(thread)}
        >
          {t("common.view")}
        </Button>
        <Button
          type="default"
          size="small"
          danger
          icon={<Trash2 size={15} />}
          loading={deleting}
          onClick={() => onDelete(thread)}
        >
          {t("common.delete")}
        </Button>
      </div>
    </div>
  );
}

export default function ConversationRecords({
  agentId,
}: ConversationRecordsProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const serverTimezone = useServerTimezone();
  const [threads, setThreads] = useState<OctopThread[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [selectedThread, setSelectedThread] = useState<OctopThread | null>(
    null,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyNextOffset, setHistoryNextOffset] = useState(0);
  const [messages, setMessages] = useState<HistoryMessage[]>([]);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const scrollHeightBeforePrependRef = useRef<number | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [cardPage, setCardPage] = useState(1);
  const [cardPageSize, setCardPageSize] = useState(THREAD_LIST_PAGE_SIZE);

  const loadThreads = useCallback(async () => {
    setListLoading(true);
    try {
      const list = await octopThreadsApi.list(agentId, 100);
      list.sort((a, b) => b.last_active - a.last_active);
      setThreads(list);
    } catch {
      setThreads([]);
      message.error(t("memory.loadFailed"));
    } finally {
      setListLoading(false);
    }
  }, [agentId, t]);

  const resetHistoryState = useCallback(() => {
    setMessages([]);
    setHistoryHasMore(false);
    setHistoryNextOffset(0);
    setHistoryLoadingMore(false);
    scrollHeightBeforePrependRef.current = null;
  }, []);

  useEffect(() => {
    setSelectedThread(null);
    setDrawerOpen(false);
    resetHistoryState();
    setCardPage(1);
    void loadThreads();
  }, [agentId, loadThreads, resetHistoryState]);

  const fetchThreadHistory = useCallback(
    async (threadId: string, offset: number) => {
      const history = await octopThreadsApi.history(agentId, threadId, {
        limit: CHAT_HISTORY_PAGE_SIZE,
        offset,
      });
      return {
        messages: (history.messages ?? []) as HistoryMessage[],
        hasMore: Boolean(history.has_more),
        nextOffset: offset + CHAT_HISTORY_PAGE_SIZE,
      };
    },
    [agentId],
  );

  const openThread = useCallback(
    async (thread: OctopThread) => {
      setSelectedThread(thread);
      setDrawerOpen(true);
      setHistoryLoading(true);
      resetHistoryState();
      try {
        const page = await fetchThreadHistory(thread.thread_id, 0);
        setMessages(page.messages);
        setHistoryHasMore(page.hasMore);
        setHistoryNextOffset(page.nextOffset);
      } catch {
        resetHistoryState();
        message.error(t("memory.conversationLoadFailed"));
      } finally {
        setHistoryLoading(false);
      }
    },
    [fetchThreadHistory, resetHistoryState, t],
  );

  const loadMoreHistory = useCallback(async () => {
    if (
      !selectedThread ||
      historyLoading ||
      historyLoadingMore ||
      !historyHasMore
    ) {
      return;
    }

    const drawerBody =
      messagesContainerRef.current?.closest(".ant-drawer-body");
    if (drawerBody instanceof HTMLElement) {
      scrollHeightBeforePrependRef.current = drawerBody.scrollHeight;
    }

    setHistoryLoadingMore(true);
    try {
      const page = await fetchThreadHistory(
        selectedThread.thread_id,
        historyNextOffset,
      );
      setMessages((prev) => [...page.messages, ...prev]);
      setHistoryHasMore(page.hasMore);
      setHistoryNextOffset(page.nextOffset);
    } catch {
      scrollHeightBeforePrependRef.current = null;
      message.error(t("memory.conversationLoadFailed"));
    } finally {
      setHistoryLoadingMore(false);
    }
  }, [
    selectedThread,
    historyLoading,
    historyLoadingMore,
    historyHasMore,
    historyNextOffset,
    fetchThreadHistory,
    t,
  ]);

  useLayoutEffect(() => {
    if (scrollHeightBeforePrependRef.current === null) return;
    const drawerBody =
      messagesContainerRef.current?.closest(".ant-drawer-body");
    if (drawerBody instanceof HTMLElement) {
      const delta =
        drawerBody.scrollHeight - scrollHeightBeforePrependRef.current;
      drawerBody.scrollTop += delta;
    }
    scrollHeightBeforePrependRef.current = null;
  }, [messages]);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedThread(null);
    resetHistoryState();
  }, [resetHistoryState]);

  const handleDelete = useCallback(
    async (thread: OctopThread) => {
      setDeletingId(thread.thread_id);
      try {
        await octopThreadsApi.delete(agentId, thread.thread_id);
        message.success(t("memory.conversationDeleteSuccess"));
        if (selectedThread?.thread_id === thread.thread_id) {
          closeDrawer();
        }
        setThreads((prev) =>
          prev.filter((row) => row.thread_id !== thread.thread_id),
        );
      } catch {
        message.error(t("memory.conversationDeleteFailed"));
      } finally {
        setDeletingId(null);
      }
    },
    [agentId, closeDrawer, selectedThread?.thread_id, t],
  );

  const confirmDelete = useCallback(
    (thread: OctopThread) => {
      showConfirmModal(
        {
          title: t("memory.conversationDeleteConfirm"),
          okText: t("common.delete"),
          cancelText: t("common.cancel"),
          okButtonProps: { danger: true },
          onOk: async () => {
            await handleDelete(thread);
          },
        },
        { isMobile },
      );
    },
    [handleDelete, isMobile, t],
  );

  const roleLabel = (role: string) => {
    const key = `memory.conversationRole.${role}`;
    const translated = t(key);
    return translated === key ? role : translated;
  };

  const visibleMessages = useMemo(
    () => filterDialogueHistoryMessages(messages),
    [messages],
  );

  const paginatedThreads = useMemo(() => {
    const maxPage = Math.max(1, Math.ceil(threads.length / cardPageSize));
    const page = Math.min(cardPage, maxPage);
    const start = (page - 1) * cardPageSize;
    return threads.slice(start, start + cardPageSize);
  }, [threads, cardPage, cardPageSize]);

  const columns: ColumnsType<OctopThread> = useMemo(
    () => [
      {
        title: t("memory.conversationColumns.threadId"),
        dataIndex: "thread_id",
        width: "28%",
        ellipsis: { showTitle: true },
        render: (id: string) => (
          <Tooltip title={id}>
            <Text code className={styles.conversationThreadId}>
              {id}
            </Text>
          </Tooltip>
        ),
      },
      {
        title: t("memory.conversationColumns.title"),
        dataIndex: "title",
        width: "26%",
        ellipsis: { showTitle: true },
        render: (title: string | null) => (
          <span className={styles.conversationTitleCell}>
            {title?.trim() || t("memory.untitledThread")}
          </span>
        ),
      },
      {
        title: t("memory.conversationColumns.channel"),
        dataIndex: "channel_type",
        width: 110,
        render: (channel: string) => (
          <Tag className={styles.channelTag}>{channelLabel(channel, t)}</Tag>
        ),
      },
      {
        title: t("memory.conversationColumns.lastActive"),
        dataIndex: "last_active",
        width: 168,
        render: (ts: number) => (
          <span className={styles.conversationTimeCell}>
            {formatThreadTime(ts, serverTimezone)}
          </span>
        ),
        sorter: (a, b) => a.last_active - b.last_active,
        defaultSortOrder: "descend",
      },
      {
        title: t("memory.conversationColumns.createdAt"),
        dataIndex: "created_at",
        width: 168,
        render: (ts: number) => (
          <span className={styles.conversationTimeCell}>
            {formatThreadTime(ts, serverTimezone)}
          </span>
        ),
        sorter: (a, b) => a.created_at - b.created_at,
      },
      {
        title: t("memory.conversationColumns.actions"),
        key: "actions",
        width: 112,
        fixed: "right",
        render: (_, row) => (
          <Space size={4} onClick={(e) => e.stopPropagation()}>
            <Tooltip title={t("common.view")}>
              <Button
                type="text"
                size="small"
                icon={<Eye size={15} />}
                aria-label={t("common.view")}
                onClick={() => void openThread(row)}
              />
            </Tooltip>
            <Popconfirm
              title={t("memory.conversationDeleteConfirm")}
              okText={t("common.delete")}
              cancelText={t("common.cancel")}
              okButtonProps={{ danger: true }}
              onConfirm={() => void handleDelete(row)}
            >
              <Tooltip title={t("common.delete")}>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<Trash2 size={15} />}
                  loading={deletingId === row.thread_id}
                  aria-label={t("common.delete")}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [deletingId, handleDelete, openThread, serverTimezone, t],
  );

  const threadPaginationTotal = (total: number) =>
    t("memory.conversationTotal", { count: total });

  const toolbar = (
    <div className={styles.conversationHeader}>
      <div>
        <h3 className={styles.conversationTitle}>
          {t("memory.conversationHistory")}
        </h3>
        <p className={styles.conversationDesc}>
          {t("memory.conversationHistoryDesc")}
        </p>
      </div>
      <Tooltip title={t("common.refresh")}>
        <Button
          type="text"
          size="small"
          className={styles.conversationRefreshBtn}
          onClick={() => void loadThreads()}
          icon={<RefreshCw size={14} />}
          loading={listLoading}
          aria-label={t("common.refresh")}
        />
      </Tooltip>
    </div>
  );

  const mobileList = listLoading ? (
    <div className={styles.conversationCardLoading}>
      <Spin />
    </div>
  ) : threads.length === 0 ? (
    <Empty description={t("memory.noConversations")} />
  ) : (
    <>
      <div className={styles.conversationCardGrid}>
        {paginatedThreads.map((thread) => (
          <ConversationThreadCard
            key={thread.thread_id}
            thread={thread}
            selected={selectedThread?.thread_id === thread.thread_id}
            deleting={deletingId === thread.thread_id}
            channelLabel={channelLabel(thread.channel_type, t)}
            timeZone={serverTimezone}
            onView={openThread}
            onDelete={confirmDelete}
          />
        ))}
      </div>
      <div className={styles.conversationCardPagination}>
        <Pagination
          size="small"
          current={cardPage}
          pageSize={cardPageSize}
          total={threads.length}
          showSizeChanger
          pageSizeOptions={[...THREAD_LIST_PAGE_SIZE_OPTIONS]}
          showTotal={threadPaginationTotal}
          onChange={(page, size) => {
            setCardPage(page);
            if (size !== cardPageSize) {
              setCardPageSize(size);
              setCardPage(1);
            }
          }}
        />
      </div>
    </>
  );

  return (
    <>
      <div className={styles.conversationRecords}>
        {toolbar}
        {isMobile ? (
          mobileList
        ) : (
          <Card className={styles.conversationTableCard} bordered={false}>
            <Table<OctopThread>
              className={styles.conversationTable}
              rowKey="thread_id"
              loading={listLoading}
              dataSource={threads}
              columns={columns}
              tableLayout="fixed"
              scroll={{ x: 980 }}
              locale={{ emptyText: t("memory.noConversations") }}
              pagination={{
                pageSize: THREAD_LIST_PAGE_SIZE,
                showSizeChanger: true,
                pageSizeOptions: THREAD_LIST_PAGE_SIZE_OPTIONS.map(String),
                showTotal: threadPaginationTotal,
              }}
              rowClassName={(row) =>
                selectedThread?.thread_id === row.thread_id
                  ? styles.conversationRowSelected
                  : ""
              }
            />
          </Card>
        )}
      </div>

      <Drawer
        open={drawerOpen}
        title={
          selectedThread
            ? selectedThread.title?.trim() || t("memory.untitledThread")
            : t("memory.conversationDetail")
        }
        width={isMobile ? "100%" : 480}
        placement="right"
        onClose={closeDrawer}
        destroyOnClose
        className={styles.conversationDrawer}
      >
        {selectedThread ? (
          <div className={styles.conversationDrawerMeta}>
            <span className={styles.conversationDrawerMetaLabel}>
              {t("memory.conversationColumns.threadId")}
            </span>
            <Text
              type="secondary"
              className={styles.conversationDrawerThreadId}
              copyable
            >
              {selectedThread.thread_id}
            </Text>
          </div>
        ) : null}
        {historyLoading ? (
          <div className={styles.conversationDrawerLoading}>
            <Spin />
          </div>
        ) : visibleMessages.length === 0 ? (
          <Empty description={t("memory.noConversationMessages")} />
        ) : (
          <div
            ref={messagesContainerRef}
            className={styles.conversationMessages}
          >
            {historyHasMore || historyLoadingMore ? (
              <div className={styles.conversationLoadMore}>
                <Button
                  type="link"
                  size="small"
                  loading={historyLoadingMore}
                  disabled={!historyHasMore || historyLoadingMore}
                  onClick={() => void loadMoreHistory()}
                >
                  {historyLoadingMore
                    ? t("memory.loadingEarlierMessages")
                    : t("memory.loadEarlierMessages")}
                </Button>
              </div>
            ) : null}
            {visibleMessages.map((msg, index) => {
              const text = extractText(msg.content).trim();
              const role = msg.role || "unknown";
              const timeLabel = (() => {
                const tsMs = resolveMessageTimestampMs(msg.timestamp);
                return tsMs > 0 ? formatMessageTime(tsMs, serverTimezone) : "";
              })();
              return (
                <div
                  key={msg.id ?? `${role}-${index}`}
                  className={`${styles.conversationMessage} ${
                    styles[`conversationRole_${role}`] ?? ""
                  }`}
                >
                  <div className={styles.conversationMessageHeader}>
                    <span className={styles.conversationMessageRole}>
                      {roleLabel(role)}
                    </span>
                    {timeLabel ? (
                      <span className={styles.conversationMessageTime}>
                        {timeLabel}
                      </span>
                    ) : null}
                  </div>
                  <div className={styles.conversationMessageBody}>
                    {role === "assistant" || role === "user" ? (
                      <Markdown
                        content={text}
                        className={styles.conversationMarkdown}
                      />
                    ) : (
                      <pre className={styles.conversationMessagePre}>
                        {text}
                      </pre>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Drawer>
    </>
  );
}
