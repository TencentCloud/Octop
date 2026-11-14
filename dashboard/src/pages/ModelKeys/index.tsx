/**
 * ModelKeys — standalone route wrapper for the model-key panel.
 *
 * The unified `/keys` page renders the same panel inside a tab.
 */
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { ModelKeysPanel } from "./ModelKeysPanel";

export default function ModelKeysPage() {
  const { t } = useTranslation();
  return (
    <PageShell title={t("nav.modelKeys")}>
      <ModelKeysPanel />
    </PageShell>
  );
}
