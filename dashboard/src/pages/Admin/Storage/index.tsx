/**
 * Admin Storage Management page — /admin/storage
 *
 * Tab A, my storage: configured storage backends in a card grid.
 * Tab B, supported types: preset backend type cards; click to configure.
 *
 * Mirrors the Experts page two-tab pattern.
 */
import { useMemo, useState } from "react";
import { Spin, Tabs } from "antd";
import { HardDrive } from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import {
  useStorageBackends,
  STORAGE_TYPE_DEFS,
  type StorageTypeDef,
} from "./useStorageBackends";
import { StorageBackendCard } from "./StorageBackendCard";
import { StorageTypeCard } from "./StorageTypeCard";
import { StorageBackendDrawer } from "./StorageBackendModal";
import styles from "./storage.module.less";

type TabKey = "my" | "types";

export default function AdminStoragePage() {
  const { t } = useTranslation();
  const { backends, loading, error, fetchAll } = useStorageBackends();

  const [activeTab, setActiveTab] = useState<TabKey>("my");
  const [newBackendName, setNewBackendName] = useState<string | null>(null);

  // Create modal state
  const [addOpen, setAddOpen] = useState(false);
  const [presetKind, setPresetKind] = useState<string | undefined>(undefined);

  const handleTypeCardClick = (typeDef: StorageTypeDef) => {
    setPresetKind(typeDef.kind);
    setAddOpen(true);
  };

  const handleCreated = async (name?: string) => {
    await fetchAll();
    setActiveTab("my");
    if (name) {
      setNewBackendName(name);
      setTimeout(() => setNewBackendName(null), 1000);
    }
  };

  // Set of configured kinds for the configured badge on type cards.
  const configuredKinds = useMemo(
    () => new Set(backends.map((b) => b.kind)),
    [backends],
  );

  // ── Tab: my storage ───────────────────────────────────────────

  const myStorageContent = useMemo(() => {
    if (loading) {
      return (
        <div className={styles.loadingState}>
          <Spin />
        </div>
      );
    }
    if (error) {
      return (
        <div className={styles.emptyState}>
          <HardDrive size={44} style={{ color: "var(--fn-text-tertiary)" }} />
          <div className={styles.emptyTitle}>{error}</div>
          <button
            className={styles.emptyAction}
            onClick={() => void fetchAll()}
          >
            {t("common.retry")}
          </button>
        </div>
      );
    }
    if (backends.length === 0) {
      return (
        <div className={styles.emptyState}>
          <HardDrive size={44} style={{ color: "var(--fn-text-tertiary)" }} />
          <div className={styles.emptyTitle}>{t("storage.emptyMyStorage")}</div>
          <div className={styles.emptyHint}>
            {t("storage.emptyMyStorageHint")}
          </div>
          <button
            className={styles.emptyAction}
            onClick={() => setActiveTab("types")}
          >
            {t("storage.goToTypes")}
          </button>
        </div>
      );
    }
    return (
      <>
        <div className={styles.gridToolbar}>
          <span className={styles.gridCount}>
            {t("storage.totalBackends", { count: backends.length })}
          </span>
          <button
            className={styles.toolbarBtn}
            onClick={() => setActiveTab("types")}
          >
            {t("storage.addFromTypes")}
          </button>
        </div>
        <div className={styles.cardGrid}>
          {backends.map((b) => (
            <StorageBackendCard
              key={b.id}
              backend={b}
              onSaved={fetchAll}
              isNew={newBackendName === b.name}
            />
          ))}
        </div>
      </>
    );
  }, [backends, loading, error, fetchAll, newBackendName, t]);

  // ── Tab: supported types ──────────────────────────────────────

  const typesContent = useMemo(
    () => (
      <div className={styles.cardGrid}>
        {STORAGE_TYPE_DEFS.map((typeDef) => (
          <StorageTypeCard
            key={typeDef.kind}
            typeDef={typeDef}
            isConfigured={configuredKinds.has(typeDef.kind)}
            onClick={handleTypeCardClick}
          />
        ))}
      </div>
    ),
    [configuredKinds],
  );

  return (
    <PageShell.FillTabs
      title={t("storage.pageTitle")}
      subtitle={t("storage.pageSubtitle")}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as TabKey)}
        items={[
          {
            key: "my",
            label: t("storage.myStorage"),
            children: myStorageContent,
          },
          {
            key: "types",
            label: t("storage.supportedTypes"),
            children: typesContent,
          },
        ]}
      />

      <StorageBackendDrawer
        open={addOpen}
        onClose={() => {
          setAddOpen(false);
          setPresetKind(undefined);
        }}
        onSaved={handleCreated}
        presetKind={presetKind}
      />
    </PageShell.FillTabs>
  );
}
