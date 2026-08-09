import { useCallback, useEffect, useState } from "react";
import { connectorsApi } from "../../../api/modules/connectors";
import { providerApi } from "../../../api/modules/provider";
import { preferencesApi } from "../../../api/modules/preferences";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { request } from "../../../api/request";
import type { ResolvedModel } from "../../../api/types";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import { CONNECTORS_CHANGED_EVENT } from "../../Agent/Connectors/customMcpUtils";
import { activeModelToRef } from "./useChatContextWindow";
import {
  loadSavedConnectors,
  loadSavedSkills,
  saveConnectors,
  saveSkills,
} from "../utils/chatStorage";

export function useChatComposerResources(
  resolvedAgentId: string | null | undefined,
  chatSkills: SkillSpec[],
  activeThreadId?: string | null,
  stickyModel?: string | null,
  stickyReasoningMode?: "auto" | "enabled" | "disabled" | null,
  stickyReasoningEffort?: string | null,
) {
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [chatConnectors, setChatConnectors] = useState<
    { mcp_server_name: string; label: string; kind: string }[]
  >([]);
  const [availableModels, setAvailableModels] = useState<ResolvedModel[]>([]);
  const [activeModelRef, setActiveModelRef] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [preferredModel, setPreferredModel] = useState<string | null>(null);
  const [modelReasoning, setModelReasoning] = useState<
    Record<
      string,
      { mode: "auto" | "enabled" | "disabled"; effort?: string | null }
    >
  >({});
  const [reasoningMode, setReasoningMode] = useState<
    "auto" | "enabled" | "disabled"
  >("auto");
  const [reasoningEffort, setReasoningEffort] = useState<string | null>(null);
  const [conversationOverrides, setConversationOverrides] = useState<
    Record<
      string,
      {
        model: string | null;
        mode: "auto" | "enabled" | "disabled";
        effort: string | null;
      }
    >
  >({});

  useEffect(() => {
    const local = activeThreadId
      ? conversationOverrides[activeThreadId]
      : undefined;
    setSelectedModel(
      local ? local.model : stickyModel || preferredModel || null,
    );
  }, [
    resolvedAgentId,
    activeThreadId,
    stickyModel,
    preferredModel,
    conversationOverrides,
  ]);

  useEffect(() => {
    const defaults = selectedModel ? modelReasoning[selectedModel] : undefined;
    const capability = availableModels.find(
      (model) => `${model.provider_name}/${model.model}` === selectedModel,
    )?.reasoning_config;
    const local = activeThreadId
      ? conversationOverrides[activeThreadId]
      : undefined;
    setReasoningMode(
      local
        ? local.mode
        : stickyReasoningMode ||
            defaults?.mode ||
            capability?.default_mode ||
            "auto",
    );
    setReasoningEffort(
      local
        ? local.effort
        : stickyReasoningEffort ||
            defaults?.effort ||
            capability?.default_effort ||
            null,
    );
  }, [
    activeThreadId,
    selectedModel,
    stickyReasoningMode,
    stickyReasoningEffort,
    modelReasoning,
    availableModels,
    conversationOverrides,
  ]);

  useEffect(() => {
    let cancelled = false;
    const loadConnectors = () => {
      void connectorsApi.listInstances().then((instances) => {
        if (cancelled) return;
        const options = (instances ?? [])
          .filter((i) => i.status === "active" && i.has_credentials)
          .map((i) => ({
            mcp_server_name: i.mcp_server_name,
            label: i.display_name,
            kind: i.kind,
          }));
        setChatConnectors(options);
        const allowed = new Set(options.map((o) => o.mcp_server_name));
        setSelectedConnectors((prev) => {
          const saved = resolvedAgentId
            ? loadSavedConnectors(resolvedAgentId)
            : [];
          const base = prev.length > 0 ? prev : saved;
          return base.filter((n) => allowed.has(n));
        });
      });
    };
    loadConnectors();
    const onFocus = () => loadConnectors();
    window.addEventListener("focus", onFocus);
    window.addEventListener(CONNECTORS_CHANGED_EVENT, loadConnectors);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(CONNECTORS_CHANGED_EVENT, loadConnectors);
    };
  }, [resolvedAgentId]);

  useEffect(() => {
    if (!resolvedAgentId) {
      setSelectedSkills([]);
      return;
    }
    const allowed = new Set(
      chatSkills.filter((s) => s.enabled).map((s) => s.slug),
    );
    setSelectedSkills((prev) => {
      const saved = loadSavedSkills(resolvedAgentId);
      const base = prev.length > 0 ? prev : saved;
      return base.filter((n) => allowed.has(n));
    });
  }, [resolvedAgentId, chatSkills]);

  useEffect(() => {
    let cancelled = false;
    void providerApi
      .listResolvedModels()
      .then((data) => {
        if (!cancelled) setAvailableModels(data);
      })
      .catch(() => {
        if (!cancelled) setAvailableModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void preferencesApi
      .get()
      .then((preferences) => {
        if (cancelled) return;
        setPreferredModel(preferences.preferred_model || null);
        setModelReasoning(preferences.model_reasoning || {});
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadActiveModel = () => {
      void request<{ provider_name: string; model: string }>(
        "/providers/active-model",
      )
        .then((active) => {
          if (!cancelled) setActiveModelRef(activeModelToRef(active));
        })
        .catch(() => {
          if (!cancelled) setActiveModelRef(null);
        });
    };
    loadActiveModel();
    const onFocus = () => loadActiveModel();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const handleConnectorsChange = useCallback(
    (names: string[]) => {
      setSelectedConnectors(names);
      if (resolvedAgentId) saveConnectors(resolvedAgentId, names);
    },
    [resolvedAgentId],
  );

  const handleSkillsChange = useCallback(
    (names: string[]) => {
      setSelectedSkills(names);
      if (resolvedAgentId) saveSkills(resolvedAgentId, names);
    },
    [resolvedAgentId],
  );

  const handleModelChange = useCallback(
    (model: string | null) => {
      setSelectedModel(model);
      const defaults = model ? modelReasoning[model] : undefined;
      const capability = availableModels.find(
        (item) => `${item.provider_name}/${item.model}` === model,
      )?.reasoning_config;
      const nextMode = defaults?.mode || capability?.default_mode || "auto";
      const nextEffort = defaults?.effort || capability?.default_effort || null;
      setReasoningMode(nextMode);
      setReasoningEffort(nextEffort);
      if (activeThreadId) {
        setConversationOverrides((current) => ({
          ...current,
          [activeThreadId]: {
            model,
            mode: nextMode,
            effort: nextEffort,
          },
        }));
      }
      if (resolvedAgentId && activeThreadId) {
        void octopThreadsApi.patch(resolvedAgentId, activeThreadId, {
          model_ref: model,
          reasoning_mode: nextMode,
          reasoning_effort: nextEffort,
        });
      }
    },
    [activeThreadId, availableModels, modelReasoning, resolvedAgentId],
  );

  const handleReasoningChange = useCallback(
    (mode: "auto" | "enabled" | "disabled", effort: string | null) => {
      setReasoningMode(mode);
      setReasoningEffort(effort);
      if (activeThreadId) {
        setConversationOverrides((current) => ({
          ...current,
          [activeThreadId]: {
            model: selectedModel,
            mode,
            effort,
          },
        }));
      }
      if (resolvedAgentId && activeThreadId) {
        void octopThreadsApi.patch(resolvedAgentId, activeThreadId, {
          reasoning_mode: mode,
          reasoning_effort: effort,
        });
      }
    },
    [activeThreadId, resolvedAgentId, selectedModel],
  );

  return {
    selectedModel,
    setSelectedModel: handleModelChange,
    reasoningMode,
    reasoningEffort,
    handleReasoningChange,
    selectedConnectors,
    selectedSkills,
    chatConnectors,
    availableModels,
    activeModelRef,
    handleConnectorsChange,
    handleSkillsChange,
  };
}
