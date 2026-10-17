import {
  Component,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Alert, Button, Empty, List, Spin } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { pluginsApi } from "../../api/modules/plugins";
import { loadInstalledPluginUis } from "../../plugins/toolRenderers/loader";
import { ensureBuiltinToolRenderers } from "../../plugins/toolRenderers/ensureBuiltins";
import { createPluginPageHost } from "../../plugins/toolRenderers/host";
import {
  getPluginPagesVersion,
  listPluginPages,
  resolvePluginPage,
  subscribePluginPages,
} from "../../plugins/pages/registry";
import { PLUGINS_CHANGED_EVENT } from "../Admin/Plugins/pluginsEvents";

class PageBoundary extends Component<
  { children: ReactNode; message: string },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <Alert type="error" showIcon message={this.props.message} />
    ) : (
      this.props.children
    );
  }
}

/** Authenticated plugin pages, independent of agent/model/chat initialization. */
export default function PluginPagesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pluginId, pageId } = useParams();
  const version = useSyncExternalStore(
    subscribePluginPages,
    getPluginPagesVersion,
    getPluginPagesVersion,
  );
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const host = useMemo(createPluginPageHost, []);

  useEffect(() => {
    let active = true;
    async function load() {
      if (active) setPhase("loading");
      try {
        ensureBuiltinToolRenderers();
        await loadInstalledPluginUis(await pluginsApi.list());
        if (active) setPhase("ready");
      } catch {
        if (active) setPhase("error");
      }
    }
    void load();
    window.addEventListener(PLUGINS_CHANGED_EVENT, load);
    return () => {
      active = false;
      window.removeEventListener(PLUGINS_CHANGED_EVENT, load);
    };
  }, []);

  const page = pluginId && pageId ? resolvePluginPage(pluginId, pageId) : null;
  const pages = listPluginPages();
  const Page = page?.component;
  const unavailable = t(
    "pluginPages.unavailable",
    "This plugin page is unavailable.",
  );
  return (
    <PageShell
      title={page?.title ?? t("pluginPages.title", "Plugin pages")}
      actions={
        pluginId ? (
          <Button onClick={() => navigate("/extensions")}>
            {t("pluginPages.back", "All plugin pages")}
          </Button>
        ) : undefined
      }
    >
      {phase === "loading" ? (
        <Spin />
      ) : phase === "error" ? (
        <Alert
          type="error"
          showIcon
          message={t(
            "pluginPages.loadFailed",
            "Could not load plugin pages. Please try again.",
          )}
        />
      ) : pluginId && pageId ? (
        Page && page ? (
          <PageBoundary
            key={`${pluginId}:${pageId}:${version}`}
            message={unavailable}
          >
            <Page pluginId={page.pluginId} host={host} />
          </PageBoundary>
        ) : (
          <Alert type="warning" showIcon message={unavailable} />
        )
      ) : pages.length ? (
        <List
          dataSource={pages}
          renderItem={(item) => (
            <List.Item
              key={`${item.pluginId}:${item.id}`}
              actions={[
                <Button
                  key="open"
                  onClick={() =>
                    navigate(
                      `/extensions/${encodeURIComponent(
                        item.pluginId,
                      )}/${encodeURIComponent(item.id)}`,
                    )
                  }
                >
                  {t("pluginPages.open", "Open")}
                </Button>,
              ]}
            >
              <List.Item.Meta title={item.title} description={item.pluginId} />
            </List.Item>
          )}
        />
      ) : (
        <Empty
          description={t(
            "pluginPages.empty",
            "No enabled plugin pages are installed.",
          )}
        />
      )}
    </PageShell>
  );
}
