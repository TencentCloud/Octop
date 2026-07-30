/**
 * Per-agent channels hook.
 *
 * Drives octop's ``/agents/{aid}/channels`` CRUD + ``/test`` endpoints with
 * finnie-style state management (loading flag, in-place optimistic updates,
 * antd ``message`` toasts). Drop-in replacement for finnie's flat-config
 * ``useChannels`` — the page-level component need only swap the data shape
 * (a list of ``ChannelRow`` per agent, keyed by id, instead of a
 * ``ChannelKind → SingleChannelConfig`` map).
 */
import { useCallback } from "react";
import { message } from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { showApiError } from "../../../utils/showApiToast";

export interface ChannelRow {
  id: string;
  agent_id: string;
  kind: string;
  name: string;
  enabled: boolean;
  runtime?: {
    connected: boolean;
    error?: string | null;
    updated_at?: number;
  };
}

/** Full channel row including its ``config`` blob — populated by GET /channels/{id}. */
export interface ChannelDetail extends ChannelRow {
  config?: Record<string, unknown>;
}

export interface ChannelCreateBody {
  kind: string;
  name: string;
  config?: Record<string, unknown>;
}

export interface ChannelPatchBody {
  kind?: string;
  name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
}

export function useChannels(agentId: string | null) {
  const { t } = useTranslation();

  const {
    data: channels,
    loading,
    refresh: fetchChannels,
    setData: setChannels,
  } = useAsyncResource<ChannelRow[]>(
    [],
    async () => {
      const data = await request<ChannelRow[]>(`/agents/${agentId}/channels`);
      return data ?? [];
    },
    [agentId],
    {
      enabled: !!agentId,
      errorFallback: t("channels.loadFailed"),
      t,
      logLabel: "Channels",
    },
  );

  const getChannel = useCallback(
    async (channelId: string): Promise<ChannelDetail | null> => {
      if (!agentId) return null;
      try {
        return await request<ChannelDetail>(
          `/agents/${agentId}/channels/${channelId}`,
        );
      } catch (error) {
        console.error("[Channels] Failed to fetch channel:", error);
        showApiError(error, t("channels.loadDetailFailed"), t);
        return null;
      }
    },
    [agentId, t],
  );

  const createChannel = useCallback(
    async (body: ChannelCreateBody): Promise<ChannelRow | null> => {
      if (!agentId) return null;
      try {
        const created = await request<ChannelRow>(
          `/agents/${agentId}/channels`,
          {
            method: "POST",
            body: JSON.stringify(body),
          },
        );
        setChannels((prev) => [...prev, created]);
        message.success(t("channels.createdSuccess"));
        return created;
      } catch (error) {
        console.error("[Channels] Failed to create channel:", error);
        showApiError(error, t("channels.createFailed"), t);
        return null;
      }
    },
    [agentId, setChannels, t],
  );

  const updateChannel = useCallback(
    async (
      channelId: string,
      body: ChannelPatchBody,
    ): Promise<ChannelRow | null> => {
      if (!agentId) return null;
      try {
        const updated = await request<ChannelRow>(
          `/agents/${agentId}/channels/${channelId}`,
          {
            method: "PATCH",
            body: JSON.stringify(body),
          },
        );
        setChannels((prev) =>
          prev.map((c) => (c.id === channelId ? updated : c)),
        );
        return updated;
      } catch (error) {
        console.error("[Channels] Failed to update channel:", error);
        showApiError(error, t("channels.updateFailed"), t);
        return null;
      }
    },
    [agentId, setChannels, t],
  );

  const deleteChannel = useCallback(
    async (channelId: string): Promise<boolean> => {
      if (!agentId) return false;
      // Optimistic remove; restore from server fetch on failure.
      const previous = channels;
      setChannels((prev) => prev.filter((c) => c.id !== channelId));
      try {
        await request(`/agents/${agentId}/channels/${channelId}`, {
          method: "DELETE",
        });
        message.success(t("channels.deletedSuccess"));
        return true;
      } catch (error) {
        console.error("[Channels] Failed to delete channel:", error);
        setChannels(previous);
        showApiError(error, t("channels.deleteFailed"), t);
        return false;
      }
    },
    [agentId, channels, setChannels, t],
  );

  /** Probe a channel by starting/stopping it. Returns ``ok`` / ``error``. */
  const testChannel = useCallback(
    async (channelId: string): Promise<{ ok: boolean; error?: string }> => {
      if (!agentId) return { ok: false, error: "no agent" };
      try {
        return await request<{ ok: boolean; error?: string }>(
          `/agents/${agentId}/channels/${channelId}/test`,
          { method: "POST" },
        );
      } catch (error) {
        console.error("[Channels] Failed to probe channel:", error);
        return {
          ok: false,
          error: error instanceof Error ? error.message : "test failed",
        };
      }
    },
    [agentId],
  );

  /** Probe draft credentials without saving the channel row. */
  const probeChannelConfig = useCallback(
    async (
      kind: string,
      config: Record<string, unknown>,
    ): Promise<{ ok: boolean; error?: string }> => {
      if (!agentId) return { ok: false, error: "no agent" };
      try {
        return await request<{ ok: boolean; error?: string }>(
          `/agents/${agentId}/channels/probe`,
          {
            method: "POST",
            body: JSON.stringify({ kind, config }),
          },
        );
      } catch (error) {
        console.error("[Channels] Failed to probe channel config:", error);
        return {
          ok: false,
          error: error instanceof Error ? error.message : "probe failed",
        };
      }
    },
    [agentId],
  );

  return {
    channels,
    loading,
    fetchChannels,
    getChannel,
    createChannel,
    updateChannel,
    deleteChannel,
    testChannel,
    probeChannelConfig,
  };
}
