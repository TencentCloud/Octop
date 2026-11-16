import { useState } from "react";
import { Alert, Button } from "antd";
import { useTranslation } from "react-i18next";
import { discoverMagpie } from "../../../../api/modules/magpie";
import type { MagpieDiscovery } from "../../../../api/modules/magpie";
import { MAGPIE_DEFAULT_BASE_URL } from "../magpie";

export function MagpieServerNotice() {
  const { t } = useTranslation();
  const [discovery, setDiscovery] = useState<MagpieDiscovery | null>(null);
  const [scanning, setScanning] = useState(false);

  const check = async () => {
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
  };

  const address = discovery?.base_url || MAGPIE_DEFAULT_BASE_URL;
  let status: string | null = null;
  if (scanning) {
    status = t("models.magpieDiscoveryScanning");
  } else if (discovery?.available) {
    status = t("models.magpieDiscoveryFound", {
      version: discovery.version || "—",
      address,
    });
  } else if (discovery && !discovery.available) {
    status = t("models.magpieDiscoveryMissing", { address });
  }

  return (
    <Alert
      style={{ marginBottom: 12 }}
      type={discovery?.available ? "success" : "info"}
      showIcon
      message={t("models.magpieDiscoveryTitle")}
      description={
        <div>
          {status ? <div>{status}</div> : null}
          <div>{t("models.magpieFailoverNote")}</div>
        </div>
      }
      action={
        <Button size="small" loading={scanning} onClick={() => void check()}>
          {discovery ? t("models.magpieRescan") : t("models.magpieCheck")}
        </Button>
      }
    />
  );
}
