import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Segmented } from "antd";
import { Globe, TerminalSquare } from "lucide-react";
import TerminalPage from "../Terminal";
import RemoteBrowserPage from "../RemoteBrowser";
import styles from "./index.module.less";

export type WorkbenchTab = "terminal" | "browser";

const TAB_STORAGE_KEY = "octop:workbench:tab";

function isWorkbenchTab(
  value: string | null | undefined,
): value is WorkbenchTab {
  return value === "terminal" || value === "browser";
}

/** Resolve tab from a concrete workbench subpath. Bare `/workbench` → null. */
function tabFromPath(pathname: string): WorkbenchTab | null {
  if (
    pathname === "/workbench/terminal" ||
    pathname.startsWith("/workbench/terminal/")
  ) {
    return "terminal";
  }
  if (
    pathname === "/workbench/browser" ||
    pathname.startsWith("/workbench/browser/")
  ) {
    return "browser";
  }
  return null;
}

export function readSavedWorkbenchTab(): WorkbenchTab {
  try {
    const saved = localStorage.getItem(TAB_STORAGE_KEY);
    if (isWorkbenchTab(saved)) return saved;
  } catch {
    /* ignore */
  }
  return "browser";
}

interface WorkbenchPageProps {
  /** True when the workbench keep-alive surface is currently shown. */
  isVisible?: boolean;
}

export default function WorkbenchPage({
  isVisible = true,
}: WorkbenchPageProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  const pathTab = tabFromPath(location.pathname);
  const isBareWorkbench = location.pathname === "/workbench";
  const activeTab: WorkbenchTab = pathTab ?? readSavedWorkbenchTab();

  // Do not mount panels while on bare `/workbench` — wait for redirect so we
  // don't spuriously start the browser stream when the saved tab is terminal.
  const [terminalMounted, setTerminalMounted] = useState(false);
  const [browserMounted, setBrowserMounted] = useState(false);

  useEffect(() => {
    if (!isBareWorkbench) return;
    navigate(
      `/workbench/${readSavedWorkbenchTab()}${location.search}${location.hash}`,
      { replace: true },
    );
  }, [isBareWorkbench, location.search, location.hash, navigate]);

  useEffect(() => {
    if (!pathTab) return;
    try {
      localStorage.setItem(TAB_STORAGE_KEY, pathTab);
    } catch {
      /* ignore */
    }
  }, [pathTab]);

  useEffect(() => {
    if (!pathTab) return;
    if (pathTab === "terminal") setTerminalMounted(true);
    if (pathTab === "browser") setBrowserMounted(true);
  }, [pathTab]);

  const handleTabChange = useCallback(
    (value: string | number) => {
      const next = String(value);
      if (!isWorkbenchTab(next) || next === activeTab) return;
      navigate(`/workbench/${next}${location.search}${location.hash}`, {
        replace: false,
      });
    },
    [activeTab, location.search, location.hash, navigate],
  );

  const tabOptions = useMemo(
    () => [
      {
        label: (
          <span className={styles.tabLabel}>
            <Globe size={14} strokeWidth={2} />
            {t("workbench.tabs.browser")}
          </span>
        ),
        value: "browser",
      },
      {
        label: (
          <span className={styles.tabLabel}>
            <TerminalSquare size={14} strokeWidth={2} />
            {t("workbench.tabs.terminal")}
          </span>
        ),
        value: "terminal",
      },
    ],
    [t],
  );

  const browserVisible = isVisible && pathTab === "browser";
  const terminalVisible = isVisible && pathTab === "terminal";

  return (
    <div className={styles.workbench}>
      <div className={styles.header}>
        <div className={styles.headerInfo}>
          <h1 className={styles.title}>{t("workbench.title")}</h1>
          <p className={styles.description}>{t("workbench.description")}</p>
        </div>
        <Segmented
          size="middle"
          value={activeTab}
          options={tabOptions}
          onChange={handleTabChange}
        />
      </div>

      <div className={styles.panels}>
        {browserMounted && (
          <div
            className={styles.panel}
            style={{ display: pathTab === "browser" ? "flex" : "none" }}
            aria-hidden={pathTab !== "browser"}
          >
            <RemoteBrowserPage embedded isVisible={browserVisible} />
          </div>
        )}
        {terminalMounted && (
          <div
            className={styles.panel}
            style={{ display: pathTab === "terminal" ? "flex" : "none" }}
            aria-hidden={pathTab !== "terminal"}
          >
            <TerminalPage embedded isVisible={terminalVisible} />
          </div>
        )}
      </div>
    </div>
  );
}
