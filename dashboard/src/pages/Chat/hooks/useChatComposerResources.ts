import { useCallback, useEffect, useState } from "react";
import { connectorsApi } from "../../../api/modules/connectors";
import { providerApi } from "../../../api/modules/provider";
import { request } from "../../../api/request";
import type { ResolvedModel } from "../../../api/types";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import { CONNECTORS_CHANGED_EVENT } from "../../Agent/Connectors/customMcpUtils";
import { modelOptionValue } from "../../../utils/modelOptions";
import { activeModelToRef } from "./useChatContextWindow";
import {
  hasSavedConnectors,
  loadSavedConnectors,
  loadSavedSkills,
  saveConnectors,
  saveSkills,
} from "../utils/chatStorage";
import { resolveInitialConnectors } from "../utils/resolveInitialConnectors";

export function useChatComposerResources(
  resolvedAgentId: string | null | undefined,
  chatSkills: SkillSpec[],
) {
  const [selectedConnectors, setSelectedConnectors] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
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

  // Auto = omit turn model; backend applies the expert default.
  useEffect(() => {
    setSelectedModel(null);
  }, [resolvedAgentId]);

  // Drop composer picks that disappeared from the catalog (model deleted).
  useEffect(() => {
    if (!selectedModel || availableModels.length === 0) return;
    const allowed = new Set(availableModels.map(modelOptionValue));
    if (!allowed.has(selectedModel)) {
      setSelectedModel(null);
    }
  }, [availableModels, selectedModel]);

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
