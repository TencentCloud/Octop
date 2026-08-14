/**
 * useProviders — admin model management hook.
 *
 * Fetches all providers and presets via the admin endpoints.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { providerApi } from "../../../api/modules/provider";
import { preferencesApi } from "../../../api/modules/preferences";
import type { ResolvedModel } from "../../../api/types";

export type { ResolvedModel };

export interface ProviderModel {
  id: string;
  name: string;
  enabled: boolean;
  input?: string[];
  thinking?: boolean | null;
  reasoning?: boolean;
  reasoning_config?: ResolvedModel["reasoning_config"];
  context_window?: number;
  max_tokens?: number;
  /** Embedding-only: excluded from chat picker and auto-route. */
  embedding?: boolean;
  task?: string;
}

export interface ProviderPresetModel {
  id: string;
  name: string;
  max_input_tokens?: number | null;
  context_window?: number | null;
  max_tokens?: number | null;
  input?: string[];
  reasoning?: boolean | null;
  description?: string | null;
}

export interface ProviderPreset {
  id: string;
  name: string;
  base_url: string;
  protocol: string;
  api_key_prefix: string;
  models: ProviderPresetModel[];
  vendor?: string;
  vendor_name?: string;
  variant?: string;
  provider_group?: string;
  provider_group_name?: string;
  provider_variant?: string;
  logo_id?: string;
  auth_method?: string;
}

export interface ProviderRow {
  id: number;
  name: string;
  kind: string;
  base_url: string | null;
  api_key: string | null;
  models: ProviderModel[];
  note: string | null;
  enabled: boolean;
}

export interface UseProvidersResult {
  providers: ProviderRow[];
  presets: ProviderPreset[];
  resolvedModels: ResolvedModel[];
  activeModel: { provider_name: string; model: string };
  modelReasoning: Record<
    string,
    { mode: "auto" | "enabled" | "disabled"; effort?: string | null }
  >;
  loading: boolean;
  error: string | null;
  fetchAll: () => Promise<void>;
}

export function useProviders(): UseProvidersResult {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [resolvedModels, setResolvedModels] = useState<ResolvedModel[]>([]);
  const [activeModel, setActiveModel] = useState({
    provider_name: "",
    model: "",
  });
  const [modelReasoning, setModelReasoning] = useState<
    UseProvidersResult["modelReasoning"]
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasLoadedRef = useRef(false);

  const fetchAll = useCallback(async () => {
    // Only show full-page loading on first load so open config modals
    // are not unmounted by subsequent refreshes.
    if (!hasLoadedRef.current) setLoading(true);
    setError(null);
    try {
      const settled = await Promise.allSettled([
        request<ProviderRow[]>("/admin/providers"),
        request<ProviderPreset[]>("/providers/presets"),
        providerApi.listResolvedModels(),
        request<{ provider_name: string; model: string }>(
          "/providers/active-model",
        ),
        preferencesApi.get(),
      ]);
      const rows =
        settled[0].status === "fulfilled" && Array.isArray(settled[0].value)
          ? settled[0].value
          : [];
      const presetList =
        settled[1].status === "fulfilled" && Array.isArray(settled[1].value)
          ? settled[1].value
          : [];
      const resolved =
        settled[2].status === "fulfilled" && Array.isArray(settled[2].value)
          ? settled[2].value
          : [];
      const active =
        settled[3].status === "fulfilled" ? settled[3].value : null;
      const preferences =
        settled[4].status === "fulfilled" ? settled[4].value : null;

      if (
        settled[0].status === "rejected" &&
        settled[1].status === "rejected"
      ) {
        throw settled[0].reason instanceof Error
          ? settled[0].reason
          : new Error(t("models.loadProvidersFailed"));
      }

      const normalized = rows.map((r) => ({
        ...r,
        models: Array.isArray(r.models) ? r.models : [],
      }));
      setProviders(normalized);
      setPresets(presetList);
      setResolvedModels(resolved);
      const preferredParts = (preferences?.preferred_model || "").split("/");
      setActiveModel(
        preferredParts.length > 1
          ? {
              provider_name: preferredParts[0],
              model: preferredParts.slice(1).join("/"),
            }
          : active && typeof active === "object"
          ? {
              provider_name: active.provider_name ?? "",
              model: active.model ?? "",
            }
          : { provider_name: "", model: "" },
      );
      setModelReasoning(preferences?.model_reasoning || {});
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : t("models.loadProvidersFailed");
      console.error("Failed to load providers:", err);
      setError(msg);
    } finally {
      hasLoadedRef.current = true;
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  return {
    providers,
    presets,
    resolvedModels,
    activeModel,
    modelReasoning,
    loading,
    error,
    fetchAll,
  };
}
