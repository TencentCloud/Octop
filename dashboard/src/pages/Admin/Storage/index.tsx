/**
 * Admin Storage Management page — /admin/storage
 *
 * Tab A, my storage: configured storage backends in a card grid.
 * Tab B, supported types: preset backend type cards; click to configure.
 *
 * Mirrors the Experts page two-tab pattern.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Spin, Tabs } from "antd";
import { HardDrive, LayoutGrid } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import PageShell from "../../../layouts/PageShell";
import TabLabel from "../../../components/TabLabel";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import StreamSetupGuide from "../../../components/StreamSetupGuide/StreamSetupGuide";
import { ResourceVisibilityFields } from "../../../components/ResourceVisibilityFields";
import type { ResourceVisibilityMode } from "../../../api/modules/userGroups";
import { request } from "../../../api/request";
import { apiErrorMessage } from "../../../utils/apiError";
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

function StorageFeatureAccess() {
  const { t } = useTranslation();
  const [visibility, setVisibility] = useState<ResourceVisibilityMode>("all");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void request<{ visibility: "all" | "groups"; group_ids: string[] }>(
      "/admin/storage-backends/access",
    )
      .then((row) => {
        if (cancelled) return;
        setVisibility(row.visibility === "groups" ? "groups" : "all");
        setGroupIds(row.group_ids ?? []);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          message.error(apiErrorMessage(err, t("storage.featureAccessFailed")));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const save = useCallback(
    async (nextVisibility: "all" | "groups", nextIds: string[]) => {
      try {
        const saved = await request<{
          visibility: "all" | "groups";
          group_ids: string[];
        }>("/admin/storage-backends/access", {
          method: "PUT",
          body: JSON.stringify({
            visibility: nextVisibility,
            group_ids: nextIds,
          }),
        });
        setVisibility(saved.visibility === "groups" ? "groups" : "all");
        setGroupIds(saved.group_ids ?? []);
        message.success(t("storage.featureAccessSaved"));
      } catch (err) {
        message.error(apiErrorMessage(err, t("storage.featureAccessFailed")));
      }
    },
    [t],
  );

  return (
    <div className={styles.featureAccess}>
      <div className={styles.featureAccessTitle}>
        {t("storage.featureAccessTitle")}
      </div>
      <p className={styles.featureAccessHint}>
        {t("storage.featureAccessHint")}
      </p>
      {loading ? (
        <Spin size="small" />
      ) : (
        <ResourceVisibilityFields
          allowOwner={false}
          visibility={visibility}
          groupIds={groupIds}
          onChange={(next) => {
            const nextVisibility =
              next.visibility === "groups" ? "groups" : "all";
            setVisibility(nextVisibility);
            setGroupIds(next.groupIds);
            if (nextVisibility === "groups" && next.groupIds.length === 0) {
              return;
            }
            void save(nextVisibility, next.groupIds);
          }}
        />
      )}
    </div>
  );
}

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
        <StreamSetupGuide
          wide
          icon={
            <OctopEmptyMascot size={120} className={styles.emptyGuideMascot} />
          }
          title={t("storage.emptyGuideTitle")}
          description={t("storage.emptyGuideDesc")}
          steps={[
            {
              label: t("storage.emptyGuideStepWhat"),
              detail: t("storage.emptyGuideStepWhatDetail"),
            },
            {
              label: t("storage.emptyGuideStepHow"),
              detail: t("storage.emptyGuideStepHowDetail"),
            },
            {
              label: t("storage.emptyGuideStepUse"),
              detail: t("storage.emptyGuideStepUseDetail"),
            },
          ]}
          primaryAction={{
            label: t("storage.goToTypes"),
            onClick: () => setActiveTab("types"),
            icon: <LayoutGrid size={14} />,
          }}
        />
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
      <>
        <StorageFeatureAccess />
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
      </>
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
            label: (
              <TabLabel icon={HardDrive}>{t("storage.myStorage")}</TabLabel>
            ),
            children: myStorageContent,
          },
          {
            key: "types",
            label: (
              <TabLabel icon={LayoutGrid}>
                {t("storage.supportedTypes")}
              </TabLabel>
            ),
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
