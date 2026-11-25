import { useCallback, useEffect, useState } from "react";
import { Button, Empty, Space, Spin } from "antd";
import { Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { request } from "../../../api/request";
import type { ProviderRow } from "../../Settings/Models/useProviders";
import { ProviderCard } from "../../Settings/Models/components/cards/ProviderCard";
import { CustomProviderModal } from "../../Settings/Models/components/modals/CustomProviderModal";

export default function AdminSharedModelsPage() {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await request<ProviderRow[]>("/admin/providers");
      if (!Array.isArray(rows)) {
        throw new Error("Unexpected API response shape from /admin/providers");
      }
      setProviders(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载共享供应商失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  return (
    <PageShell
      title={t("pageShell.adminSharedModels.title")}
      subtitle={t("pageShell.adminSharedModels.subtitle")}
      actions={
        <Space>
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => void fetchAll()}
          >
            {t("common.refresh")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            onClick={() => setAddOpen(true)}
          >
            {t("admin.sharedModels.addProvider")}
          </Button>
        </Space>
      }
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : error ? (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            color: "var(--fn-text-danger)",
          }}
        >
          {error}
          <div style={{ marginTop: 12 }}>
            <Button onClick={() => void fetchAll()}>{t("common.retry")}</Button>
          </div>
        </div>
      ) : providers.length === 0 ? (
        <Empty description={t("admin.sharedModels.addProvider")} />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 16,
            padding: "16px 0",
          }}
        >
          {providers.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              onSaved={fetchAll}
              isHover={hoveredCard === p.id}
              onMouseEnter={() => setHoveredCard(p.id)}
              onMouseLeave={() => setHoveredCard(null)}
              apiPrefix="/admin/providers"
            />
          ))}
        </div>
      )}

      <CustomProviderModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSaved={fetchAll}
        apiPrefix="/admin/providers"
      />
    </PageShell>
  );
}
