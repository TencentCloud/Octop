/**
 * SearchKeys — standalone route wrapper for the search-key panel.
 *
 * The unified `/keys` page renders the same panel inside a tab.
 */
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { SearchKeysPanel } from "./SearchKeysPanel";

export default function SearchKeysPage() {
  const { t } = useTranslation();
  return (
    <PageShell title={t("nav.searchKeys")}>
      <SearchKeysPanel />
    </PageShell>
  );
}
