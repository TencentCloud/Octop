import { useState } from "react";
import { Alert, Button, Space, Tag } from "antd";
import { useTranslation } from "react-i18next";
import {
  openDesignApi,
  type DesignHealth,
} from "../../../api/modules/openDesign";
import { apiErrorMessage } from "../../../utils/apiError";

export function OpenDesignHealth({ instanceId }: { instanceId: string }) {
  const { t } = useTranslation();
  const [result, setResult] = useState<DesignHealth>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Button
        loading={loading}
        onClick={async () => {
          setLoading(true);
          setError(undefined);
          try {
            setResult(await openDesignApi.health(instanceId));
          } catch (e) {
            setError(apiErrorMessage(e, t("openDesignStudio.failed"), t));
          } finally {
            setLoading(false);
          }
        }}
      >
        {t("openDesignStudio.healthCheck")}
      </Button>
      {error && <Alert type="warning" message={error} />}
      {result && (
        <>
          <Space wrap>
            {["launch", "protocol", "daemon", "runtime", "resources"].map(
              (level) => {
                const item = result.levels.find((r) => r.level === level);
                return (
                  <Tag key={level} color={item?.ok ? "success" : "warning"}>
                    {t(`openDesignStudio.health.${level}`)} ·{" "}
                    {t(
                      item?.ok
                        ? "openDesignStudio.ready"
                        : "openDesignStudio.notReady",
                    )}
                    {typeof item?.count === "number" && ` (${item.count})`}
                  </Tag>
                );
              },
            )}
          </Space>
          <Alert
            type="info"
            showIcon
            message={t("openDesignStudio.unverified")}
            description={
              result.agents.length
                ? result.agents
                    .map(
                      (agent) =>
                        `${agent.name}${
                          agent.version ? ` · ${agent.version}` : ""
                        }`,
                    )
                    .join(" / ")
                : t("openDesignStudio.runtimeHint")
            }
          />
        </>
      )}
    </Space>
  );
}
