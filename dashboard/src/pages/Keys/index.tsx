/**
 * Keys — unified self-service key page.
 *
 * Renders the panels registered in ./tabs. A single registered panel is
 * rendered without a tab bar, so each credential feature can ship on its own;
 * a second panel turns the page into a multi-tab view automatically. The
 * standalone `/model-keys` / `/search-keys` routes remain for deep links.
 */
import { useCallback, useMemo } from "react";
import { Tabs } from "antd";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import PageShell from "../../layouts/PageShell";
import { KEYS_TABS } from "./tabs";

export default function KeysPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const defaultKey = KEYS_TABS[0]?.key ?? "";
  const requested = params.get("tab");
  const active =
    requested && KEYS_TABS.some((tab) => tab.key === requested)
      ? requested
      : defaultKey;

  const onChange = useCallback(
    (next: string) => {
      const updated = new URLSearchParams(params);
      if (next === defaultKey) updated.delete("tab");
      else updated.set("tab", next);
      setParams(updated, { replace: true });
    },
    [params, setParams, defaultKey],
  );

  const items = useMemo(
    () =>
      KEYS_TABS.map(({ key, labelKey, Component }) => ({
        key,
        label: t(labelKey),
        children: <Component />,
      })),
    [t],
  );

  if (items.length === 1) {
    return (
      <PageShell title={t(KEYS_TABS[0].labelKey)}>
        {items[0].children}
      </PageShell>
    );
  }

  return (
    <PageShell title={t("nav.keys")}>
      <Tabs activeKey={active} onChange={onChange} items={items} />
    </PageShell>
  );
}
