import * as React from "react";
import * as ui from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import type { InstalledPlugin } from "../../../api/modules/plugins";
import { message } from "../../../utils/antdMessage";

interface SettingsHost {
  version: 1;
  React: typeof React;
  ui: typeof ui;
  message: typeof message;
  locale: string;
  request<T>(options?: RequestInit): Promise<T>;
}

interface SettingsModule {
  createSettingsPanel(host: SettingsHost): React.ComponentType;
  css?: string;
}

class SettingsBoundary extends React.Component<
  { children: React.ReactNode; fallback: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** Load a plugin-owned, self-contained settings module through the shared SDK. */
export function PluginSettingsPanel({ plugin }: { plugin: InstalledPlugin }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage || "en";
  const [revision, retry] = React.useReducer((value: number) => value + 1, 0);
  const [loaded, setLoaded] = React.useState<{
    Panel: React.ComponentType;
    css: string;
  } | null>(null);
  const [failed, setFailed] = React.useState(false);
  const entry = plugin.settings_ui?.entry;
  React.useEffect(() => {
    let active = true;
    setLoaded(null);
    setFailed(false);
    if (!entry) return;
    const id = encodeURIComponent(plugin.id);
    const path = entry.replace(/^\/+/, "").replace(/^ui\//, "");
    void (async () => {
      let url: string | undefined;
      try {
        const source = await request<string>(`/plugins/${id}/ui/${path}`, {
          cache: "no-store",
        });
        url = URL.createObjectURL(
          new Blob([source], { type: "text/javascript" }),
        );
        const module = (await import(/* @vite-ignore */ url)) as SettingsModule;
        if (typeof module.createSettingsPanel !== "function")
          throw new Error("Invalid settings module");
        const Panel = module.createSettingsPanel({
          version: 1,
          React,
          ui,
          message,
          locale,
          request: <T,>(options?: RequestInit) =>
            request<T>(`/plugins/${id}/settings`, options),
        });
        if (active) setLoaded({ Panel, css: module.css || "" });
      } catch {
        if (active) setFailed(true);
      } finally {
        if (url) URL.revokeObjectURL(url);
      }
    })();
    return () => {
      active = false;
    };
  }, [plugin.id, plugin.version, entry, locale, revision]);
  const fallback = (
    <ui.Alert
      type="error"
      showIcon
      message={t("plugins.settingsLoadFailed")}
      action={<ui.Button onClick={retry}>{t("common.retry")}</ui.Button>}
    />
  );
  if (failed) return fallback;
  if (!loaded) return <ui.Spin />;
  return (
    <SettingsBoundary
      key={`${plugin.id}:${locale}:${revision}`}
      fallback={fallback}
    >
      <style>{loaded.css}</style>
      <loaded.Panel />
    </SettingsBoundary>
  );
}
