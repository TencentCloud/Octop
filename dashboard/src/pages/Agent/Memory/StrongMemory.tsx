import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Skeleton } from "antd";
import { useTranslation } from "react-i18next";

import memoryApi from "../../../api/modules/memoryDashboard";
import { message } from "../../../utils/antdMessage";
import styles from "./StrongMemory.module.less";

export default function StrongMemory({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [exists, setExists] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    setSaving(false);
    setFailed(false);
    setContent("");
    setSavedContent("");
    memoryApi
      .getStrongMemory(agentId)
      .then((file) => {
        if (generation.current !== current) return;
        setContent(file.content);
        setSavedContent(file.content);
        setExists(file.exists);
      })
      .catch(() => {
        if (generation.current === current) setFailed(true);
      })
      .finally(() => {
        if (generation.current === current) setLoading(false);
      });
    return () => {
      generation.current = current + 1;
    };
  }, [agentId, retry]);

  const save = async () => {
    const current = generation.current;
    setSaving(true);
    try {
      const file = await memoryApi.putStrongMemory(agentId, content);
      if (generation.current !== current) return;
      setSavedContent(file.content);
      setExists(file.exists);
      message.success(
        t("memory.strong.saved", "强记忆已保存，将从下一轮聊天开始使用。"),
      );
    } catch {
      if (generation.current === current) {
        message.error(
          t("memory.strong.saveFailed", "保存失败，修改内容已保留，请重试。"),
        );
      }
    } finally {
      if (generation.current === current) setSaving(false);
    }
  };

  const disabled = loading || failed || saving;
  return (
    <div className={styles.strongMemory}>
      <Alert
        type="info"
        showIcon
        message={t(
          "memory.strong.contextNotice",
          "每次聊天都会将这里的全部内容加入上下文。",
        )}
        description={t(
          "memory.strong.description",
          "强记忆由你手动维护，适合填写始终需要参考的重要背景和约定。普通记忆按需召回，每次将相关记忆加入上下文。对 Agent 说“记住”会保存到普通记忆，不会改动这里。",
        )}
      />
      {failed && (
        <Alert
          type="error"
          showIcon
          message={t("memory.strong.loadFailed", "加载强记忆失败，请重试。")}
          action={
            <Button onClick={() => setRetry((value) => value + 1)}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      )}
      {loading ? (
        <Skeleton active paragraph={{ rows: 10 }} />
      ) : (
        <div className={styles.editor}>
          <label htmlFor={`strong-memory-${agentId}`}>
            {t("memory.strong.contentLabel", "强记忆内容")}
          </label>
          <Input.TextArea
            id={`strong-memory-${agentId}`}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            disabled={disabled}
            autoSize={{ minRows: 16, maxRows: 32 }}
            placeholder={t(
              "memory.strong.placeholder",
              "在这里填写每次聊天都需要参考的内容，支持 Markdown。",
            )}
            spellCheck={false}
          />
        </div>
      )}
      <div className={styles.actions}>
        <Button
          disabled={disabled || content === savedContent}
          onClick={() => setContent(savedContent)}
        >
          {t("memory.strong.discard", "撤销修改")}
        </Button>
        <Button
          type="primary"
          loading={saving}
          disabled={disabled || (exists && content === savedContent)}
          onClick={save}
        >
          {t("common.save", "保存")}
        </Button>
      </div>
    </div>
  );
}
