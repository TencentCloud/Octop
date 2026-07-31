/**
 * Hook that manages the skill recording workflow within the chat page.
 *
 * Detects localized "end" and "confirm" user messages to orchestrate:
 * - end -> stop recording, generate skill, push skill preview to chat
 * - confirm -> create skill via API, push confirmation message
 *
 * The hook intercepts outgoing user messages and, if they match trigger
 * keywords, performs the workflow actions instead of (or in addition to)
 * sending the message to the agent.
 */
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { browserApi } from "../../../api/modules/browser";
import { request } from "../../../api/request";
import * as chatStore from "../hooks/chatStore";

import { message as antMessage } from "@/utils/antdMessage";

interface UseSkillRecordingWorkflowParams {
  agentId: string | null;
  threadId: string | null;
  browserRecording: boolean;
  browserRecordingId: string | null;
  setBrowserRecording: (v: boolean) => void;
  setBrowserRecordingId: (v: string | null) => void;
  setBrowserLastRecordingId: (v: string | null) => void;
}

// Keywords that trigger "stop recording and generate skill"
const END_KEYWORDS = ["结束", "end", "stop recording", "结束录制"];

// Keywords that trigger "confirm and apply skill"
const CONFIRM_KEYWORDS = ["确认", "confirm", "ok", "确认应用", "apply"];

export function useSkillRecordingWorkflow({
  agentId,
  threadId,
  browserRecording,
  browserRecordingId,
  setBrowserRecording,
  setBrowserRecordingId,
  setBrowserLastRecordingId,
}: UseSkillRecordingWorkflowParams) {
  const { t } = useTranslation();
  const [pendingSkillContent, setPendingSkillContent] = useState<string | null>(
    null,
  );
  const [pendingSkillName, setPendingSkillName] = useState<string | null>(null);
  const [pendingSkillRecordingId, setPendingSkillRecordingId] = useState<
    string | null
  >(null);
  const workflowBusyRef = useRef(false);

  /** Check if user text matches an end keyword while recording is active. */
  const isEndRecordingCommand = useCallback(
    (text: string): boolean => {
      const normalized = text.trim().toLowerCase();
      return (
        browserRecording &&
        END_KEYWORDS.some((kw) => normalized === kw.toLowerCase())
      );
    },
    [browserRecording],
  );

  /** Check if user text matches a confirm keyword while a skill is pending confirmation. */
  const isConfirmSkillCommand = useCallback(
    (text: string): boolean => {
      const normalized = text.trim().toLowerCase();
      return (
        !!pendingSkillContent &&
        CONFIRM_KEYWORDS.some((kw) => normalized === kw.toLowerCase())
      );
    },
    [pendingSkillContent],
  );

  /** Stop recording, generate skill, and push preview to chat. */
  const handleEndRecording = useCallback(async () => {
    if (workflowBusyRef.current) return;
    workflowBusyRef.current = true;

    try {
      // Use the combined stop-and-generate-skill endpoint
      const data = await browserApi.stopAndGenerateSkill({
        recordingId: browserRecordingId,
        name: threadId ? `chat-${threadId}` : "skill-recording",
        generateSteps: true,
      });

      const recordingId = data.recordingId ?? browserRecordingId;
      setBrowserRecording(false);
      setBrowserRecordingId(null);
      if (recordingId) {
        setBrowserLastRecordingId(recordingId);
      }

      if (data.skillContent) {
        // Store the skill content for later confirmation
        setPendingSkillContent(data.skillContent);
        setPendingSkillName(data.skillName ?? recordingId ?? "browser-skill");
        setPendingSkillRecordingId(recordingId ?? null);

        // Push a preview message to chat
        const previewLines = data.skillContent.split("\n").slice(0, 20);
        const previewText = previewLines.join("\n");
        const truncationNotice =
          data.skillContent.split("\n").length > 20
            ? `\n\n... (共 ${
                data.skillContent.split("\n").length
              } 行，完整内容将在确认后保存)`
            : "";

        chatStore.appendPushMessage(
          `✅ 录制完成！已生成 ${data.steps ?? 0} 个回放步骤。\n\n` +
            `📝 **技能脚本预览：**\n\n${previewText}${truncationNotice}\n\n` +
            `回复"确认"即可应用此技能，之后可以一键回放相同操作流程。`,
        );
      } else {
        chatStore.appendPushMessage(
          `✅ 录制完成！已生成 ${data.steps ?? 0} 个回放步骤。\n\n` +
            `⚠️ 技能脚本生成失败，请稍后重试或手动生成。`,
        );
      }

      antMessage.success(
        t(
          "skillRecord.recordingStopped",
          `录制完成，已生成 ${data.steps ?? 0} 个回放步骤`,
        ),
      );
    } catch (err) {
      antMessage.error(
        err instanceof Error
          ? err.message
          : t("skillRecord.stopFailed", "停止录制失败"),
      );
    } finally {
      workflowBusyRef.current = false;
    }
  }, [
    browserRecordingId,
    threadId,
    setBrowserRecording,
    setBrowserRecordingId,
    setBrowserLastRecordingId,
    t,
  ]);

  /** Confirm and apply the pending skill. */
  const handleConfirmSkill = useCallback(async () => {
    if (
      !pendingSkillContent ||
      !pendingSkillName ||
      !agentId ||
      workflowBusyRef.current
    )
      return;
    workflowBusyRef.current = true;

    try {
      // Create the skill via the skills API
      const result = await request<{
        slug: string;
        name: string;
        enabled: boolean;
      }>(`/agents/${agentId}/skills`, {
        method: "POST",
        body: JSON.stringify({
          name: pendingSkillName,
          content: pendingSkillContent,
        }),
      });

      // Clear pending state
      setPendingSkillContent(null);
      setPendingSkillName(null);
      setPendingSkillRecordingId(null);

      // Push confirmation message to chat
      chatStore.appendPushMessage(
        `🎉 技能 **${result.name || pendingSkillName}** 已成功应用！\n\n` +
          `之后可以通过聊天输入相关指令，一键回放相同的浏览器操作流程。`,
      );

      antMessage.success(
        t(
          "skillRecord.skillApplied",
          `技能 "${result.name || pendingSkillName}" 已成功应用`,
        ),
      );
    } catch (err) {
      antMessage.error(
        err instanceof Error
          ? err.message
          : t("skillRecord.applyFailed", "应用技能失败"),
      );
    } finally {
      workflowBusyRef.current = false;
    }
  }, [pendingSkillContent, pendingSkillName, agentId, t]);

  /**
   * Intercepts outgoing user messages. If the message matches a workflow
   * keyword, performs the workflow action and returns true
   * (meaning the caller should NOT also send it as a regular chat message).
   * Otherwise returns false.
   */
  const interceptUserMessage = useCallback(
    (text: string): boolean => {
      if (isEndRecordingCommand(text)) {
        void handleEndRecording();
        // Do not send the end keyword as a chat message to the agent.
        return true;
      }
      if (isConfirmSkillCommand(text)) {
        void handleConfirmSkill();
        // Do not send the confirm keyword as a chat message to the agent.
        return true;
      }
      return false;
    },
    [
      isEndRecordingCommand,
      isConfirmSkillCommand,
      handleEndRecording,
      handleConfirmSkill,
    ],
  );

  return {
    interceptUserMessage,
    isEndRecordingCommand,
    isConfirmSkillCommand,
    pendingSkillContent,
    pendingSkillName,
    pendingSkillRecordingId,
  };
}
