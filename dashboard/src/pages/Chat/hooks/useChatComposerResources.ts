import { useCallback, useEffect, useState } from "react";
import { connectorsApi } from "../../../api/modules/connectors";
import { providerApi } from "../../../api/modules/provider";
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
  activeAgentDefaultModel?: string | null,
) {
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [chatConnectors, setChatConnectors] = useState<
    { mcp_server_name: string; label: string; kind: string }[]
  >([]);
  const [availableModels, setAvailableModels] = useState<ResolvedModel[]>([]);
  const [activeModelRef, setActiveModelRef] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  useEffect(() => {
    setSelectedModel(activeAgentDefaultModel ?? null);
  }, [resolvedAgentId, activeAgentDefaultModel]);

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

  return {
    selectedModel,
    setSelectedModel,
    selectedConnectors,
    selectedSkills,
    chatConnectors,
    availableModels,
    activeModelRef,
    handleConnectorsChange,
    handleSkillsChange,
  };
}
