import { useEffect, useState } from "react";
import { Alert, Button, Collapse, Space, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { connectorsApi } from "../../../api/modules/connectors";
import { OpenDesignConfigImport } from "./OpenDesignConfigImport";
import type { OpenDesignLaunchConfig } from "./openDesignConfig";
import styles from "./index.module.less";

export function OpenDesignConnection({
  automatic,
  onImport,
  onAutomatic,
}: {
  automatic: boolean;
  onImport: (config: OpenDesignLaunchConfig) => void;
  onAutomatic: () => void;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState("loading");
  const [loading, setLoading] = useState(false);
  const refresh = async () => {
    setLoading(true);
    try {
      setState((await connectorsApi.openDesignLocalStatus()).state);
    } catch {
      setState("error");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);
  return (
    <Space
      direction="vertical"
      size={12}
      style={{ width: "100%", marginBottom: 24 }}
    >
      <Alert
        showIcon
        type={automatic && state !== "ready" ? "warning" : "success"}
        message={t(
          automatic
            ? "connectors.openDesignAutomatic"
            : "connectors.openDesignImported",
        )}
        description={t(
          automatic
            ? `connectors.openDesignLocal.${state}`
            : "connectors.openDesignImportedHint",
        )}
      />
      {automatic && (
        <Space wrap>
          <Button loading={loading} onClick={() => void refresh()}>
            {t("connectors.openDesignDetect")}
          </Button>
          {state !== "ready" && (
            <Button
              href="https://open-design.ai/zh/"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("connectors.openDesignInstall")}
            </Button>
          )}
          {loading && <Spin size="small" />}
        </Space>
      )}
      {!automatic && (
        <Button onClick={onAutomatic}>
          {t("connectors.openDesignUseAutomatic")}
        </Button>
      )}
      <Collapse
        className={styles.openDesignAdvanced}
        items={[
          {
            key: "import",
            label: t("connectors.openDesignAdvanced"),
            children: (
              <>
                <p className={styles.openDesignImportHint}>
                  {t("connectors.openDesignAdvancedHint")}
                </p>
                <OpenDesignConfigImport onImport={onImport} />
              </>
            ),
          },
        ]}
      />
    </Space>
  );
}
