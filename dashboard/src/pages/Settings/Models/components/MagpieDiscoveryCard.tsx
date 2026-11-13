import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Space } from "antd";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";
import { request } from "../../../../api/request";
import { discoverMagpie } from "../../../../api/modules/magpie";
import type { MagpieDiscovery } from "../../../../api/modules/magpie";
import { fetchProviderModels } from "../providerApi";
import type { ProviderRow } from "../useProviders";
import {
  MAGPIE_DEFAULT_BASE_URL,
  MAGPIE_LOCAL_API_KEY,
  MAGPIE_PRESET_NAME,
  initialMagpieModels,
  isMagpieProvider,
  magpieIntegrationExtra,
} from "../magpie";
import { ProviderConfigModal } from "./modals/ProviderConfigModal";

interface MagpieDiscoveryCardProps {
  discovery: MagpieDiscovery | null;
  scanning: boolean;
  providers: ProviderRow[];
  onRescan: () => void;
  onAdded: () => void | Promise<void>;
}

function isNameTaken(err: unknown): boolean {
  const text = err instanceof Error ? err.message : String(err);
  return text.includes("PROVIDER_NAME_TAKEN") || text.includes("UNIQUE");
}

export function MagpieDiscoveryCard({
  discovery,
  scanning,
  providers,
  onRescan,
  onAdded,
}: MagpieDiscoveryCardProps) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const addingRef = useRef(false);
  const [created, setCreated] = useState<ProviderRow | null>(null);
  const alreadyConfigured = providers.some((provider) =>
    isMagpieProvider(provider),
  );
  const address = discovery?.base_url || MAGPIE_DEFAULT_BASE_URL;

  const handleAdd = async () => {
    if (addingRef.current || alreadyConfigured || created) return;
    addingRef.current = true;
    setAdding(true);
    try {
      const fetched = await fetchProviderModels({
        kind: "openai",
        api_key: MAGPIE_LOCAL_API_KEY,
        base_url: address,
        name: MAGPIE_PRESET_NAME,
        extra_json: magpieIntegrationExtra(),
      });
      if (!fetched.ok) {
        message.error(
          t("models.fetchModelsFailed", { error: fetched.error ?? "unknown" }),
        );
        return;
      }
      const models = initialMagpieModels(fetched.models ?? []);
      if (!models) {
        message.warning(t("models.magpieNoModels"));
        return;
      }
      const row = await request<ProviderRow>("/admin/providers", {
        method: "POST",
        body: JSON.stringify({
          name: MAGPIE_PRESET_NAME,
          kind: "openai",
          base_url: address,
          api_key: MAGPIE_LOCAL_API_KEY,
          models,
          purpose: "chat",
          stream_usage: true,
          extra_json: magpieIntegrationExtra(),
        }),
      });
      setCreated(row);
      message.success(t("models.magpieAdded"));
      await onAdded();
    } catch (err) {
      if (isNameTaken(err)) {
        message.error(t("models.magpieNameTaken"));
        return;
      }
      message.error(
        err instanceof Error ? err.message : t("models.createFailedSimple"),
      );
    } finally {
      addingRef.current = false;
      setAdding(false);
    }
  };

  let description = t("models.magpieDiscoveryScanning");
  if (!scanning && discovery?.available) {
    description = t("models.magpieDiscoveryFound", {
      version: discovery.version || "—",
      address,
    });
  } else if (!scanning && discovery && !discovery.available) {
    description = t("models.magpieDiscoveryMissing", { address });
  }

  return (
    <>
      <Alert
        style={{ marginBottom: 12 }}
        type={discovery?.available ? "success" : "info"}
        showIcon
        message={t("models.magpieDiscoveryTitle")}
        description={
          <div>
            <div>{description}</div>
            <div>{t("models.magpieFailoverNote")}</div>
            {alreadyConfigured ? (
              <div>{t("models.magpieAlreadyAdded")}</div>
            ) : null}
          </div>
        }
        action={
          <Space>
            <Button size="small" loading={scanning} onClick={onRescan}>
              {t("models.magpieRescan")}
            </Button>
            {discovery?.available && !alreadyConfigured && !created ? (
              <Button
                size="small"
                type="primary"
                loading={adding}
                disabled={adding}
                onClick={() => void handleAdd()}
              >
                {t("models.magpieAdd")}
              </Button>
            ) : null}
          </Space>
        }
      />
      {created ? (
        <ProviderConfigModal
          provider={created}
          open
          apiPrefix="/admin/providers"
          onClose={() => setCreated(null)}
          onSaved={onAdded}
        />
      ) : null}
    </>
  );
}

export function useMagpieDiscovery(enabled: boolean) {
  const [discovery, setDiscovery] = useState<MagpieDiscovery | null>(null);
  const [scanning, setScanning] = useState(false);
  const started = useRef(false);

  const rescan = useCallback(async () => {
    setScanning(true);
    try {
      setDiscovery(await discoverMagpie());
    } catch {
      setDiscovery({
        available: false,
        base_url: MAGPIE_DEFAULT_BASE_URL,
        version: null,
      });
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled || started.current) return;
    started.current = true;
    void rescan();
  }, [enabled, rescan]);

  return { discovery, scanning, rescan: () => void rescan() };
}
