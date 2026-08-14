import { useCallback, useEffect, useState } from "react";
import { connectorsApi } from "../../../api/modules/connectors";
import { providerApi } from "../../../api/modules/provider";
import { preferencesApi } from "../../../api/modules/preferences";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { request } from "../../../api/request";
import {
  knowledgeBasesApi,
  type KnowledgeBase,
} from "../../../api/modules/knowledgeBases";
import type { ResolvedModel } from "../../../api/types";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import { CONNECTORS_CHANGED_EVENT } from "../../Agent/Connectors/customMcpUtils";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { activeModelToRef } from "./useChatContextWindow";
import {
  hasSavedConnectors,
  loadSavedConnectors,
  loadSavedSkills,
  saveConnectors,
  saveSkills,
} from "../utils/chatStorage";
import { resolveInitialConnectors } from "../utils/resolveInitialConnectors";
import { withDefaultOpenKnowledgeBases } from "../utils/withDefaultOpenKnowledgeBases";

export function useChatComposerResources(
  resolvedAgentId: string | null | undefined,
  chatSkills: SkillSpec[],
  activeThreadId?: string | null,
  stickyModel?: string | null,
  stickyReasoningMode?: "auto" | "enabled" | "disabled" | null,
  stickyReasoningEffort?: string | null,
) {
  const user = useCurrentUser();
  const currentUserId = user?.id ?? null;
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [selectedKnowledgeBaseIds, setSelectedKnowledgeBaseIds] = useState<
    string[]
  >([]);
  const [chatKnowledgeBases, setChatKnowledgeBases] = useState<
    KnowledgeBase[] | undefined
  >(undefined);
  const [chatConnectors, setChatConnectors] = useState<
    {
      mcp_server_name: string;
      label: string;
      kind: string;
      default_open?: boolean;
    }[]
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

  // Auto = omit turn model; backend applies the expert default.
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
            default_open: i.default_open === true,
          }));
        setChatConnectors(options);
        const allowed = new Set(options.map((o) => o.mcp_server_name));
        const defaults = options
          .filter((o) => o.default_open)
          .map((o) => o.mcp_server_name);
        setSelectedConnectors((prev) =>
          resolveInitialConnectors({
            prev,
            saved: resolvedAgentId ? loadSavedConnectors(resolvedAgentId) : [],
            hasSaved: resolvedAgentId
              ? hasSavedConnectors(resolvedAgentId)
              : false,
            defaults,
            allowed,
          }),
        );
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
    setSelectedKnowledgeBaseIds([]);
    setChatKnowledgeBases(undefined);
    void knowledgeBasesApi
      .getCapability()
      .then((capability) => {
        if (cancelled || !capability.usable) return;
        return knowledgeBasesApi.list().then((bases) => {
          if (cancelled) return;
          setChatKnowledgeBases(bases);
          const ownedDefaults = bases
            .filter(
              (base) =>
                base.default_open &&
                currentUserId != null &&
                base.owner_user_id === currentUserId,
            )
            .map((base) => base.id);
          setSelectedKnowledgeBaseIds((previous) =>
            withDefaultOpenKnowledgeBases(previous, ownedDefaults),
          );
        });
      })
      .catch(() => {
        if (!cancelled) setChatKnowledgeBases(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [resolvedAgentId, currentUserId]);

  useEffect(() => {
    let cancelled = false;
    const loadModels = () => {
      void providerApi
        .listResolvedModels()
        .then((data) => {
          if (!cancelled) setAvailableModels(data);
        })
        .catch(() => {
          if (!cancelled) setAvailableModels([]);
        });
    };
    loadModels();
    const onFocus = () => loadModels();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
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

  const handleKnowledgeBaseIdsChange = useCallback((ids: string[]) => {
    setSelectedKnowledgeBaseIds(ids);
  }, []);

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
    selectedKnowledgeBaseIds,
    chatConnectors,
    chatKnowledgeBases,
    availableModels,
    activeModelRef,
    handleConnectorsChange,
    handleSkillsChange,
    handleKnowledgeBaseIdsChange,
  };
}
