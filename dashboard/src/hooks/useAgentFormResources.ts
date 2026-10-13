import { useEffect, useState } from "react";
import { providerApi } from "../api/modules/provider";
import { request } from "../api/request";
import { isAgentResolvableStorageKind } from "../pages/Admin/Storage/useStorageBackends";
import type { ModelPickerOption } from "../utils/modelOptions";
import { isBridgeAgentId } from "../utils/remoteExpert";

export interface AgentStorageBackend {
  id: number;
  name: string;
  kind: string;
  enabled: boolean;
  bucket?: string | null;
}

export interface AgentFormResources {
  models: ModelPickerOption[];
  modelsLoading: boolean;
  backends: AgentStorageBackend[];
  backendsLoading: boolean;
}

/**
 * Load resolved models + enabled storage backends for agent create/edit drawers.
 * Pass a Bridge shadow ``agentId`` so model lists hop to the peer.
 */
export function useAgentFormResources(
  enabled: boolean,
  agentId?: string | null,
): AgentFormResources {
  const [models, setModels] = useState<ModelPickerOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [backends, setBackends] = useState<AgentStorageBackend[]>([]);
  const [backendsLoading, setBackendsLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setModels([]);
      setBackends([]);
      return;
    }

    let cancelled = false;
    setModelsLoading(true);
    setBackendsLoading(true);

    void providerApi
      .listResolvedModels(agentId)
      .then((data) => {
        if (!cancelled) setModels(data as ModelPickerOption[]);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });

    // Storage backends are not in the Bridge tunnel allowlist.
    if (isBridgeAgentId(agentId)) {
      setBackends([]);
      setBackendsLoading(false);
    } else {
      void request<AgentStorageBackend[]>("/storage-backends")
        .then((data) => {
          if (!cancelled) {
            setBackends(
              data.filter(
                (b) => b.enabled && isAgentResolvableStorageKind(b.kind),
              ),
            );
          }
        })
        .catch(() => {
          if (!cancelled) setBackends([]);
        })
        .finally(() => {
          if (!cancelled) setBackendsLoading(false);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [enabled, agentId]);

  return { models, modelsLoading, backends, backendsLoading };
}
