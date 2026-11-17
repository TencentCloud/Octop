/**
 * My models — the signed-in user's model pool and AUTO preference.
 *
 * Admin model configuration (providers, global keys, catalog) stays at
 * ``/admin/models``. This page only reads models the user may select
 * (``/providers/resolved``) and their own preferences, so every user can
 * manage the AUTO preferred model without provider-admin permissions.
 */
import { useCallback, useEffect, useState } from "react";
import { Empty, Spin } from "antd";
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { message } from "../../utils/antdMessage";
import { apiErrorMessage } from "../../utils/apiError";
import { providerApi } from "../../api/modules/provider";
import { preferencesApi } from "../../api/modules/preferences";
import type { ResolvedModel } from "../../api/types";
import { ActiveModelPool } from "../Settings/Models/components/sections/ActiveModelPool";

interface PreferredModelRef {
  provider_name: string;
  model: string;
}

const NO_PREFERENCE: PreferredModelRef = { provider_name: "", model: "" };

function preferredFromRef(ref: string | null | undefined): PreferredModelRef {
  const parts = (ref ?? "").trim().split("/");
  if (parts.length < 2) return NO_PREFERENCE;
  return {
    provider_name: parts[0],
    model: parts.slice(1).join("/"),
  };
}

export default function MyModelsPage() {
  const { t } = useTranslation();
  const [models, setModels] = useState<ResolvedModel[]>([]);
  const [preferred, setPreferred] = useState<PreferredModelRef>(NO_PREFERENCE);
  const [modelReasoning, setModelReasoning] = useState<
    Record<
      string,
      { mode: "auto" | "enabled" | "disabled"; effort?: string | null }
    >
  >({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [resolved, preferences] = await Promise.all([
        providerApi.listResolvedModels(),
        preferencesApi.get(),
      ]);
      setModels(resolved);
      setPreferred(preferredFromRef(preferences.preferred_model));
      setModelReasoning(preferences.model_reasoning ?? {});
    } catch (error) {
      message.error(apiErrorMessage(error, t("models.loadProvidersFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell
      title={t("nav.myModels")}
      subtitle={t("models.myModelsSubtitle")}
    >
      <Spin spinning={loading}>
        {models.length > 0 ? (
          <ActiveModelPool
            resolvedModels={models}
            activeModel={preferred}
            providers={[]}
            modelReasoning={modelReasoning}
            onSaved={load}
          />
        ) : (
          <Empty description={t("models.noModelsAvailable")} />
        )}
      </Spin>
    </PageShell>
  );
}
